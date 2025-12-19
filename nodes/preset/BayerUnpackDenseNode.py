'''
BayerUnpackDenseNode - ベイヤー分離(密)ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from config import BLOCK_SIZE
from base.FlowNode_CONST import *
from base import DataBlock, LazyFlowData
from nodes import LazyNNOperationNode
from utils import numpy_helpers as nh

class BayerUnpackDenseNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'bayer_unpack_dense'
    # ノード名
    name      = 'ベイヤー分離(密)'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """ベイヤーデータのみを抽出"""
        return [data for data in inputDatas if data.headers.get('is_bayer', False)]
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._bayerUnpackOperation)
        lazyFlowData.addHeaderOperation('mode'  , self._computeHeaders)
        lazyFlowData.addHeaderOperation('planes', self._computeHeaders)
        lazyFlowData.addHeaderOperation('width' , self._computeHeaders)
        lazyFlowData.addHeaderOperation('height', self._computeHeaders)

        width, height = inputData.getDimensions()
        lazyFlowData.setDimensions(width // 2, height // 2)

        return lazyFlowData
    
    @staticmethod
    def _bayerUnpackOperation(flowData, planeIndex, x, y):
        """ベイヤー分離操作（4プレーン、縦横半分）"""
        # 出力座標から入力座標を計算
        inputX = x * 2
        inputY = y * 2
        
        block00 = flowData.getBlock(0, inputX           , inputY)
        block10 = flowData.getBlock(0, inputX+BLOCK_SIZE, inputY)
        block01 = flowData.getBlock(0, inputX           , inputY+BLOCK_SIZE)
        block11 = flowData.getBlock(0, inputX+BLOCK_SIZE, inputY+BLOCK_SIZE)
        if not block00 or block00.data is None:
            return None
        
        # ベイヤーパターンを取得
        bayer_pattern = flowData.headers.get('bayer_pattern', 'RGGB')
        
        # 2x2ブロックから各プレーンを抽出
        data00 = block00.data
        data10 = block10.data if block10 else None
        data01 = block01.data if block01 else None
        data11 = block11.data if block11 else None
        height00, width00 = data00.shape
        height10, width10 = data10.shape if data10 is not None else (0, 0)
        height01, width01 = data01.shape if data01 is not None else (0, 0)
        height11, width11 = data11.shape if data11 is not None else (0, 0)
        
        # 出力サイズ（半分）
        outHeight = (height00+height01) // 2
        outWidth = (width00+width10) // 2
        
        result = nh.nans((outHeight, outWidth))
        
        # ベイヤーパターンに応じてマスクを作成     [   R      G1      B       G2  ]
        if   bayer_pattern == 'RGGB': offsets = [(0, 0), (0, 1), (1, 1), (1, 0)]
        elif bayer_pattern == 'GRBG': offsets = [(0, 1), (0, 0), (1, 0), (1, 1)]
        elif bayer_pattern == 'GBRG': offsets = [(1, 0), (1, 1), (0, 1), (0, 0)]
        elif bayer_pattern == 'BGGR': offsets = [(1, 1), (1, 0), (0, 0), (0, 1)]
        else                        : offsets = [(0, 0), (0, 1), (1, 1), (1, 0)] # デフォルト RGGB
        
        # 指定プレーンのオフセット
        if planeIndex < len(offsets):
            dy, dx = offsets[planeIndex]
            
            # numpyスライシングで効率化
            if data00 is not None: result[0:height00//2                        , 0:width00//2                      ] = data00[dy::2, dx::2]
            if data10 is not None: result[0:height10//2                        ,   width00//2:width00//2+width10//2] = data10[dy::2, dx::2]
            if data01 is not None: result[  height00//2:height00//2+height01//2, 0:width01//2                      ] = data01[dy::2, dx::2]
            if data11 is not None: result[  height10//2:height10//2+height11//2,   width01//2:width01//2+width11//2] = data11[dy::2, dx::2]
        
        return DataBlock(result, planeIndex, x, y)
    
    @staticmethod
    def _computeHeaders(lazyFlowData):
        """ヘッダー情報を計算"""
        sourceHeaders = lazyFlowData.sourceFlowData.headers
        return {
            'mode'  : 'RGBG',
            'planes': ['R', 'G1', 'B', 'G2'],
            'width' : sourceHeaders['width'] // 2,
            'height': sourceHeaders['height'] // 2
        }
