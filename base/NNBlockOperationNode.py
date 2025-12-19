'''
NNBlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
from .FlowNode import FlowNode
from .FlowData import FlowData
from concurrent.futures import as_completed
from utils.ThreadPool import ProcessExecutor

class NNBlockOperationNode(FlowNode):
    """データ入出力 N:N のブロック単位計算ノードの基底クラス"""

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
        
        # 前処理（サブクラスでオーバーライド可能）
        processedInputs = self.preprocessInputs(inputDatas)
        
        resultFlowDatas = []
        futureToDatas = {}
        
        for inputData in processedInputs:
            # 結果用のFlowDataを初期化
            width, height = inputData.getDimensions()
            headers = inputData.headers.copy() if inputData.headers else {}
            flowData = FlowData(headers)
            flowData.setDimensions(width, height)
            
            # display_levelsを計算して設定
            displayLevels = self.getDisplayLevels(inputData)
            if displayLevels and flowData.headers:
                flowData.headers['display_levels'] = displayLevels
            
            resultFlowDatas.append(flowData)
            
            # ブロック単位で並列処理
            for block in inputData.iterateBlocks():
                future = ProcessExecutor.submit(self.processBlock, block)
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
    
    def getDisplayLevels(self, inputFlowData):
        """入力データから出力のdisplay_levelsを計算（サブクラスでオーバーライド）
        
        Args:
            inputFlowData: 入力FlowData
            
        Returns:
            display_levelsの辞書、またはNone
        """
        return None
    
    @abstractmethod
    def processBlock(self, block):
        """単一ブロックの処理（サブクラスで実装）
        
        Args:
            block: 処理対象のブロック
            
        Returns:
            処理結果のDataBlock
        """
        pass