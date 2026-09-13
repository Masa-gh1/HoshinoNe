'''
NNBlockOperationNode base class

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

class NNBlockOperationNode(NxBlockOperationNode):
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
                    future = ParallelExecutor.submit(self, mes.elapsedThreading, self.operation, inputDatas, planeIndex, x, y)
                    futureToDatas[future] = flowData
                    futureCountPerDatas[flowData] += 1
            else:
                flowData = self.createFlowData(inputDatas[0])
                futureCountPerDatas[flowData] = 0
            
                # ブロック単位で並列処理
                for block in flowData.iterateBlocks():
                    planeIndex = block.planeIndex
                    x, y = block.x, block.y
                    future = ParallelExecutor.submit(self, mes.elapsedThreading, self.operation, inputDatas[0], planeIndex, x, y)
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
    
    def operation(self, flowDatas:list[FlowData], planeIndex:int, x:int, y:int) -> DataBlock:
        """
        単一ブロックの処理 (サブクラスでオーバーライド可能)
        
        Args:
            flowDatas: 入力 FlowDatas
            planeIndex: 処理する plane のインデックス
            x: 処理するブロックの x 座標
            y: 処理するブロックの y 座標
            
        Returns:
            処理結果の DataBlock
        """
        from base import BroadcastMixin
        blocks, shape = BroadcastMixin.calculateBroadcastedBlock(flowDatas, planeIndex, x, y)
        if not blocks:
            return None
        else:
            return self.blockOperation(blocks, planeIndex, x, y)
    
    @abstractmethod
    def blockOperation(self, blocks:DataBlock|list[DataBlock], planeIndex:int, x:int, y:int) -> DataBlock:
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
