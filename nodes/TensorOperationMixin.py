'''
TensorOperationMixin - tensor 操作の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

class TensorOperationMixin:
    """tensor 操作の共通機能を提供するMixin"""
    
    @classmethod
    def computeCombinedTensor(cls, tensorDatas, operation):
        """複数 tensor を事前に統合計算"""
        from base import FlowData
        from base import DataBlock
        
        if not tensorDatas:
            return None
        if len(tensorDatas) == 1:
            return tensorDatas[0]
        
        # 最初の tensor をベースとしてコピー
        result = FlowData(tensorDatas[0].headers.copy())

        for planeIndex in range(tensorDatas[0].getPlaneCount()):
            block = tensorDatas[0].getBlock(planeIndex,0,0)
            data = block.data
            
            # 残りの tensor を順次適用
            for tensorData in tensorDatas[1:]:
                w, h = tensorData.getDimensions()
                next = tensorData.getBlock(planeIndex,0,0)
                data = operation(data, next.data)

            height, width = data.shape
            result.setDimensions(width, height)
            result.setBlock(DataBlock( data, planeIndex, 0, 0))
        
        return result
    
    @classmethod
    def calculateTensorRange(cls, tensor, width, height):
        """tensor の範囲を計算"""
        import numpy as np
        
        if tensor is None:
            return 0.0, 0.0
        
        # tensorの各成分の最小値と最大値を計算
        minVal = np.min(tensor)
        maxVal = np.max(tensor)
        
        # tensorの各成分の最小値と最大値を計算
        return minVal, maxVal
