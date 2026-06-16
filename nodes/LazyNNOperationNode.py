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
    majorType = 'Lazy_NN_block_operation'
    minorType = 'Lazy_NN_block_operation'
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
        
        # 前処理（サブクラスでオーバーライド可能）
        processedStreams = self.preprocessStreams(inputStreams)
        if not processedStreams:
            processedDatas = self.preprocessInputs([data for stream in inputStreams for data in stream])
        
        resultFlowDatas = []
        
        # LazyFlowDataを作成
        if processedStreams:
            for inputDatas in zip_longest(*processedStreams):
                lazyFlowData = self.createLazyFlowData(inputDatas)
                resultFlowDatas.append(lazyFlowData)
        else:
            for inputDatas in processedDatas:
                lazyFlowData = self.createLazyFlowData(inputDatas)
                resultFlowDatas.append(lazyFlowData)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def preprocessStreams(self, inputStreams):
        """入力ストリームの前処理（サブクラスでオーバーライド可能）
        
        Args:
            inputStreams: 入力ストリームのリスト
            
        Returns:
            処理対象ストリームのリスト
            None の場合、後に preprocessInputs を実行する
        """
        return None # inputStreams
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理（サブクラスでオーバーライド可能）
        
        Args:
            inputStreams: 入力ストリームのリスト
            
        Returns:
            処理対象データのリスト
        """
        return inputDatas
    
    @abstractmethod
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成（サブクラスで実装）
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        pass