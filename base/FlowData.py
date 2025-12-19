'''
FlowData class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import uuid
from tkinter import messagebox
from config import BLOCK_SIZE
from .DataBlock import DataBlock
from main.CacheManager import CacheManager

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

class FlowData:
    def __init__(self, headers={}):
        self.instanceId = str(uuid.uuid4())
        
        self.cachePolicy = CacheManager.PERSISTENT # キャッシュポリシー（元データはPERSISTENT固定）
        self.headers = headers
        self._dimensions = (0, 0)
        self._blockSize = BLOCK_SIZE
        self._maxValue = None
        self._minValue = None
        self._percentileCache = {} # パーセンタイルキャッシュ
        self._histogramCache = {}  # ヒストグラムキャッシュ
        self._existingBlocks = set()  # 保存済みブロックの記録 上書きチェックなどに使用する
        
        if not NUMPY_AVAILABLE:
            messagebox.showerror("FlowData エラー", "numpyライブラリがインストールされていません。\npip install numpy でインストールしてください。")
            return
    
    def __del__(self):
        try:
            # キャッシュから自身のエントリを削除
            CacheManager.clearByInstanceId(self.instanceId)
        except (ImportError, AttributeError):
            pass

    def _updateStatistics(self, planeIndex, x, y, blockData):
        """統計情報を更新"""
        # ブロック上書き検出
        blockKey = (planeIndex, x, y)
        if blockKey in self._existingBlocks:
            if CacheManager.PERSISTENT == self.cachePolicy: # 永続なので再setは発生しない見込み
                print(f"Warning: Block overwrite detected at plane={planeIndex}, x={x}, y={y}")
        else:
            self._existingBlocks.add(blockKey)
            
            # 最大値・最小値を更新し、キャッシュをクリア
            if 0 < blockData.size:
                blockMax = np.nanmax(blockData)
                blockMin = np.nanmin(blockData)
                
                if not np.isnan(blockMax) and (self._maxValue is None or blockMax > self._maxValue):
                    self._maxValue = blockMax
                if not np.isnan(blockMin) and (self._minValue is None or blockMin < self._minValue):
                    self._minValue = blockMin
                
                # データ更新時にキャッシュをクリア
                self._percentileCache.clear()
                self._histogramCache.clear()
    
    def setDimensions(self, width, height):
        """データの次元を設定"""
        self._dimensions = (width, height)
    
    def getType(self):
        """データの型を取得"""
        if 'type' in self.headers:
            return self.headers['type']
        return 'matrix'
    
    def getMode(self):
        """データのモードを取得"""
        if 'mode' in self.headers:
            return self.headers['mode']
        # プレーン数から推定
        planeCount = self.getPlaneCount()
        if planeCount == 3:
            return 'RGB'
        elif planeCount == 4:
            return 'RGGB'
        elif planeCount == 1:
            return 'L'
        else:
            return None
    
    def getDimensions(self):
        """データの次元を取得 (width, height)"""
        return self._dimensions
    
    def getPlaneCount(self):
        """プレーン数を取得"""
        if 'planes' in self.headers:
            return len(self.headers['planes'])
        # フォールバック: 次元数から推定
        return None
    
    def getArea(self):
        """データの面積を取得"""
        width, height = self.getDimensions()
        return (width*height)
    
    def getBlock(self, planeIndex, x, y):
        """指定位置からブロックを取得"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if planeIndex >= planeCount or x >= width or y >= height:
            return None
        
        # 遅延ロード用のDataBlockを作成
        block = DataBlock(planeIndex, x, y, None)
        block.cachePolicy = self.cachePolicy
        block.blockId = (self.instanceId, planeIndex, x, y)
        return block
    
    def getBlockCount(self):
        """ブロックの総数を取得"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if planeCount == 0:
            return 0
        
        blocksX = (width + self._blockSize - 1) // self._blockSize
        blocksY = (height + self._blockSize - 1) // self._blockSize
        
        return planeCount * blocksX * blocksY
    
    def iterateBlocks(self):
        """全ブロックを順次取得するジェネレータ"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if planeCount == 0:
            return
        
        for planeIdx in range(planeCount):
            for y in range(0, height, self._blockSize):
                for x in range(0, width, self._blockSize):
                    block = self.getBlock(planeIdx, x, y)
                    if block:
                        yield block
    
    def setBlock(self, dataBlock):
        """ブロックデータを保存"""
        dataBlock.flowData = self
        dataBlock.blockId = (self.instanceId, dataBlock.planeIndex, dataBlock.x, dataBlock.y)
        dataBlock.cachePolicy = self.cachePolicy
        
        # numpy配列として正規化
        if isinstance(dataBlock.data, list):
            arr = np.array(dataBlock.data, dtype=np.float64)
        else:
            arr = dataBlock.data
        
        dataBlock.data = arr
    
        # 統計情報更新
        self._updateStatistics(dataBlock.planeIndex, dataBlock.x, dataBlock.y, arr)
        
    def getMaxValue(self):
        """データの最大値を取得"""
        return self._maxValue
    
    def getMinValue(self):
        """データの最小値を取得"""
        return self._minValue
    
    def getPercentile(self, percentile):
        """指定したパーセンタイル値を取得（キャッシュ付き）"""
        if percentile in self._percentileCache:
            return self._percentileCache[percentile]
        
        # 全ピクセルでパーセンタイルを計算
        allValues = []
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        
        for planeIdx in range(min(planeCount, 3)):  # RGBのみ
            for blockY in range(0, height, self._blockSize):
                for blockX in range(0, width, self._blockSize):
                    block = self.getBlock(planeIdx, blockX, blockY)
                    if block and hasattr(block, 'data') and block.data is not None:
                        # 全ピクセルを使用
                        allValues.extend(block.data.flatten())
        
        if allValues:
            # NaN値を除外してパーセンタイル計算
            validValues = np.array(allValues)
            validValues = validValues[~np.isnan(validValues)]
            if len(validValues) > 0:
                result = np.percentile(validValues, percentile)
                self._percentileCache[percentile] = result
                return result
        return 0.0
    
    def getHistogram(self, bins=256, range_min=None, range_max=None, log_scale=False):
        """プレーン別ヒストグラムを取得（キャッシュ付き）"""
        cacheKey = (bins, range_min, range_max, log_scale)
        if cacheKey in self._histogramCache:
            return self._histogramCache[cacheKey]
        
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        
        # プレーン別にヒストグラムを計算
        planeHistograms = []
        for planeIdx in range(min(planeCount, 4)):
            planeValues = []
            for blockY in range(0, height, self._blockSize):
                for blockX in range(0, width, self._blockSize):
                    block = self.getBlock(planeIdx, blockX, blockY)
                    if block and hasattr(block, 'data') and block.data is not None:
                        planeValues.extend(block.data.flatten())
            
            if planeValues:
                planeValues = np.array(planeValues)
                # NaN値を除外して範囲計算
                validValues = planeValues[~np.isnan(planeValues)]
                if len(validValues) > 0:
                    if range_min is None:
                        range_min = np.min(validValues)
                    if range_max is None:
                        range_max = np.max(validValues)
                    planeValues = validValues
                else:
                    planeValues = []
                
                # 等比数列のビンを作成
                if log_scale:
                    bin_edges = np.logspace(np.log10(0.1), np.log10(1.0), bins + 1)
                    # 正規化パラメータ
                    scale = 0.9 / (range_max - range_min)
                    offset = -range_min + 0.1 / scale
                    # 正規化を戻す
                    bin_edges = bin_edges / scale - offset
                else:
                    bin_edges = np.linspace(range_min, range_max, bins + 1)
                
                if len(planeValues) > 0:
                    hist, _ = np.histogram(planeValues, bins=bin_edges)
                else:
                    hist = np.zeros(bins, dtype=int)
                planeHistograms.append({
                    'counts': hist.tolist(),
                    'bin_edges': bin_edges.tolist(),
                    'total_samples': len(planeValues)
                })
            else:
                planeHistograms.append({
                    'counts': [0] * bins,
                    'bin_edges': list(range(bins + 1)),
                    'total_samples': 0
                })
        
        result = {'planes': planeHistograms}
        self._histogramCache[cacheKey] = result
        return result
