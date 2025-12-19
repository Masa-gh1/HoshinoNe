'''
BayerUnpackSparseNode - ベイヤー分離(疎)ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from base import DataBlock, LazyFlowData
from nodes import LazyNNOperationNode
from utils import numpy_helpers as nh

class BayerUnpackSparseNode(LazyNNOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "bayer_unpack_sparse", "ベイヤー分離(疎)")
    
    def getColor(self):
        return self._color_func
    
    def preprocessInputs(self, inputDatas):
        """ベイヤーデータのみを抽出"""
        return [data for data in inputDatas if data.headers.get('is_bayer', False)]
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._bayerUnpackOperation)
        lazyFlowData.addHeaderOperation('mode', self._computeHeaders)
        lazyFlowData.addHeaderOperation('planes', self._computeHeaders)
        return lazyFlowData
    
    @classmethod
    def _bayerUnpackOperation(cls, flowData, planeIndex, x, y):
        """ベイヤー分離操作（3プレーン、元サイズ、NaN埋め）"""
        block = flowData.getBlock(0, x, y)
        if not block or block.data is None:
            return None
        
        # ベイヤーパターンを取得
        bayer_pattern = flowData.headers.get('bayer_pattern', 'RGGB')
        
        data = block.data
        height, width = data.shape
        result = nh.nans((height, width))
        
        # 座標配列を作成（スレッドセーフ: np.mgrid 置き換え）
        y_indices = np.arange(height).reshape(-1, 1)
        x_indices = np.arange(width)
        y_coords = np.broadcast_to(y_indices, (height, width))
        x_coords = np.broadcast_to(x_indices, (height, width))
        
        # ベイヤーパターンに応じてマスクを作成
        if bayer_pattern == 'RGGB':
            if planeIndex == 0:  # R
                mask = (y_coords % 2 == 0) & (x_coords % 2 == 0)
            elif planeIndex == 1:  # G
                mask = ((y_coords % 2 == 0) & (x_coords % 2 == 1)) | ((y_coords % 2 == 1) & (x_coords % 2 == 0))
            elif planeIndex == 2:  # B
                mask = (y_coords % 2 == 1) & (x_coords % 2 == 1)
        elif bayer_pattern == 'GRBG':
            if planeIndex == 0:  # R
                mask = (y_coords % 2 == 0) & (x_coords % 2 == 1)
            elif planeIndex == 1:  # G
                mask = ((y_coords % 2 == 0) & (x_coords % 2 == 0)) | ((y_coords % 2 == 1) & (x_coords % 2 == 1))
            elif planeIndex == 2:  # B
                mask = (y_coords % 2 == 1) & (x_coords % 2 == 0)
        elif bayer_pattern == 'GBRG':
            if planeIndex == 0:  # R
                mask = (y_coords % 2 == 1) & (x_coords % 2 == 0)
            elif planeIndex == 1:  # G
                mask = ((y_coords % 2 == 0) & (x_coords % 2 == 0)) | ((y_coords % 2 == 1) & (x_coords % 2 == 1))
            elif planeIndex == 2:  # B
                mask = (y_coords % 2 == 0) & (x_coords % 2 == 1)
        elif bayer_pattern == 'BGGR':
            if planeIndex == 0:  # R
                mask = (y_coords % 2 == 1) & (x_coords % 2 == 1)
            elif planeIndex == 1:  # G
                mask = ((y_coords % 2 == 0) & (x_coords % 2 == 1)) | ((y_coords % 2 == 1) & (x_coords % 2 == 0))
            elif planeIndex == 2:  # B
                mask = (y_coords % 2 == 0) & (x_coords % 2 == 0)
        else:
            # デフォルト（RGGB）
            if planeIndex == 0:  # R
                mask = (y_coords % 2 == 0) & (x_coords % 2 == 0)
            elif planeIndex == 1:  # G
                mask = ((y_coords % 2 == 0) & (x_coords % 2 == 1)) | ((y_coords % 2 == 1) & (x_coords % 2 == 0))
            elif planeIndex == 2:  # B
                mask = (y_coords % 2 == 1) & (x_coords % 2 == 1)
        
        # マスクを適用してピクセルを抽出
        if planeIndex < 3:
            result[mask] = data[mask]
        
        return DataBlock(result, planeIndex, x, y)
    
    @classmethod
    def _computeHeaders(cls):
        """ヘッダー情報を計算"""
        def compute(lazyFlowData):
            return {
                'mode': 'RGB',
                'planes': ['R', 'G', 'B']
            }
        return compute