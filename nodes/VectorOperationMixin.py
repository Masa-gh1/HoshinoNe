'''
VectorOperationMixin - vector 操作の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import FlowData
from base import DataBlock
import utils.numpy_helpers as nh

class VectorOperationMixin:
    """vector 操作の共通機能を提供するMixin"""
    
    @classmethod
    def computeCombinedVector(cls, vectorDatas, operation):
        """複数 vector を事前に統合計算"""
        if not vectorDatas:
            return None
        if len(vectorDatas) == 1:
            return vectorDatas[0]
        
        # 最初の vector をベースとしてコピー
        result = FlowData(vectorDatas[0].headers.copy())

        # 最初の vector のデータをコピー
        for planeIndex in range(vectorDatas[0].getPlaneCount()):
            block = vectorDatas[0].getBlock(planeIndex,0,0)
            data = block.data.copy()
            
            # 残りの vector を順次適用
            for vectorData in vectorDatas[1:]:
                w, h = vectorData.getDimensions()
                next = vectorData.getBlock(planeIndex,0,0)
                data = operation(data, next.data)

            height, width = data.shape
            result.setDimensions(width, height)
            result.setBlock(DataBlock( data, planeIndex, 0, 0))
        
        return result
    
    @classmethod
    def calculateVectorRange(cls, vector, width, height):
        """vector の範囲を計算"""
        if vector is None:
            return 0.0, 0.0
        
        # ベクトルの各成分の最小値と最大値を計算
        minVal = np.min(vector)
        maxVal = np.max(vector)
        
        # ベクトルの各成分の最小値と最大値を計算
        return minVal, maxVal
