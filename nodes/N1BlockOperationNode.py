'''
N1BlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from base import FlowNode

class N1BlockOperationNode(FlowNode):
    """データ入出力 N:1 のブロック単位計算ノードの基底クラス"""
    # ノードタイプ
    majorType = 'N1_block_operation'
    minorType = 'N1_block_operation'
    # ノード名
    name      = 'N1BlockOperationNode'
    # 入出力タイプ
    ioType    = _IO_TYPE_N1
    outputCat = _OUT_CAT_PAS
    
    def process(self, context=None):
        from utils.ThreadPool import ProcessExecutorInNode

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
        
        if not processedInputs:
            self.flowDatas = processedInputs
        else:
            # 結果用の FlowData を初期化
            flowData = self.createFlowData(processedInputs)

            # ブロック単位で並列処理
            futures = []
            for block in flowData.iterateBlocks():
                planeIndex = block.planeIndex
                x, y = block.x, block.y
                future = ProcessExecutorInNode.submit(self, self.processBlock, processedInputs, planeIndex, x, y)
                futures.append(future)
            
            # 全ブロックの処理完了を待つ
            self.reportProgress(context, "処理中")
            totalBlocks = len(futures)
            for i, future in enumerate(as_completed(futures)):
                resultBlock = future.result()
                if resultBlock:
                    flowData.setBlock(resultBlock)
                self.reportProgress(context, "処理中", i + 1, totalBlocks)
            self.flowDatas = [flowData]
        
        self.reportProgress(context, "完了")
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理 (サブクラスでオーバーライド可能)
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            処理対象データのリスト
        """
        return inputDatas
    
    def createFlowData(self, inputDatas):
        """
        LazyFlowDataを作成 (サブクラスでオーバーライド可能)
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        from base import FlowData

        # 基準データを決定
        baseDataIndex = self.getBaseDataIndex(inputDatas)
        baseData = inputDatas[baseDataIndex]

        # headers を生成
        headers = baseData.headers.copy() if baseData.headers else {}
        headers.update(self.processHeaders(baseData, inputDatas))

        # サイズを決定
        width, height = self.getOutputDimensions(baseData, inputDatas)
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)
        
        return flowData
    
    def getBaseDataIndex(self, inputDatas):
        """
        基準データのインデックスを返す (サブクラスでオーバーライド可能)
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            基準データのインデックス
        """
        return 0  # デフォルトは最初のデータ
    
    def getOutputDimensions(self, baseData, inputDatas):
        """
        結果画像のサイズを決定 (サブクラスでオーバーライド可能)
        
        Args:
            baseData: 基準データ
            inputDatas: 入力データのリスト
            
        Returns:
            結果のサイズ
        """
        return baseData.getDimensions()
    
    def getUnionDimensions(self, inputDatas):
        """全入力データを包含する最大サイズを計算"""
        width, height = inputDatas[0].getDimensions()
        for data in inputDatas[1:]:
            w, h = data.getDimensions()
            width  = max(width, w)
            height = max(height, h)
        return width, height
    
    def processHeaders(self, baseData, inputDatas):
        """
        出力 FlowData の headers を処理 (サブクラスでオーバーライド可能)
        
        Args:
            baseData: 基準データ
            inputDatas: 入力 FlowData

        Returns:
            出力 FlowData に追記する headers
        """
        return {}
    
    @abstractmethod
    def processBlock(self, inputDatas, planeIndex, x, y):
        """
        単一ブロックの処理 (サブクラスで実装)
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            処理結果のDataBlock
        """
        pass
