'''
LazyNNOperationNode - LazyFlowDataを用いるN:N処理基底クラス

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
from base.FlowNode_CONST import *
from base import FlowNode

class LazyNNOperationNode(FlowNode):
    """LazyFlowDataを用いるN:N処理ノードの基底クラス"""
    # ノードタイプ
    majorType = 'Lazy_NN_block_operation'
    minorType = 'Lazy_NN_block_operation'
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
        
        # 前処理（サブクラスでオーバーライド可能）
        processedInputs = self.preprocessInputs(inputDatas)
        
        resultFlowDatas = []
        
        for inputData in processedInputs:
            # LazyFlowDataを作成
            lazyFlowData = self.createLazyFlowData(inputData)
            resultFlowDatas.append(lazyFlowData)
        
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
    
    @abstractmethod
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成（サブクラスで実装）
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        pass