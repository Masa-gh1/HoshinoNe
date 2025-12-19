'''
FlowData class

@author: Masakazu Inoue
'''

import tempfile
import pickle
from tkinter import messagebox
import os
import shutil
import time
import atexit
import threading
from config import BLOCK_SIZE, MAX_BLOCK_CACHE_SIZE
from .DataBlock import DataBlock

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

class FlowData:
    _cleanup_registered = False
    _globalBlockCache = {}
    _globalTempDir = None
    _lock = threading.Lock()
    
    def __init__(self, headers=None):
        # 初回のみクリーンアップを登録
        if not FlowData._cleanup_registered:
            atexit.register(FlowData._cleanupOldTempDirs)
            FlowData._cleanupOldTempDirs()
            FlowData._cleanup_registered = True
        
        # グローバル変数の操作をスレッドセーフに
        with FlowData._lock:
            # グローバルなFlowData_*ディレクトリを作成（初回のみ）
            if FlowData._globalTempDir is None:
                FlowData._globalTempDir = tempfile.mkdtemp(prefix="FlowData_")
        
        # インスタンスごとのdata_*サブディレクトリを作成
        self.tempDir = tempfile.mkdtemp(prefix=os.path.join(FlowData._globalTempDir, "data_"))
        
        os.makedirs(self.tempDir, exist_ok=True)
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
    
    @staticmethod
    def _cleanupOldTempDirs():
        """古いFlowData一時ディレクトリを削除"""
        try:
            tempRoot = tempfile.gettempdir()
            currentTime = time.time()
            
            for item in os.listdir(tempRoot):
                if item.startswith("FlowData_"):
                    itemPath = os.path.join(tempRoot, item)
                    if os.path.isdir(itemPath):
                        # 24時間以上古いディレクトリまたは空のディレクトリを削除
                        isOld = currentTime - os.path.getmtime(itemPath) > 24*60*60
                        isEmpty = len(os.listdir(itemPath)) == 0
                        
                        if isOld or isEmpty:
                            shutil.rmtree(itemPath, ignore_errors=True)
                            # グローバル参照をクリア
                            if FlowData._globalTempDir == itemPath:
                                FlowData._globalTempDir = None
        except (OSError, IOError):
            pass
    
    def __del__(self):
        try:
            if os.path.exists(self.tempDir):
                # グローバルキャッシュから自身のキャッシュエントリを削除
                with FlowData._lock:
                    keysToRemove = [key for key in FlowData._globalBlockCache.keys() if key[0] == self.tempDir]
                    for key in keysToRemove:
                        del FlowData._globalBlockCache[key]
                
                # 個別のdata_*ディレクトリを削除
                shutil.rmtree(self.tempDir)
                
                # _globalTempDirが空になったらそれも削除
                with FlowData._lock:
                    if(   FlowData._globalTempDir
                      and os.path.exists(FlowData._globalTempDir) 
                      and len(os.listdir(FlowData._globalTempDir)) == 0
                      ):
                        shutil.rmtree(FlowData._globalTempDir)
                        FlowData._globalTempDir = None
        except (ImportError, AttributeError, OSError):
            pass
    
    def _getBlockFileName(self, planeIndex, blockX, blockY):
        """ブロックファイル名を生成"""
        return os.path.join(self.tempDir, f"block_{planeIndex}_{blockX}_{blockY}.pkl")
    
    def _loadBlock(self, planeIndex, blockX, blockY):
        """指定ブロックを読み込み（グローバルキャッシュ付き）"""
        cacheKey = (self.tempDir, planeIndex, blockX, blockY)
        
        # グローバルキャッシュから取得
        with FlowData._lock:
            if cacheKey in FlowData._globalBlockCache:
                return FlowData._globalBlockCache[cacheKey]
        
        # ファイルから読み込み
        fileName = self._getBlockFileName(planeIndex, blockX, blockY)
        try:
            with open(fileName, 'rb') as f:
                block = pickle.load(f)
                
            # グローバルキャッシュに保存
            FlowData._addToGlobalCache(cacheKey, block, self)
            return block
        except (FileNotFoundError, EOFError):
            return None
    
    def _saveBlock(self, planeIndex, blockX, blockY, blockData):
        """指定ブロックをキャッシュに保存"""
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
        
        # 最大値・最小値を更新し、キャッシュをクリア
        if arr.size > 0:
            blockMax = np.max(arr)
            blockMin = np.min(arr)
            
            if self._maxValue is None or blockMax > self._maxValue:
                self._maxValue = blockMax
            if self._minValue is None or blockMin < self._minValue:
                self._minValue = blockMin
            
            # データ更新時にキャッシュをクリア
            self._percentileCache.clear()
            self._histogramCache.clear()
        
        # グローバルキャッシュに保存
        cacheKey = (self.tempDir, planeIndex, blockX, blockY)
        FlowData._addToGlobalCache(cacheKey, arr, self)
    
    
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
            result = np.percentile(allValues, percentile)
            self._percentileCache[percentile] = result
            return result
        else:
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
                if range_min is None:
                    range_min = np.min(planeValues)
                if range_max is None:
                    range_max = np.max(planeValues)
                
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
                
                hist, _ = np.histogram(planeValues, bins=bin_edges)
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
    
    @classmethod
    def _addToGlobalCache(cls, cacheKey, block, flowDataInstance):
        """ブロックをグローバルキャッシュに追加"""
        with cls._lock:
            # キャッシュサイズを超えた場合、古いエントリをファイルに書き出し
            if len(cls._globalBlockCache) >= MAX_BLOCK_CACHE_SIZE:
                try:
                    # 最初のキーを取得（FIFO）
                    oldestKey = next(iter(cls._globalBlockCache))
                    oldestBlock = cls._globalBlockCache.get(oldestKey)
                    
                    if oldestBlock is not None:
                        # ファイルに書き出し
                        tempDir, planeIndex, blockX, blockY = oldestKey
                        try:
                            fileName = os.path.join(tempDir, f"block_{planeIndex}_{blockX}_{blockY}.pkl")
                            with open(fileName, 'wb') as f:
                                pickle.dump(oldestBlock, f)
                        except (OSError, IOError):
                            pass  # ファイル書き込みエラーを無視
                    
                    # キーが存在する場合のみ削除
                    if oldestKey in cls._globalBlockCache:
                        del cls._globalBlockCache[oldestKey]
                except (StopIteration, KeyError):
                    pass  # キャッシュが空またはキーが存在しない
            
            cls._globalBlockCache[cacheKey] = block
    
    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とディスク使用量を取得"""
        cacheCount = len(cls._globalBlockCache)
        cacheSize = cacheCount * BLOCK_SIZE * BLOCK_SIZE * 8  # 1ブロック = BLOCK_SIZE x BLOCK_SIZE x 8バイト(float64)
        
        diskSize = 0
        if cls._globalTempDir and os.path.exists(cls._globalTempDir):
            try:
                for root, dirs, files in os.walk(cls._globalTempDir):
                    for file in files:
                        diskSize += os.path.getsize(os.path.join(root, file))
            except (OSError, IOError):
                pass
        
        return cacheSize, diskSize