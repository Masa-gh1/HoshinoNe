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
from .CacheManager import CacheManager

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

class FlowData:
    def __init__(self, headers=None):
        # インスタンス識別子
        self.instanceId = str(uuid.uuid4())
        
        # キャッシュポリシー（元データはPERSISTENT固定）
        self.cachePolicy = CacheManager.PERSISTENT
        self.headers = headers if headers is not None else {}
        self._dimensions = (0, 0)
        self._blockSize = BLOCK_SIZE
        self._maxValue = None
        self._minValue = None
        self._percentileCache = {}
        self._histogramCache = {}  # ヒストグラムキャッシュ
        self._existingBlocks = set()  # 保存済みブロックの記録
        
        if not NUMPY_AVAILABLE:
            messagebox.showerror("FlowData エラー", "numpyライブラリがインストールされていません。\npip install numpy でインストールしてください。")
            return
    
    def __del__(self):
        try:
            # 統一キャッシュから自身のエントリを削除
            CacheManager.clearByPolicy(self.cachePolicy, self.instanceId)
        except (ImportError, AttributeError):
            pass
    
    def _loadBlock(self, planeIndex, blockX, blockY):
        """指定ブロックを読み込み（統一キャッシュ使用）"""
        cacheKey = (self.instanceId, planeIndex, blockX, blockY)
        
        # 統一キャッシュから取得
        cachedData = CacheManager.get(cacheKey)
        if cachedData is not None:
            return cachedData
        
        # ディスクから読み込み
        return CacheManager.loadFromDisk(cacheKey)
    
    def _saveBlock(self, planeIndex, blockX, blockY, blockData):
        """指定ブロックをキャッシュに保存（統一キャッシュ使用）"""
        # ブロック上書き検出
        blockKey = (planeIndex, blockX, blockY)
        if blockKey in self._existingBlocks:
            print(f"Warning: Block overwrite detected at plane={planeIndex}, x={blockX}, y={blockY}")
        else:
            self._existingBlocks.add(blockKey)
        
        # numpy配列として正規化
        if isinstance(blockData, list):
            arr = np.array(blockData, dtype=np.float64)
        else:
            arr = blockData
        
        # 最大値・最小値を更新し、キャッシュをクリア（NaN除外）
        if arr.size > 0:
            blockMax = np.nanmax(arr)
            blockMin = np.nanmin(arr)
            
            if not np.isnan(blockMax) and (self._maxValue is None or blockMax > self._maxValue):
                self._maxValue = blockMax
            if not np.isnan(blockMin) and (self._minValue is None or blockMin < self._minValue):
                self._minValue = blockMin
            
            # データ更新時にキャッシュをクリア
            self._percentileCache.clear()
            self._histogramCache.clear()
        
        # 統一キャッシュに保存
        cacheKey = (self.instanceId, planeIndex, blockX, blockY)
        CacheManager.set(cacheKey, arr, self.cachePolicy)
    
    
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
        
        blockX = x // self._blockSize
        blockY = y // self._blockSize
        
        # 遅延ロード用のDataBlockを作成（データはNoneで初期化）
        return DataBlock(planeIndex, blockX * self._blockSize, blockY * self._blockSize, None, self)
    
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
        """ブロックデータを直接保存"""
        blockX = dataBlock.x // self._blockSize
        blockY = dataBlock.y // self._blockSize
        dataBlock.flowData = self
        
        self._saveBlock(dataBlock.planeIndex, blockX, blockY, dataBlock.data)
    
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
    
    # 古いキャッシュ実装を削除（CacheManagerに統合）
    
    @classmethod
    def getCacheStats(cls):
        """キャッシュ統計情報を取得（CacheManagerに委謗）"""
        from .CacheManager import CacheManager
        return CacheManager.getCacheStats()