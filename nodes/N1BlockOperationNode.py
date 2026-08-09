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
        from utils import measurement as mes
        from utils.ThreadPool import ParallelExecutor

        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)
        
        if not inputStreams or not any(inputStreams):
            self.flowDatas = []
            self.reportProgress(context, "完了")
            return
        
        # 前処理
        tempStreams = self.preprocessStreams(inputStreams)
        processedDatas = []
        for stream in tempStreams:
            processedStream = self.preprocessInputs(stream)
            processedDatas.extend(processedStream)
        
        if not processedDatas:
            self.flowDatas = []
        else:
            # 結果用の FlowData を初期化
            flowData = self.createFlowData(processedDatas)
            
            # ブロック単位で並列処理
            futures = []
            for block in flowData.iterateBlocks():
                planeIndex = block.planeIndex
                x, y = block.x, block.y
                future = ParallelExecutor.submit(self, mes.elapsedThreading, self.operation, processedDatas, planeIndex, x, y)
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
    
    def preprocessStreams(self, inputStreams):
        """入力ストリームの前処理（サブクラスでオーバーライド可能）
        演算結果のデータタイプを primary 優先とするため、
        primary/auxiliaryで分類し、primaryを前に集める。
        
        Args:
            inputStreams: 入力ストリームのリスト
            
        Returns:
            処理対象ストリームのリスト
        """
        def getPriority(stream):
            category = stream[0].headers.get("category", "primary")
            dataType = stream[0].headers.get("type", "table")
            n        = len(stream)
            
            if   "primary"   == category: priority =     0
            elif "auxiliary" == category: priority = 10000
            else                        : priority = 20000
            
            if   "tensor"     == dataType: priority += 1000
            elif "polynomial" == dataType: priority += 2000
            else                         : priority +=    0
            
            priority += n

            return priority
        
        streams = filter(lambda s: s, inputStreams)
        streams = sorted(streams, key=getPriority)
        return streams
    
    def preprocessInputs(self, inputStream):
        """入力データの前処理(サブクラスでオーバーライド可能)
        
        Args:
            inputStream: 入力ストリーム
            
        Returns:
            処理対象データのリスト
        """
        return inputStream
    
    def createFlowData(self, inputDatas):
        """
        FlowDataを作成 (サブクラスでオーバーライド可能)
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            FlowData
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
    
    def operation(self, flowDatas, planeIndex, x, y):
        """
        単一ブロックの処理 (サブクラスでオーバーライド可能)
        
        Args:
            flowDatas: 入力 FlowDatas
            planeIndex: 処理する plane のインデックス
            x: 処理するブロックの x 座標
            y: 処理するブロックの y 座標
            
        Returns:
            処理結果のDataBlock
        """
        from base import BroadcastMixin
        blocks, shape = BroadcastMixin.calculateBroadcastedBlock(flowDatas, planeIndex, x, y)
        if not blocks:
            return None
        else:
            return self.blockOperation(blocks, planeIndex, x, y)

    def blockOperation(self, blocks, planeIndex, x, y):
        """
        単一ブロックの処理 (サブクラスでオーバーライド可能)
        
        Args:
            blocks: 入力データのリスト
            planeIndex: 処理する plane のインデックス
            x: 処理するブロックの x 座標
            y: 処理するブロックの y 座標
            
        Returns:
            処理結果のDataBlock
        """
        return None
