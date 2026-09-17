'''
BroadcastMixin - ブロードキャスト処理の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from .PolynomialOperationMixin import PolynomialOperationMixin
from .TensorOperationMixin     import TensorOperationMixin

if TYPE_CHECKING:
    from .DataBlock import DataBlock
    from .FlowData import FlowData

class BroadcastMixin:
    """ブロードキャスト処理の共通機能を提供するMixin"""
    
    @classmethod
    def calculateBroadcastedStream(cls, streams):
        """stream 間でデータのブロードキャストを行う
        
        Args:
            streams: stream のリスト
            
        Returns:
            tuple: stream のリスト
        """
        num = 0
        for stream in streams:
            if stream:
                num = max(num, len(stream))

        result = []
        for stream in streams:
            if 1 < num and 1 == len(stream):
                result.append(stream*num) # 1枚だけなので、最長の枚数分ブロードキャストする
            else:
                result.append(stream)
        return result

    @classmethod
    def calculateBroadcastedBlock(cls, flowDatas:FlowData|list[FlowData], planeIndex:int, x:int, y:int, shape=None) -> tuple[DataBlock|list[DataBlock], tuple]:
        """FlowData 間でブロードキャストを行うブロックを計算する
        
        Args:
            flowDatas: FlowData のリスト
            planeIndex: プレーンインデックス
            x: X座標
            y: Y座標
            shape: ブロックの形状（指定しない場合は先頭の FlowData に合わせる）
            
        Returns:
            tuple: (DataBlock のリスト, ブロックの形状)
        """
        import numpy as np
        inputFlowDatas = flowDatas if isinstance(flowDatas, (list,tuple)) else [flowDatas]
        
        dataTypes = []
        blocks    = []
        maxShape  = [0,0]
        for flowData in inputFlowDatas:
            dataType = flowData.headers.get('type', 'table')
            dataTypes.append(dataType)
            if 1 == flowData.getPlaneCount():
                block = flowData.getBlock(0, x, y)
            else:
                block = flowData.getBlock(planeIndex, x, y)
            blocks.append(block)
            if 'polynomial' == dataType:
                pass
            else:
                if block:
                    maxShape = [max(a,b) for a,b in zip(maxShape, block.data.shape)]
        
        maxShape = tuple(maxShape)
        
        # ブロックの計算
        retBlocks = []
        for flowData, dataType, block in zip(inputFlowDatas, dataTypes, blocks):
            if not np.all(maxShape):
                # ブロックに面積がない
                pass
            elif 'tensor' == dataType:
                block = TensorOperationMixin.calculateTensorBlock(flowData, planeIndex, x, y, maxShape, defaultValue=np.nan)
            elif 'polynomial' == dataType:
                block = PolynomialOperationMixin.calculatePolynomialBlock(flowData, planeIndex, x, y, maxShape, defaultValue=np.nan)
            else:
                pass
            
            retBlocks.append(block)

        if retBlocks and np.all(maxShape) and maxShape != retBlocks[0].data.shape and (1 in maxShape or 1 in retBlocks[0].data.shape):
            # 1つ目のデータの大きさが異なるので、1つ目だけブロードキャスト適用する。
            # これにより、サブクラスでの実装でを簡潔にする。(インプレース演算(+=)を使える)
            from .DataBlock import DataBlock
            data = np.zeros(maxShape, dtype=retBlocks[0].data.dtype) + retBlocks[0].data
            retBlocks[0] = DataBlock(data, planeIndex, x, y)
        
        if isinstance(flowDatas, (list,tuple)):
            return(retBlocks, maxShape)
        else:
            return(retBlocks[0], maxShape)
