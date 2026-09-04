'''
FlowData class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING, Iterator

import uuid
import threading
from tkinter import messagebox

from config import BLOCK_SIZE
from .Constants import CachePolicy
from .CacheManager import CacheManager
from utils.Debug import Debug

if TYPE_CHECKING:
    import numpy as np
    from .DataBlock import DataBlock

class FlowData:
    """ノードの実行結果を保存する"""
    __slots__ = ('instanceId'       ,
                 'cachePolicy'      ,
                 'headers'          ,
                 '_dimensions'      ,
                 '_variableType'    ,
                 '_maxValue'        , 
                 '_minValue'        ,
                 '_percentileCache' ,
                 '_histogramCache'  ,
                 '_highResHistCache',
                 '_existingBlocks'  ,
                 '_lock'            ,
                )
    def __init__(self, headers={}):
        self.instanceId = str(uuid.uuid4())
        
        self.cachePolicy = CachePolicy.PERSISTENT # キャッシュポリシー（元データはPERSISTENT固定）
        self.headers = headers
        self._dimensions = (0, 0)
        self._variableType = None

        self._maxValue = None
        self._minValue = None
        self._percentileCache  = {}   # パーセンタイルキャッシュ
        self._histogramCache   = {}   # ヒストグラムキャッシュ
        self._highResHistCache = {}   # 高解像度ヒストグラムキャッシュ
        self._existingBlocks   = None # 保存済みブロックの記録 上書きチェックなどに使用する
        self._lock             = threading.Lock()
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("numpy"):
            raise ImportError("ライブラリ numpy がインストールされていません。\npip install numpy でインストールしてください。")  
    
    def __del__(self):
        try:
            # キャッシュから自身のエントリを削除
            CacheManager.clearByPartialKey(self.instanceId)
        except Exception as e:
            Debug.log(type(self).__name__, "Warning: cleanup", e)

    def setDimensions(self, width, height):
        """次元を設定"""
        self._dimensions = (width, height)
    
    def getType(self) -> str:
        """型を取得"""
        if 'type' in self.headers:
            return self.headers['type']
        return 'table'
    
    def getMode(self) -> str:
        """モードを取得"""
        if 'mode' in self.headers:
            return self.headers['mode']
        else:
            return None
    
    def getPlaneCount(self) -> int:
        """プレーン数を取得"""
        if 'planes' in self.headers:
            return len(self.headers['planes'])
        else:
            return None
    
    def getDimensions(self) -> tuple[int, int]:
        """次元を取得 (width, height)"""
        return self._dimensions
    
    def getVariableType(self) -> np.dtype:
        """データ型を取得"""
        if self._variableType is None:
            self.getBlock(0,0,0).data
        return self._variableType

    def getArea(self) -> int:
        """面積を取得"""
        width, height = self.getDimensions()
        return (width*height)
    
    def getBlock(self, planeIndex:int, x:int, y:int) -> DataBlock:
        """指定位置からブロックを取得"""
        from .DataBlock import DataBlock
        
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if(  planeIndex < 0 or planeCount <= planeIndex
          or x          < 0 or width      <= x
          or y          < 0 or height     <= y
          ):
            # 範囲外なので None
            return None
        
        if(  self._existingBlocks is None
          or not self._existingBlocks[planeIndex, y//BLOCK_SIZE, x//BLOCK_SIZE]
          ):
            # 未設定なので all nan
            from utils import numpy_helpers as nh
            from base import DataBlock
            w = min(BLOCK_SIZE, width-x)
            h = min(BLOCK_SIZE, height-y)
            return DataBlock(nh.nans((h, w)), planeIndex, x, y)
        
        # 遅延ロード用のDataBlockを作成
        block = DataBlock(None, planeIndex, x, y)
        block.cachePolicy = self.cachePolicy
        block.blockId = f"{self.instanceId}:{planeIndex}:{x}:{y}"
        return block
    
    def getBlockCount(self) -> int:
        """ブロックの総数を取得"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if 0 == planeCount:
            return 0
        
        blocksX = (width  + BLOCK_SIZE - 1) // BLOCK_SIZE
        blocksY = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
        
        return planeCount * blocksX * blocksY
    
    def iterateBlocks(self, planeIndex:int=None) -> Iterator[DataBlock]:
        """全ブロックを順次取得するジェネレータ"""
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        if 0 == planeCount:
            return None
        
        # Z階数曲線でブロックを返す
        from utils.order import zOrderGenerator
        if planeIndex is None:
            for x, y in zOrderGenerator(0, 0, width, height, BLOCK_SIZE, BLOCK_SIZE):
                for planeIndex in range(planeCount):
                    block = self.getBlock(planeIndex, x, y)
                    if block:
                        yield block
        else:
            for x, y in zOrderGenerator(0, 0, width, height, BLOCK_SIZE, BLOCK_SIZE):
                block = self.getBlock(planeIndex, x, y)
                if block:
                    yield block
    
    def setBlock(self, dataBlock:DataBlock):
        """ブロックデータを保存"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        # numpy配列として正規化
        data = dataBlock.data
        if isinstance(data, list):
            if np.iscomplexobj(data):
                # 複素数
                data = np.array(data, dtype=nh.BDCOMPLEX)
            else:
                # 実数
                data = nh.array(data)
        else:
            if np.iscomplexobj(data):
                # 複素数
                if data.dtype != nh.BDCOMPLEX:
                    data = data.astype(nh.BDCOMPLEX)
                else:
                    data = data
            else:
                # 実数
                if data.dtype != nh.BDTYPE:
                    data = data.astype(nh.BDTYPE)
                else:
                    data = data
        
        # DataBlock を再利用
        dataBlock.blockId = f"{self.instanceId}:{dataBlock.planeIndex}:{dataBlock.x}:{dataBlock.y}"
        dataBlock.cachePolicy = self.cachePolicy
        dataBlock.data = data
    
        # 統計情報更新
        self._updateStatistics(dataBlock)
        
    def _updateStatistics(self, dataBlock:DataBlock):
        """統計情報を更新"""
        import numpy as np
        
        if self._existingBlocks is None:
            with self._lock:
                if self._existingBlocks is None:
                    planeCount = self.getPlaneCount()
                    width, height = self._dimensions
                    blockW = (width  + BLOCK_SIZE - 1) // BLOCK_SIZE
                    blockH = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
                    self._existingBlocks = np.zeros((planeCount, blockH, blockW), dtype=bool)
            
        planeIndex = dataBlock.planeIndex
        x = dataBlock.x
        y = dataBlock.y
        blockX = x // BLOCK_SIZE
        blockY = y // BLOCK_SIZE

        if self._existingBlocks[planeIndex, blockY, blockX]:
            # ブロック上書き検出
            if CachePolicy.PERSISTENT == self.cachePolicy: # 永続なので再setは発生しない見込み
                from utils.Debug import Debug
                Debug.log(type(self).__name__, f"Warning: Block overwrite detected at plane={planeIndex}, x={x}, y={y}")
        elif not self._variableType is None and self._variableType != dataBlock.data.dtype:
            # 型違い検出
            from utils.Debug import Debug
            Debug.log(type(self).__name__, f"Warning: Block type mismatch at plane={planeIndex}, x={x}, y={y}")
        else:
            self._existingBlocks[planeIndex, blockY, blockX] = True
            data = dataBlock.data
            self._variableType = data.dtype
            if 0 < data.size and not np.isnan(data).all():
                # 最大値・最小値を更新し、キャッシュをクリア
                if np.iscomplexobj(data):
                    blockMax = np.nanmax(np.abs(data))
                    blockMin = np.nanmin(np.abs(data))
                else:
                    blockMax = np.nanmax(data)
                    blockMin = np.nanmin(data)
                
                with self._lock:
                    if self._maxValue is None or self._maxValue < blockMax:
                        self._maxValue = blockMax
                    if self._minValue is None or blockMin < self._minValue:
                        self._minValue = blockMin
                    
                    # データ更新時にキャッシュをクリア
                    self._percentileCache.clear()
                    self._histogramCache.clear()
                    self._highResHistCache.clear()
    
    def getMaxValue(self) -> float:
        """最大値を取得"""
        return self._maxValue
    
    def getMinValue(self) -> float:
        """最小値を取得"""
        return self._minValue
    
    def _getHighResHistograms(self, bins=1024) -> list[dict]:
        """高解像度ヒストグラム(不等間隔)を取得（キャッシュ用の中間生成物）"""
        import numpy as np
        from utils import numpy_helpers as nh

        if bins in self._highResHistCache:
            return self._highResHistCache[bins]
        
        planeCount = self.getPlaneCount()
        
        planeHistograms = []

        for planeIndex in range(planeCount):
            blockArrays = []
            for block in self.iterateBlocks(planeIndex):
                blockArrays.append(block.data.ravel())
            
            if not blockArrays:
                planeHistograms.append(None)
            else:
                planeData = np.concatenate(blockArrays)
                validData = planeData[~np.isnan(planeData)]
                if np.iscomplexobj(validData):
                    validData = np.abs(validData)
                sortedData = np.sort(validData)

                if len(sortedData) <= 0:
                    planeHistograms.append(None)
                else:
                    minVal = sortedData[0]
                    maxVal = sortedData[-1]
                    minEdge = minVal
                    maxEdge = maxVal
                    
                    while minEdge < maxEdge:
                        # linear bins
                        linear_edges = np.linspace(minEdge, maxEdge, bins+1)
                        
                        # log bins (getHistogram と同じ正規化をする)
                        log_edges = np.logspace(np.log10(0.1), np.log10(1.0), bins+1)
                        scale = 0.9 / (maxEdge - minEdge)
                        offset = -minEdge + 0.1 / scale
                        log_edges = log_edges / scale - offset
                        
                        newMinEdge = minEdge
                        newMaxEdge = maxEdge
                        
                        # log_edges の先頭から連続する空ビン(1以下)の最後を探す
                        log_indices = np.searchsorted(sortedData, log_edges)
                        log_diffs = np.diff(log_indices)
                        non_empty = np.where(log_diffs > 1)[0]
                        if 0 < len(non_empty) and 0 < non_empty[0]:
                            newMinEdge = log_edges[non_empty[0]]
                        
                        # linear_edges の末尾から連続する空ビン(1以下)の最初を探す
                        linear_indices = np.searchsorted(sortedData, linear_edges)
                        linear_diffs = np.diff(linear_indices)
                        non_empty = np.where(linear_diffs > 1)[0]
                        if 0 < len(non_empty) and non_empty[-1] < len(linear_diffs) - 1:
                            newMaxEdge = linear_edges[non_empty[-1] + 1]
                        
                        if minEdge < newMinEdge or newMaxEdge < maxEdge:
                            minEdge = newMinEdge
                            maxEdge = newMaxEdge
                        else:
                            break
                    
                    if minEdge < maxEdge:
                        # マージして重複除去
                        merged_edges = np.unique(np.concatenate([[minVal,maxVal], linear_edges, log_edges]))

                        # histogram計算はこの一回だけ
                        bin_counts, _ = np.histogram(validData, bins=merged_edges)
                    
                        planeHistograms.append({
                            'min': minVal,
                            'max': maxVal,
                            'total_samples': len(validData),
                            'bin_counts': bin_counts,
                            'bin_edges': merged_edges
                        })
                    else:
                        planeHistograms.append({
                            'min': minVal,
                            'max': maxVal,
                            'total_samples': len(validData),
                            'bin_counts': nh.array([len(validData)]),
                            'bin_edges': nh.array([minVal,maxEdge])
                        })

        
        self._highResHistCache[bins] = planeHistograms
        return planeHistograms
    
    def getModeValue(self) -> float:
        """最頻値を取得（全プレーン統合）"""
        import numpy as np
        
        planeHistograms = self._getHighResHistograms()
        
        if not planeHistograms or not any(hist is not None for hist in planeHistograms):
            return 0.0
        
        # 全プレーンで最大カウントのビンを探す
        max_count = 0
        mode_value = 0.0
        
        for hist_data in planeHistograms:
            if(   not hist_data is None
              and 0 < hist_data['bin_counts'].size
              ):
                max_idx = np.argmax(hist_data['bin_counts'])
                if hist_data['bin_counts'][max_idx] > max_count:
                    max_count = hist_data['bin_counts'][max_idx]
                    # ビンの中央値を最頻値とする
                    mode_value = (hist_data['bin_edges'][max_idx] + hist_data['bin_edges'][max_idx + 1]) / 2
        
        return mode_value
    
    def getQuantile(self, per:float, planeIndex:int|None=None) -> float:
        """指定したクォンタイル値(分位数)を取得（キャッシュ付き）"""
        import numpy as np

        if (per, planeIndex) in self._percentileCache:
            return self._percentileCache[(per, planeIndex)]
        
        # 高解像度ヒストグラムで全プレーンを取得
        planeCount = self.getPlaneCount()
        planeHistograms = self._getHighResHistograms()

        # planeIndex が指定されている場合はそのプレーンのみを使用
        planeHistograms = [planeHistograms[planeIndex]] if not planeIndex is None else planeHistograms
        
        if planeHistograms and any(hist is not None for hist in planeHistograms):
            # 全プレーンのビン中央値を収集
            all_centers = []
            all_counts = []
            
            for hist_data in planeHistograms:
                if not hist_data is None:
                    centers = (hist_data['bin_edges'][:-1] + hist_data['bin_edges'][1:]) / 2
                    all_centers.append(centers)
                    all_counts.append(hist_data['bin_counts'])
            
            # 結合
            combined_centers = np.concatenate(all_centers)
            combined_counts = np.concatenate(all_counts)
            
            # ソートしてパーセンタイル計算
            sort_idx = np.argsort(combined_centers)
            sorted_centers = combined_centers[sort_idx]
            sorted_counts = combined_counts[sort_idx]
            
            total_samples = np.sum(sorted_counts)
            if total_samples > 0:
                target_count = (per) * total_samples
                cumsum = np.cumsum(sorted_counts)
                
                bin_idx = np.searchsorted(cumsum, target_count)
                bin_idx = min(bin_idx, len(sorted_centers) - 1)
                
                result = sorted_centers[bin_idx]
                self._percentileCache[(per, planeIndex)] = result
                return result
        return 0.0
    
    def getHistogram(self, bins:int=256, log_scale:bool=False) -> dict:
        """プレーン別ヒストグラムを取得（キャッシュ付き）"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        cacheKey = (bins, log_scale)
        if cacheKey in self._histogramCache:
            return self._histogramCache[cacheKey]
        
        width, height = self.getDimensions()
        planeCount = self.getPlaneCount()
        
        # 高解像度ヒストグラムでプレーン別ヒストグラムを計算
        planeHighResHists = self._getHighResHistograms()
        
        planeHistograms = []
        for planeIndex in range(planeCount):
            if(  len(planeHighResHists) <= planeIndex
              or planeHighResHists[planeIndex] is None
              ):
                planeHistograms.append({
                    'bin_counts': [0] * bins,
                    'bin_edges': nh.array([float(x)/bins for x in range(bins)]+[1.0]),
                    'total_samples': 0,
                })
            elif(  planeHighResHists[planeIndex]['max'] <= planeHighResHists[planeIndex]['min']
                or len(planeHighResHists[planeIndex]['bin_edges']) <= 2
                ):
                min = planeHighResHists[planeIndex]['max'] # 大小が逆かも知れないので入れ替え
                max = planeHighResHists[planeIndex]['min'] # 大小が逆かも知れないので入れ替え
                sum = planeHighResHists[planeIndex]['total_samples']
                planeHistograms.append({
                    'bin_counts': nh.array(([0]*(bins//2))+[sum]+([0]*(bins//2-1))),
                    'bin_edges': nh.array(([min]*(bins//2+1))+([max]*(bins//2))),
                    'total_samples': sum,
                })
            else:
                hist_data = planeHighResHists[planeIndex]
                
                range_min = hist_data['bin_edges'][1]  # 両端に count 1 の集約があるので捨てる
                range_max = hist_data['bin_edges'][-2] # 両端に count 1 の集約があるので捨てる
                
                # 目標ビンエッジを作成
                if log_scale:
                    bin_edges = np.logspace(np.log10(0.1), np.log10(1.0), bins + 1)
                    scale = 0.9 / (range_max - range_min)
                    offset = -range_min + 0.1 / scale
                    bin_edges = bin_edges / scale - offset
                else:
                    bin_edges = np.linspace(range_min, range_max, bins + 1)
                
                # 高解像度ヒストグラムを目標解像度にリサンプリング(近似)
                source_edges = hist_data['bin_edges'][1:-2] # 両端に count 1 の集約があるので捨てる
                source_counts = hist_data['bin_counts'][1:-2] # 両端に count 1 の集約があるので捨てる
                bin_indices = np.searchsorted(bin_edges[1:], source_edges[:-1])
                resampled_hist = np.zeros(len(bin_edges) - 1, dtype=int)
                np.add.at(resampled_hist, bin_indices, source_counts)
                
                planeHistograms.append({
                    'bin_counts': resampled_hist.astype(int),
                    'bin_edges': bin_edges,
                    'total_samples': hist_data['total_samples']
                })
        
        result = {'planes': planeHistograms}
        self._histogramCache[cacheKey] = result
        return result
