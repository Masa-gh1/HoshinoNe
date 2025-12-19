'''
LazySystem - 遅延評価システム統合

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
import uuid
from .FlowData import FlowData
from .DataBlock import DataBlock
from .CacheManager import CacheManager
from collections import UserDict

class LazyFlowData(FlowData):
    """遅延評価FlowData"""
    
    def __init__(self, sourceFlowData, cachePolicy=CacheManager.LIGHT_CALC):
        super().__init__(None)
        self.cachePolicy = cachePolicy
        self.sourceFlowData = sourceFlowData
        self.operationChain = []
        self.instanceId = str(uuid.uuid4())
        self._headerComputeFuncs = {}
        self.headers = LazyHeadersDict(self, sourceFlowData.headers)
        self.setDimensions(*sourceFlowData.getDimensions())
    
    def addOperation(self, func, *args, **kwargs):
        """新しい操作を追加"""
        operation = LazyOperation(func, *args, **kwargs)
        self.operationChain.append(operation)
        return operation
    
    def addHeaderCompute(self, key, func, *args, **kwargs):
        """header計算関数を追加"""
        operation = LazyHeaderOperation(func, *args, **kwargs)
        self._headerComputeFuncs[key] = operation
        if key in self.headers:
            del self.headers[key]
        return operation
    
    def getBlock(self, planeIndex, x, y):
        """ブロック取得"""
        blockX, blockY = x // self._blockSize, y // self._blockSize
        cacheKey = (self.instanceId, planeIndex, blockX, blockY)
        
        cachedData = CacheManager.get(cacheKey)
        if cachedData is not None:
            return DataBlock(planeIndex, blockX * self._blockSize, blockY * self._blockSize, cachedData, self)
        
        resultBlock = self._executeChain(planeIndex, blockX, blockY)
        
        if resultBlock and resultBlock.data is not None:
            CacheManager.set(cacheKey, resultBlock.data, self.cachePolicy)
        
        return resultBlock
    
    def _executeChain(self, planeIndex, blockX, blockY):
        """操作チェーン実行"""
        currentFlowData = self.sourceFlowData
        
        for operation in self.operationChain:
            resultBlock = operation(currentFlowData, planeIndex, blockX, blockY)
            if resultBlock is None:
                return DataBlock(planeIndex, blockX * self._blockSize, blockY * self._blockSize, 
                               np.full((self._blockSize, self._blockSize), np.nan), self)
            
            if len(self.operationChain) > 1:
                tempFlowData = FlowData(currentFlowData.headers.copy())
                tempFlowData.setDimensions(*currentFlowData.getDimensions())
                tempFlowData.setBlock(resultBlock)
                currentFlowData = tempFlowData
        
        if resultBlock:
            resultBlock.flowData = self
        return resultBlock
    
    def getMinValue(self):
        """最小値を取得（遅延評価）"""
        minValue = None
        for block in self.iterateBlocks():
            if block and block.data is not None:
                blockMin = np.nanmin(block.data)
                if not np.isnan(blockMin):
                    minValue = blockMin if minValue is None else min(minValue, blockMin)
        return minValue
    
    def getMaxValue(self):
        """最大値を取得（遅延評価）"""
        maxValue = None
        for block in self.iterateBlocks():
            if block and block.data is not None:
                blockMax = np.nanmax(block.data)
                if not np.isnan(blockMax):
                    maxValue = blockMax if maxValue is None else max(maxValue, blockMax)
        return maxValue

class LazyHeadersDict(UserDict):
    """遅延評価対応のheaders辞書"""
    
    def __init__(self, lazyFlowData, initialHeaders=None):
        super().__init__(initialHeaders or {})
        self._lazyFlowData = lazyFlowData
    
    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        
        if key in self._lazyFlowData._headerComputeFuncs:
            operation = self._lazyFlowData._headerComputeFuncs[key]
            result = operation(self._lazyFlowData)
            
            if isinstance(result, dict):
                self.data.update(result)
                return self.data.get(key)
            else:
                self.data[key] = result
                return result
        
        # sourceFlowDataのheadersから取得を試行
        if hasattr(self._lazyFlowData, 'sourceFlowData') and self._lazyFlowData.sourceFlowData.headers:
            try:
                return self._lazyFlowData.sourceFlowData.headers[key]
            except KeyError:
                pass
        
        raise KeyError(key)
    
    def __contains__(self, key):
        return (key in self.data or 
                key in self._lazyFlowData._headerComputeFuncs or
                (hasattr(self._lazyFlowData, 'sourceFlowData') and 
                 self._lazyFlowData.sourceFlowData.headers and 
                 key in self._lazyFlowData.sourceFlowData.headers))
    
    def __delitem__(self, key):
        if key in self.data:
            del self.data[key]
        elif key in self._lazyFlowData._headerComputeFuncs:
            del self._lazyFlowData._headerComputeFuncs[key]
        else:
            raise KeyError(key)

class LazyOperation:
    """遅延実行される単一操作"""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def __call__(self, flowData, planeIndex, blockX, blockY):
        return self.func(flowData, planeIndex, blockX, blockY, *self.args, **self.kwargs)

class LazyHeaderOperation:
    """遅延実行されるヘッダー操作"""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def __call__(self, lazyFlowData):
        return self.func(*self.args, **self.kwargs)(lazyFlowData)

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
    def transform(flowData, planeIndex, blockX, blockY, transformMatrix, fillValue=np.nan):
        """アフィン変換"""
        import cv2
        
        blockSize = flowData._blockSize
        
        # 出力ブロックの中心位置
        outputCenterX = blockX * blockSize + blockSize // 2
        outputCenterY = blockY * blockSize + blockSize // 2
        
        # 逆変換行列で入力位置を計算
        matrix2x3 = transformMatrix[:2, :] if transformMatrix.shape == (3, 3) else transformMatrix
        invMatrix = cv2.invertAffineTransform(matrix2x3)
        
        # 入力中心位置を計算
        inputCenter = np.dot(invMatrix[:, :2], [outputCenterX, outputCenterY]) + invMatrix[:, 2]
        inputCenterX, inputCenterY = int(inputCenter[0]), int(inputCenter[1])
        
        # 入力中心位置からブロック座標を計算
        inputBlockX = inputCenterX // blockSize
        inputBlockY = inputCenterY // blockSize
        
        # 入力位置を中心とした拡張データを取得
        extended_data = LazyOperations._getExtendedBlockData(flowData, planeIndex, inputBlockX, inputBlockY)
        
        # 変換実行
        transformed_extended = cv2.warpAffine(
            extended_data.astype(np.float32), matrix2x3,
            extended_data.shape[::-1],
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=fillValue
        )
        
        # 出力ブロックサイズに切り出し
        margin = (extended_data.shape[0] - blockSize) // 2
        result = transformed_extended[margin:margin+blockSize, margin:margin+blockSize]
        
        return DataBlock(planeIndex, blockX * blockSize, blockY * blockSize, result.astype(np.float64))
    
    @staticmethod
    def _getExtendedBlockData(flowData, planeIndex, blockX, blockY, margin=64):
        """隣接ブロックを含む拡張データを取得"""
        blockSize = flowData._blockSize
        extendedSize = blockSize + 2 * margin
        extended_data = np.full((extendedSize, extendedSize), np.nan, dtype=np.float64)
        
        # 3x3の隣接ブロックを取得
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                neighborBlockX = blockX + dx
                neighborBlockY = blockY + dy
                neighborX = neighborBlockX * blockSize
                neighborY = neighborBlockY * blockSize
                
                try:
                    neighborBlock = flowData.getBlock(planeIndex, neighborX, neighborY)
                    if neighborBlock and neighborBlock.data is not None:
                        # 隣接ブロックを適切な位置に配置
                        startY = margin + dy * blockSize
                        endY = startY + blockSize
                        startX = margin + dx * blockSize
                        endX = startX + blockSize
                        
                        if 0 <= startY < extendedSize and 0 <= startX < extendedSize:
                            extended_data[max(0, startY):min(extendedSize, endY),
                                        max(0, startX):min(extendedSize, endX)] = neighborBlock.data
                except:
                    pass
        
        return extended_data
    
    @staticmethod
    def scale(flowData, planeIndex, blockX, blockY, factor):
        """スケール変換"""
        block = flowData.getBlock(planeIndex, blockX * flowData._blockSize, blockY * flowData._blockSize)
        if not block or block.data is None:
            return None
        return DataBlock(planeIndex, blockX * flowData._blockSize, blockY * flowData._blockSize, block.data * factor)
    
    @staticmethod
    def offset(flowData, planeIndex, blockX, blockY, offsetValue):
        """オフセット加算"""
        block = flowData.getBlock(planeIndex, blockX * flowData._blockSize, blockY * flowData._blockSize)
        if not block or block.data is None:
            return None
        return DataBlock(planeIndex, blockX * flowData._blockSize, blockY * flowData._blockSize, block.data + offsetValue)