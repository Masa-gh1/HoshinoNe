'''
NNBlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from base import FlowData
from base import FlowNode
from utils.ThreadPool import ProcessExecutorInNode

class NNBlockOperationNode(FlowNode):
    """データ入出力 N:N のブロック単位計算ノードの基底クラス"""
    # ノードタイプ
    majorType = 'NN_block_operation'
    minorType = 'NN_block_operation'
    # ノード名
    name      = 'NNBlockOperationNode'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_PAS

    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputDatas = []
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        if not inputDatas:
            self.flowDatas = []
            self.reportProgress(context, "完了")
            return
        
        # 前処理
        processedInputs = self.preprocessInputs(inputDatas)
        
        resultFlowDatas = []
        futureToDatas = {}
        
        for inputData in processedInputs:
            # 結果用のFlowDataを初期化
            width, height = inputData.getDimensions()
            headers = inputData.headers.copy() if inputData.headers else {}
            flowData = FlowData(headers)
            flowData.setDimensions(width, height)
            
            # display_levelsをheaders経由で計算
            self.setupDisplayLevels(flowData, inputData)
            
            resultFlowDatas.append(flowData)
            
            # ブロック単位で並列処理
            for block in inputData.iterateBlocks():
                future = ProcessExecutorInNode.submit(self, self.processBlock, block)
                futureToDatas[future] = flowData
        
        # 全ブロックの処理完了を待つ
        self.reportProgress(context, "処理中")
        totalBlocks = len(futureToDatas)
        for i, future in enumerate(as_completed(futureToDatas)):
            resultBlock = future.result()
            if resultBlock:
                futureToDatas[future].setBlock(resultBlock)
            self.reportProgress(context, "処理中", i + 1, totalBlocks)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理（サブクラスでオーバーライド可能）
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            処理対象データのリスト
        """
        return inputDatas
    
    def setupDisplayLevels(self, outputFlowData, inputFlowData):
        """出力FlowDataのdisplay_levelsを設定（サブクラスでオーバーライド可能）
        
        Args:
            outputFlowData: 出力FlowData
            inputFlowData: 入力FlowData
        """
        # デフォルトは入力のままコピー
        if inputFlowData.headers and 'display_levels' in inputFlowData.headers:
            outputFlowData.headers['display_levels'] = inputFlowData.headers['display_levels']
    
    @abstractmethod
    def processBlock(self, block):
        """単一ブロックの処理（サブクラスで実装）
        
        Args:
            block: 処理対象のブロック
            
        Returns:
            処理結果のDataBlock
        """
        pass