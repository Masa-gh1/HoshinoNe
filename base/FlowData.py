'''
FlowData class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import uuid
import sys
from tkinter import messagebox

from config import BLOCK_SIZE
from .Constants import CachePolicy
from .DataBlock import DataBlock
from .CacheManager import CacheManager
from utils import numpy_helpers as nh

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

class FlowData:
    def __init__(self, headers={}):
        self.instanceId = str(uuid.uuid4())
        
        self.cachePolicy = CachePolicy.PERSISTENT # キャッシュポリシー（元データはPERSISTENT固定）
        self.headers = headers
        self._dimensions = (0, 0)
        self._maxValue = None
        self._minValue = None
        self._percentileCache = {} # パーセンタイルキャッシュ
        self._histogramCache = {}  # ヒストグラムキャッシュ
        self._highResHistCache = None  # 高解像度ヒストグラムキャッシュ
        self._existingBlocks = set()  # 保存済みブロックの記録 上書きチェックなどに使用する
        
        if not NUMPY_AVAILABLE:
            messagebox.showerror("FlowData エラー", "numpyライブラリがインストールされていません。\npip install numpy でインストールしてください。")
            return
    
    def __del__(self):
        try:
            # キャッシュから自身のエントリを削除
            CacheManager.clearByInstanceId(self.instanceId)
        except (ImportError, AttributeError) as e:
            print(f"Warning cleanup: {e}", file=sys.stderr)

    def _updateStatistics(self, planeIndex, x, y, blockData):
        """統計情報を更新"""
        # ブロック上書き検出
        blockKey = (planeIndex, x, y)
        if blockKey in self._existingBlocks:
            if CachePolicy.PERSISTENT == self.cachePolicy: # 永続なので再setは発生しない見込み
                print(f"Warning: Block overwrite detected at plane={planeIndex}, x={x}, y={y}", file=sys.stderr)
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
                self._highResHistCache = None
    
    def setDimensions(self, width, height):
        """次元を設定"""
        self._dimensions = (width, height)
    
    def getType(self):
        """型を取得"""
        if 'type' in self.headers:
            return self.headers['type']
        return 'matrix'
    
    def getMode(self):
        """モードを取得"""
        if 'mode' in self.headers:
            return self.headers['mode']
        # プレーン数から推定
        planeCount = self.getPlaneCount()
        if planeCount == 3:
            return 'RGB'
        elif planeCount == 4:
            return 'RGBG'
        elif planeCount == 1:
            return 'L'
        else:
            return None
    
    def getDimensions(self):
        """次元を取得 (width, height)"""
        return self._dimensions
    
    def getPlaneCount(self):
        """プレーン数を取得"""
        if 'planes' in self.headers:
            return len(self.headers['planes'])
        # フォールバック: 次元数から推定
        return None
    
    def getArea(self):
        """面積を取得"""
        width, height = self.getDimensions()
        return (width*height)
    
    def getBlock(self, planeIndex, x, y):
        """指定位置からブロックを取得"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if planeIndex >= planeCount or x >= width or y >= height:
            return None
        
        # 遅延ロード用のDataBlockを作成
        block = DataBlock(None, planeIndex, x, y)
        block.cachePolicy = self.cachePolicy
        block.blockId = (self.instanceId, planeIndex, x, y)
        return block
    
    def getBlockCount(self):
        """ブロックの総数を取得"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if planeCount == 0:
            return 0
        
        blocksX = (width + BLOCK_SIZE - 1) // BLOCK_SIZE
        blocksY = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
        
        return planeCount * blocksX * blocksY
    
    def iterateBlocks(self):
        """全ブロックを順次取得するジェネレータ"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if planeCount == 0:
            return
        
        for planeIdx in range(planeCount):
            for y in range(0, height, BLOCK_SIZE):
                for x in range(0, width, BLOCK_SIZE):
                    block = self.getBlock(planeIdx, x, y)
                    if block:
                        yield block
    
    def setBlock(self, dataBlock):
        """ブロックデータを保存"""
        dataBlock.blockId = (self.instanceId, dataBlock.planeIndex, dataBlock.x, dataBlock.y)
        dataBlock.cachePolicy = self.cachePolicy
        
        # numpy配列として正規化
        if isinstance(dataBlock.data, list):
            arr = nh.array(dataBlock.data)
        elif np.iscomplexobj(dataBlock.data):
            # 複素数型は複素数型を保持
            arr = dataBlock.data
        elif dataBlock.data.dtype != nh.BDTYPE:
            arr = dataBlock.data.astype(nh.BDTYPE)
        else:
            arr = dataBlock.data
        
        dataBlock.data = arr
    
        # 統計情報更新
        self._updateStatistics(dataBlock.planeIndex, dataBlock.x, dataBlock.y, arr)
        
    def getMaxValue(self):
        """最大値を取得"""
        return self._maxValue
    
    def getMinValue(self):
        """最小値を取得"""
        return self._minValue
    
    def _getHighResHistograms(self):
        """高解像度ヒストグラムを取得（中間生成物キャッシュ）"""
        if self._highResHistCache:
            return self._highResHistCache
        
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        
        planeHistograms = []
        for planeIndex in range(planeCount):
            blockArrays = []
            for y in range(0, height, BLOCK_SIZE):
                for x in range(0, width, BLOCK_SIZE):
                    block = self.getBlock(planeIndex, x, y)
                    if block and block.data is not None:
                        blockArrays.append(block.data.flatten())
            
            if not blockArrays:
                planeHistograms.append(None)
            else:
                planeData = np.concatenate(blockArrays)
                validData = planeData[~np.isnan(planeData)]

                if len(validData) <= 0:
                    planeHistograms.append(None)
                else:
                    min_val, max_val = np.min(validData), np.max(validData)
                    
                    # linear bins
                    linear_edges = np.linspace(min_val, max_val, 1025)  # 1024ビン
                    
                    # log bins (getHistogram と同じ正規化をする)
                    log_edges = np.logspace(np.log10(0.1), np.log10(1.0), 1025)  # 1024ビン
                    scale = 0.9 / (max_val - min_val)
                    offset = -min_val + 0.1 / scale
                    log_edges = log_edges / scale - offset
                    
                    # マージして重複除去
                    merged_edges = np.unique(np.concatenate([linear_edges, log_edges]))
                    
                    # histogram計算はこの一回だけ
                    hist, _ = np.histogram(validData, bins=merged_edges)
                    
                    planeHistograms.append({
                        'min': min_val,
                        'max': max_val,
                        'total_samples': len(validData),
                        'hist': hist,
                        'edges': merged_edges
                    })
        
        self._highResHistCache = planeHistograms
        return planeHistograms
    
    def getPercentile(self, percentile):
        """指定したパーセンタイル値を取得（キャッシュ付き）"""
        if percentile in self._percentileCache:
            return self._percentileCache[percentile]
        
        # 高解像度ヒストグラムで全プレーンを取得
        planeCount = self.getPlaneCount()
        planeHistograms = self._getHighResHistograms()
        
        if planeHistograms and any(hist is not None for hist in planeHistograms):
            # 全プレーンのビン中央値を収集
            all_centers = []
            all_counts = []
            
            for hist_data in planeHistograms:
                if hist_data is not None:
                    centers = (hist_data['edges'][:-1] + hist_data['edges'][1:]) / 2
                    all_centers.append(centers)
                    all_counts.append(hist_data['hist'])
            
            # 結合
            combined_centers = np.concatenate(all_centers)
            combined_counts = np.concatenate(all_counts)
            
            # ソートしてパーセンタイル計算
            sort_idx = np.argsort(combined_centers)
            sorted_centers = combined_centers[sort_idx]
            sorted_counts = combined_counts[sort_idx]
            
            total_samples = np.sum(sorted_counts)
            if total_samples > 0:
                target_count = (percentile / 100.0) * total_samples
                cumsum = np.cumsum(sorted_counts)
                
                bin_idx = np.searchsorted(cumsum, target_count)
                bin_idx = min(bin_idx, len(sorted_centers) - 1)
                
                result = sorted_centers[bin_idx]
                self._percentileCache[percentile] = result
                return result
        return 0.0
    
    def getHistogram(self, bins=256, log_scale=False):
        """プレーン別ヒストグラムを取得（キャッシュ付き）"""
        cacheKey = (bins, log_scale)
        if cacheKey in self._histogramCache:
            return self._histogramCache[cacheKey]
        
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        
        # 高解像度ヒストグラムでプレーン別ヒストグラムを計算
        planeHighResHists = self._getHighResHistograms()
        
        planeHistograms = []
        for planeIdx in range(planeCount):
            if(   planeIdx < len(planeHighResHists)
              and planeHighResHists[planeIdx] is not None
              and planeHighResHists[planeIdx]['min'] < planeHighResHists[planeIdx]['max']
              ):
                hist_data = planeHighResHists[planeIdx]
                
                range_min = hist_data['min']
                range_max = hist_data['max']
                
                # 目標ビンエッジを作成
                if log_scale:
                    bin_edges = np.logspace(np.log10(0.1), np.log10(1.0), bins + 1)
                    scale = 0.9 / (range_max - range_min)
                    offset = -range_min + 0.1 / scale
                    bin_edges = bin_edges / scale - offset
                else:
                    bin_edges = np.linspace(range_min, range_max, bins + 1)
                
                # 高解像度ヒストグラムを目標解像度にリサンプリング(近似)
                source_edges = hist_data['edges']
                source_counts = hist_data['hist']
                bin_indices = np.searchsorted(bin_edges[1:], source_edges[:-1])
                resampled_hist = np.zeros(len(bin_edges) - 1, dtype=int)
                np.add.at(resampled_hist, bin_indices, source_counts)
                
                planeHistograms.append({
                    'counts': resampled_hist.astype(int),
                    'bin_edges': bin_edges,
                    'total_samples': hist_data['total_samples']
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
