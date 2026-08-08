'''
BroadcastMixin - ブロードキャスト処理の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from .PolynomialOperationMixin import PolynomialOperationMixin
from .TensorOperationMixin     import TensorOperationMixin

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
            if 1 == len(stream):
                result.append(stream*num) # 1枚だけなので、最長の枚数分ブロードキャストする
            else:
                result.append(stream)
        return result

    @classmethod
    def calculateBroadcastedBlock(cls, flowDatas, planeIndex, x, y, shape = None):
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
        if isinstance(flowDatas, (list,tuple)):
            blocks = []
            for flowData in flowDatas:
                block, shape = cls.calculateBroadcastedBlock(flowData, planeIndex, x, y, shape)
                blocks.append(block)
            return(blocks, shape)
        else:
            if 1 == flowDatas.getPlaneCount():
                # プレーンが1枚なので複数枚プレーンにブロードキャストする
                planeIndex = 0

            dataType = flowDatas.headers.get('type', 'table')
            if   shape and 'tensor'     == dataType:
                import numpy as np
                block = TensorOperationMixin.calculateTensorBlock(flowDatas, planeIndex, x, y, shape, defaultValue=np.nan)
            elif shape and 'polynomial' == dataType:
                import numpy as np
                block = PolynomialOperationMixin.calculatePolynomialBlock(flowDatas, planeIndex, x, y, shape, defaultValue=np.nan)
            elif dataType in ('tensor', 'polynomial'):
                block = flowDatas.getBlock(planeIndex, x, y)
            elif shape:
                block = flowDatas.getBlock(planeIndex, x, y)
            else:
                block = flowDatas.getBlock(planeIndex, x, y)
                shape = block.data.shape # shape が指定されていない場合、先頭のブロックの shape を使用する
            return(block, shape)
