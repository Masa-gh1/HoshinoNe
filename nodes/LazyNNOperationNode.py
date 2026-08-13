'''
LazyNNOperationNode - LazyFlowDataを用いるN:N処理基底クラス

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from itertools import zip_longest
from abc import abstractmethod

from base.FlowNode_CONST import *
from base import FlowNode

class LazyNNOperationNode(FlowNode):
    """LazyFlowDataを用いるN:N処理ノードの基底クラス"""
    # ノードタイプ
    majorType = 'Lazy_NN_operation'
    minorType = 'Lazy_NN_operation'
    # ノード名
    name      = 'LazyNNOperationNode'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_PAS

    def process(self, context=None):
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
        
        resultFlowDatas = []
        
        for inputDatas in zip_longest(*processedStreams):
            # LazyFlowDataを作成
            if not inputDatas:
                pass
            elif 1 < len(inputDatas):
                lazyFlowData = self.createLazyFlowData(inputDatas)
                resultFlowDatas.append(lazyFlowData)
            else:
                lazyFlowData = self.createLazyFlowData(inputDatas[0])
                resultFlowDatas.append(lazyFlowData)
        
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
            
            priority += max(0, min(999, 1000 - n))
            
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
    
    @abstractmethod
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成（サブクラスで実装）
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        pass