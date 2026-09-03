'''
BayerUnpackSparseNode - ベイヤー分離(疎)ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import DataBlock, LazyFlowData
from nodes import LazyNNOperationNode

class BayerUnpackSparseNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'bayer_unpack_sparse'
    # ノード名
    name      = 'ベイヤー分離(疎)'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def preprocessStream(self, inputStream):
        """ベイヤーデータのみを抽出"""
        return [data for data in inputStream if data.headers.get('is_bayer', False)]
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return BayerUnpackSparseLazyFlowData(inputData)
    
class BayerUnpackSparseLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y):
        """ベイヤー分離操作（3プレーン、元サイズ、NaN埋め）"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        block = flowData.getBlock(0, x, y)
        if not block or block.data is None:
            return None
        
        # ベイヤーパターンを取得
        bayer_pattern = flowData.headers.get('bayer_pattern', 'RGGB')
        
        data = block.data
        height, width = data.shape
        result = nh.nans((height, width))
        
        # 座標配列を作成
        x_coords, y_coords = np.meshgrid(nh.arange(width), nh.arange(height), copy=False, sparse=True)
        
        # ベイヤーパターンに応じてマスクを作成     [   R      G1      B       G2  ]
        if   bayer_pattern == 'RGGB': offsets = [(0, 0), (0, 1), (1, 1), (1, 0)]
        elif bayer_pattern == 'GRBG': offsets = [(0, 1), (0, 0), (1, 0), (1, 1)]
        elif bayer_pattern == 'GBRG': offsets = [(1, 0), (1, 1), (0, 1), (0, 0)]
        elif bayer_pattern == 'BGGR': offsets = [(1, 1), (1, 0), (0, 0), (0, 1)]
        else                        : offsets = [(0, 0), (0, 1), (1, 1), (1, 0)] # デフォルト RGGB

        dy, dx = offsets[planeIndex]
        mask = (y_coords % 2 == dy) & (x_coords % 2 == dx)

        if 1 == planeIndex:  # G は 2つあるのでもう 1 px 追加
            dy, dx = offsets[3]
            mask |= (y_coords % 2 == dy) & (x_coords % 2 == dx)
        
        # マスクを適用してピクセルを抽出
        if planeIndex < 3:
            result[mask] = data[mask]
        
        return DataBlock(result, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['mode', 'planes']

    def headerOperation(self, lazyFlowData, key):
        return {
            'mode': 'RGB',
            'planes': ['R', 'G', 'B']
        }
