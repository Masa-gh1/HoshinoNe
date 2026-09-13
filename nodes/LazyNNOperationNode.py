'''
LazyNNOperationNode - LazyFlowDataを用いるN:N処理基底クラス

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from itertools import zip_longest
from abc import abstractmethod

from base.FlowNode_CONST import *
from .NxBlockOperationNode import NxBlockOperationNode

if TYPE_CHECKING:
    from base.DataBlock import DataBlock
    from base.FlowData import FlowData
    from base.LazyFlowData import LazyFlowData

class LazyNNOperationNode(NxBlockOperationNode):
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
    
    @abstractmethod
    def createLazyFlowData(self, inputDatas:FlowData|list[FlowData]) -> LazyFlowData:
        """LazyFlowDataを作成（サブクラスで実装）
        
        Args:
            inputDatas: 入力 FlowData のリスト
            
        Returns:
            LazyFlowData
        """
        pass
