'''
NNPlaneOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from itertools import zip_longest
from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from .NxBlockOperationNode import NxBlockOperationNode

if TYPE_CHECKING:
    from base.DataBlock import DataBlock
    from base.FlowData import FlowData

class NNPlaneOperationNode(NxBlockOperationNode):
    """データ入出力 N:N のプレーン単位計算ノードの基底クラス"""
    # ノードタイプ
    majorType = 'NN_plane_operation'
    minorType = 'NN_plane_operation'
    # ノード名
    name      = 'NNPlaneOperationNode'
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
        
        futureToDatas = {}
        futureCountPerDatas = {}
        
        for inputDatas in zip_longest(*processedStreams):
            # 結果用の FlowData を初期化
            if not inputDatas:
                pass
            elif 1 < len(inputDatas):
                flowData = self.createFlowData(inputDatas)
                futureCountPerDatas[flowData] = 0

                # プレーン単位で並列処理
                for planeIndex in range(flowData.getPlaneCount()):
                    future = ParallelExecutor.submit(self, mes.elapsedThreading, self.planeOperation, inputDatas, planeIndex)
                    futureToDatas[future] = flowData
                    futureCountPerDatas[flowData] += 1
            else:
                flowData = self.createFlowData(inputDatas[0])
                futureCountPerDatas[flowData] = 0

                # プレーン単位で並列処理
                for planeIndex in range(flowData.getPlaneCount()):
                    future = ParallelExecutor.submit(self, mes.elapsedThreading, self.planeOperation, inputDatas[0], planeIndex)
                    futureToDatas[future] = flowData
                    futureCountPerDatas[flowData] += 1
        
        # 全プレーンの処理完了を待つ
        self.reportProgress(context, "処理中")
        resultFlowDatas = []
        totalPlaneCount = len(futureToDatas)
        for i, future in enumerate(as_completed(futureToDatas)):
            resultBlocks = future.result()
            flowData = futureToDatas.pop(future)
            for resultBlock in resultBlocks:
                flowData.setBlock(resultBlock)
            
            futureCountPerDatas[flowData] -= 1
            if 0 == futureCountPerDatas[flowData]:
                # 全部プレーンの処理が終わった flowData を結果配列に追加
                futureCountPerDatas.pop(flowData)
                resultFlowDatas.append(flowData)
            
            self.reportProgress(context, "処理中", i + 1, totalPlaneCount)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    @abstractmethod
    def planeOperation(self, flowDatas:FlowData|list[FlowData], planeIndex:int) -> list[DataBlock]:
        """単一プレーンの処理 (サブクラスで実装)
        
        Args:
            flowDatas: 入力データのリスト
            planeIndex: 処理対象プレーンのインデックス
            
        Returns:
            処理結果の DataBlock のリスト
        """
        pass
