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
        processedStreams = self.preprocessStreams(inputStreams)
        
        resultFlowDatas = []
        
        for inputDatas in zip_longest(*processedStreams):
            # LazyFlowDataを作成
            lazyFlowData = self.createLazyFlowData(inputDatas)
            resultFlowDatas.append(lazyFlowData)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def preprocessStreams(self, inputStreams):
        """入力ストリームの前処理（サブクラスでオーバーライド可能）
        入力データの前処理：primary/auxiliaryで分類し、単一枚を複数枚へブロードキャスト
        
        Args:
            inputStreams: 入力ストリームのリスト
            
        Returns:
            処理対象ストリームのリスト
        """
        num                  = 0
        prmDataStreams       = []
        prmTensorStreams     = []
        prmPolynomialStreams = []
        auxDataStreams       = []
        auxTensorStreams     = []
        auxPolynomialStreams = []
        
        for stream in inputStreams:
            if stream:
                num = max(num, len(stream))
                dataType = stream[0].headers.get('type', 'table')
                if   'tensor' == dataType:
                    prm = prmTensorStreams
                    aux = auxTensorStreams
                elif 'polynomial' == dataType:
                    prm = prmPolynomialStreams
                    aux = auxPolynomialStreams
                else:
                    prm = prmDataStreams
                    aux = auxDataStreams
                
                category = stream[0].headers.get('category', 'primary')
                if category == 'auxiliary':
                    aux.append(stream)
                else:
                    prm.append(stream)
        
        streams = []
        for stream in ( prmDataStreams + prmTensorStreams + prmPolynomialStreams
                      + auxDataStreams + auxTensorStreams + auxPolynomialStreams
                      ):
            if stream:
                if 1==len(stream):
                    streams.append([stream[0]]*num)
                else:
                    streams.append(stream)
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