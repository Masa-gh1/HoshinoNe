'''
LazySystem - 遅延評価システム統合

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
import uuid
from collections import UserDict

from config import BLOCK_SIZE
from .Constants import CachePolicy
from .FlowData import FlowData
from .DataBlock import DataBlock
from utils import numpy_helpers as nh

class LazyFlowData(FlowData):
    """遅延評価FlowData"""
    __slots__ = ('cachePolicy'        ,
                 'sourceFlowData'     ,
                 'operation'          ,
                 'instanceId'         ,
                 '_headerComputeFuncs',
                 'headers'            ,
                )
    
    def __init__(self, sourceFlowData):
        super().__init__(None)
        self.cachePolicy = CachePolicy.CALCULABLE # キャッシュポリシー（遅延評価データはCALCULABLE固定）
        self.sourceFlowData = sourceFlowData
        self.operation = None
        self.instanceId = str(uuid.uuid4())
        self._headerComputeFuncs = {}
        self.headers = LazyHeadersDict(self)
        self.setDimensions(*sourceFlowData.getDimensions())
    
    def addOperation(self, func, *args, **kwargs):
        """新しい操作を追加"""
        operation = LazyOperation(func, *args, **kwargs)
        self.operation = operation
        return operation
    
    def addHeaderOperation(self, key, func, *args, **kwargs):
        """header操作関数を追加"""
        operation = LazyHeaderOperation(func, *args, **kwargs)
        self.headers[key] = operation
        return operation
    
    def getBlock(self, planeIndex, x, y):
        """指定位置からブロックを取得（遅延評価）"""
        block = super().getBlock(planeIndex, x, y)
        if not block:
            return None
        elif block.isValid():
            return block
        else:
            # 計算済みの block が無いので遅延評価を開始
            block = self.operation( self.sourceFlowData, planeIndex, x, y)
            self.setBlock(block)
            return block
    
class LazyHeadersDict(UserDict):
    """遅延評価対応のheaders辞書"""
    
    def __init__(self, lazyFlowData):
        super().__init__(lazyFlowData.sourceFlowData.headers)
        self._lazyFlowData = lazyFlowData
    
    def __getitem__(self, key):
        if key in self.data:
            value = self.data[key]
            if isinstance(value, LazyHeaderOperation):
                lazyResult = value(self._lazyFlowData)
                self.data.update(lazyResult)
                value = self.data[key]
            return value
    
class LazyOperation:
    """遅延実行される単一操作"""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def __call__(self, flowData, planeIndex, x, y):
        return self.func(flowData, planeIndex, x, y, *self.args, **self.kwargs)

class LazyHeaderOperation:
    """遅延実行されるヘッダー操作"""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def __call__(self, lazyFlowData):
        return self.func(lazyFlowData, *self.args, **self.kwargs)

##### 以下サンプル実装
class LazyOperations:
    """遅延操作関数群"""
    
    @staticmethod
    def offsetDisplayLevels(lazyFlowData, offsetValue):
        """オフセット加算後のdisplay_levelsを計算"""
        sourceHeaders = lazyFlowData.sourceFlowData.headers
        if not sourceHeaders or 'display_levels' not in sourceHeaders:
            return None
        
        inputLevels = sourceHeaders['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        return {
            'min': inputMin + offsetValue,
            'exclusive_upper': inputMax + offsetValue
        }
    
    @staticmethod
    def scaleDisplayLevels(lazyFlowData, scaleValue):
        """スケール乗算後のdisplay_levelsを計算"""
        sourceHeaders = lazyFlowData.sourceFlowData.headers
        if not sourceHeaders or 'display_levels' not in sourceHeaders:
            return None
        
        inputLevels = sourceHeaders['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        # スケール乗算の場合は範囲が複雑になる
        products = [inputMin * scaleValue, inputMax * scaleValue]
        
        return {
            'min': min(products),
            'exclusive_upper': max(products)
        }
    
    @staticmethod
    def transform(flowData, planeIndex, x, y, transformMatrix):
        """アフィン変換"""
        import cv2
        
        # 出力ブロックの中心位置
        outputCenterX = x + BLOCK_SIZE // 2
        outputCenterY = y + BLOCK_SIZE // 2
        
        # 逆変換行列で入力位置を計算
        matrix2x3 = transformMatrix[:2, :] if transformMatrix.shape == (3, 3) else transformMatrix
        invMatrix = cv2.invertAffineTransform(matrix2x3)
        
        # 入力中心位置を計算
        inputCenter = np.dot(invMatrix[:, :2], [outputCenterX, outputCenterY]) + invMatrix[:, 2]
        inputCenterX, inputCenterY = int(inputCenter[0]), int(inputCenter[1])
        
        # 入力中心位置からブロック座標を計算
        inputBlockX = inputCenterX // BLOCK_SIZE
        inputBlockY = inputCenterY // BLOCK_SIZE
        
        # 入力位置を中心とした拡張データを取得
        extended_data = LazyOperations._getExtendedBlockData(flowData, planeIndex, inputBlockX, inputBlockY)
        
        # 変換実行
        transformed_extended = cv2.warpAffine(
            extended_data, matrix2x3,
            extended_data.shape[::-1],
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=np.nan
        )
        
        # 出力ブロックサイズに切り出し
        margin = (extended_data.shape[0] - BLOCK_SIZE) // 2
        result = transformed_extended[margin:margin+BLOCK_SIZE, margin:margin+BLOCK_SIZE]
        
        return DataBlock(result, planeIndex, x, y)
    
    @staticmethod
    def _getExtendedBlockData(flowData, planeIndex, x, y, margin=64):
        """隣接ブロックを含む拡張データを取得"""
        blockX = x // BLOCK_SIZE
        blockY = y // BLOCK_SIZE
        extendedSize = BLOCK_SIZE + 2 * margin
        extended_data = nh.nans((extendedSize, extendedSize))
        
        # 3x3の隣接ブロックを取得
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                neighborX = (blockX + dx) * BLOCK_SIZE
                neighborY = (blockY + dy) * BLOCK_SIZE
                
                try:
                    neighborBlock = flowData.getBlock(planeIndex, neighborX, neighborY)
                    if neighborBlock and neighborBlock.data is not None:
                        # 隣接ブロックを適切な位置に配置
                        startY = margin + dy * BLOCK_SIZE
                        endY = startY + BLOCK_SIZE
                        startX = margin + dx * BLOCK_SIZE
                        endX = startX + BLOCK_SIZE
                        
                        if 0 <= startY < extendedSize and 0 <= startX < extendedSize:
                            extended_data[max(0, startY):min(extendedSize, endY),
                                        max(0, startX):min(extendedSize, endX)] = neighborBlock.data
                except:
                    pass
        
        return extended_data
    
    @staticmethod
    def scale(flowData, planeIndex, x, y, scaleValue):
        """スケール変換"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block or block.data is None:
            return None
        return DataBlock(block.data * scaleValue, planeIndex, x, y)
    
    @staticmethod
    def offset(flowData, planeIndex, x, y, offsetValue):
        """オフセット加算"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block or block.data is None:
            return None
        return DataBlock(block.data + offsetValue, planeIndex, x, y)