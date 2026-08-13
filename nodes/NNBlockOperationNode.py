'''
NNBlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from itertools import zip_longest
from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from base import FlowNode

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
        from base import BroadcastMixin
        tempStreams = self.preprocessStreams(inputStreams)
        tempStreams = BroadcastMixin.calculateBroadcastedStream(tempStreams)
        processedStreams = []
        for stream in tempStreams:
            processedstream = self.preprocessStream(stream)
            processedStreams.append(processedstream)
        
        futureToDatas       = {}
        futureCountPerDatas = {}
        
        for inputDatas in zip_longest(*processedStreams):
            # 結果用の FlowData を初期化
            if not inputDatas:
                pass
            elif 1 < len(inputDatas):
                flowData = self.createFlowData(inputDatas)
                futureCountPerDatas[flowData] = 0
            
                # ブロック単位で並列処理
                for block in flowData.iterateBlocks():
                    planeIndex = block.planeIndex
                    x, y = block.x, block.y
                    blocks = [inputData.getBlock(planeIndex, x, y) for inputData in inputDatas]
                    future = ParallelExecutor.submit(self, mes.elapsedThreading, self.blockOperation, blocks, planeIndex, x, y)
                    futureToDatas[future] = flowData
                    futureCountPerDatas[flowData] += 1
            else:
                flowData = self.createFlowData(inputDatas[0])
                futureCountPerDatas[flowData] = 0
            
                # ブロック単位で並列処理
                for block in flowData.iterateBlocks():
                    planeIndex = block.planeIndex
                    x, y = block.x, block.y
                    block = inputDatas[0].getBlock(planeIndex, x, y)
                    future = ParallelExecutor.submit(self, mes.elapsedThreading, self.blockOperation, block, planeIndex, x, y)
                    futureToDatas[future] = flowData
                    futureCountPerDatas[flowData] += 1
        
        # 全ブロックの処理完了を待つ
        self.reportProgress(context, "処理中")
        resultFlowDatas = []
        totalBlockCount = len(futureToDatas)
        for i, future in enumerate(as_completed(futureToDatas)):
            resultBlock = future.result()
            flowData = futureToDatas.pop(future)
            if resultBlock:
                flowData.setBlock(resultBlock)
            
            futureCountPerDatas[flowData] -= 1
            if 0 == futureCountPerDatas[flowData]:
                # 全部ブロックの処理が終わった flowData を結果配列に追加
                futureCountPerDatas.pop(flowData)
                resultFlowDatas.append(flowData)
            
            self.reportProgress(context, "処理中", i + 1, totalBlockCount)
        
        self.flowDatas = resultFlowDatas
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
    
    def preprocessStream(self, inputStream):
        """入力データの前処理(サブクラスでオーバーライド可能)
        
        Args:
            inputStream: 入力ストリーム
            
        Returns:
            処理対象データのリスト
        """
        return inputStream
    
    def createFlowData(self, inputDatas):
        """LazyFlowDataを作成 (サブクラスでオーバーライド可能)
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        from base import FlowData

        inputData = inputDatas[0] if isinstance(inputDatas, (list, tuple)) else inputDatas
        
        # headers を生成
        headers = inputData.headers.copy()
        headers.update(self.processHeaders(inputData))

        # サイズを決定
        width, height = inputData.getDimensions()
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)

        return flowData

    def processHeaders(self, inputData):
        """
        出力 FlowData の headers を処理 (サブクラスでオーバーライド可能)
        
        Args:
            inputFlowData: 入力FlowData
        """
        return {}
    
    @abstractmethod
    def blockOperation(self, block, planeIndex, x, y):
        """単一ブロックの処理 (サブクラスで実装)
        
        Args:
            block: 処理対象のブロック
            planeIndex: 処理対象のプレーンインデックス
            x: 処理対象のブロックの x 座標
            y: 処理対象のブロックの y 座標
            
        Returns:
            処理結果のDataBlock
        """
        pass