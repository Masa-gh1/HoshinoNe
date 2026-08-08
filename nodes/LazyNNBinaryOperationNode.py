'''
LazyNNBinaryOperationNode - LazyFlowDataを用いる N:N 二項演算処理基底クラス

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
from itertools import zip_longest

from abc import abstractmethod
from base.FlowNode_CONST import *
from base import FlowNode

class LazyNNBinaryOperationNode(FlowNode):
    """LazyFlowDataを用いる N:N 二項演算処理ノードの基底クラス"""
    # ノードタイプ
    majorType = 'Lazy_NN_binary_operation'
    minorType = 'Lazy_NN_binary_operation'
    # ノード名
    name      = 'LazyNNBinaryOperationNode'
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
        
        # 前処理（サブクラスでオーバーライド可能）
        from base import BroadcastMixin
        processedStreams = self.preprocessStreams(inputStreams)
        processedStreams = BroadcastMixin.calculateBroadcastedStream(processedStreams)
        
        resultFlowDatas = []
        
        for inputDatas in zip_longest(*processedStreams):
            # LazyFlowDataを作成
            lazyFlowData = self.createLazyFlowData(inputDatas)
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
            
            if   "primary"   == category: priority =  0
            elif "auxiliary" == category: priority = 10
            else                        : priority = 20
            
            if   "tensor"     == dataType: priority += 1
            elif "polynomial" == dataType: priority += 2
            else                         : priority += 0
            
            return priority
        
        streams = filter(lambda s: s, inputStreams)
        streams = sorted(streams, key=getPriority)
        return streams
    
    @abstractmethod
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成（サブクラスで実装）
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        pass