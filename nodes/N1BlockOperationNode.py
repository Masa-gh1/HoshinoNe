'''
N1BlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from .NxBlockOperationNode import NxBlockOperationNode

if TYPE_CHECKING:
    from base.DataBlock import DataBlock
    from base.FlowData import FlowData

class N1BlockOperationNode(NxBlockOperationNode):
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
            processedStream = self.preprocessStream(stream)
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
                future = ParallelExecutor.submit(self, mes.elapsedThreading, self.operation, processedDatas, planeIndex, block.x, block.y)
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

    def blockOperation(self, blocks:list[DataBlock], planeIndex:int, x:int, y:int) -> DataBlock:
        """
        単一ブロックの処理 (サブクラスでオーバーライド可能)
        
        Args:
            blocks: 入力データのリスト
            planeIndex: 処理する plane のインデックス
            x: 処理するブロックの x 座標
            y: 処理するブロックの y 座標
            
        Returns:
            処理結果の DataBlock
        """
        return None
