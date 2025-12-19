'''
FlowData class

@author: Masakazu Inoue
'''

import tempfile
import pickle
import os
import shutil
import time
import atexit
import numpy as np
from config import BLOCK_SIZE, MAX_BLOCK_CACHE_SIZE
from .DataBlock import DataBlock

class FlowData:
    _cleanup_registered = False
    _globalBlockCache = {}
    
    def __init__(self, headers=None):
        # 初回のみクリーンアップを登録
        if not FlowData._cleanup_registered:
            atexit.register(FlowData._cleanupOldTempDirs)
            FlowData._cleanupOldTempDirs()
            FlowData._cleanup_registered = True
        
        self.tempDir = tempfile.mkdtemp(prefix="FlowData_")
        self.headers = headers if headers is not None else {}
        self._dimensions = (0, 0, 0)
        self._blockSize = BLOCK_SIZE
    
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
                        # 24時間以上古いディレクトリを削除
                        if currentTime - os.path.getmtime(itemPath) > 24*60*60:
                            shutil.rmtree(itemPath, ignore_errors=True)
        except (OSError, IOError):
            pass
    
    def __del__(self):
        try:
            if os.path.exists(self.tempDir):
                shutil.rmtree(self.tempDir)
        except (ImportError, AttributeError):
            pass
    
    def _getBlockFileName(self, planeIndex, blockX, blockY):
        """ブロックファイル名を生成"""
        return os.path.join(self.tempDir, f"block_{planeIndex}_{blockX}_{blockY}.pkl")
    
    def _loadBlock(self, planeIndex, blockX, blockY):
        """指定ブロックを読み込み（グローバルキャッシュ付き）"""
        cacheKey = (self.tempDir, planeIndex, blockX, blockY)
        
        # グローバルキャッシュから取得
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
        # numpy配列として正規化
        if isinstance(blockData, list):
            arr = np.array(blockData, dtype=np.float64)
        else:
            arr = blockData
        
        # グローバルキャッシュに保存
        cacheKey = (self.tempDir, planeIndex, blockX, blockY)
        FlowData._addToGlobalCache(cacheKey, arr, self)
    
    def get2dData(self):
        """互換性のため2次元配列として取得"""
        width, height, planeCount = self._dimensions
        if planeCount == 0:
            return []
        
        # 第1プレーンのみを取得
        data = []
        for y in range(0, height, self._blockSize):
            for x in range(0, width, self._blockSize):
                block = self.getBlock(0, x, y)
                if block:
                    data.extend(block.data)
        return data
    
    def set2dData(self, data, headers=None):
        """2次元配列から設定（1プレーンとして扱う）"""
        if not data:
            return
        
        height = len(data)
        width = len(data[0]) if height > 0 else 0
        self.setDimensions(width, height, 1)
        
        if headers is not None:
            self.headers = headers
        
        # ブロック単位で保存
        for y in range(0, height, self._blockSize):
            for x in range(0, width, self._blockSize):
                endY = min(y + self._blockSize, height)
                endX = min(x + self._blockSize, width)
                
                block = []
                for rowIdx in range(y, endY):
                    blockRow = data[rowIdx][x:endX]
                    block.append(blockRow)
                
                dataBlock = DataBlock( 0, x, y, block, self)
                self.setBlock(dataBlock)

    
    def setDimensions(self, width, height, planeCount):
        """データの次元を設定"""
        self._dimensions = (width, height, planeCount)
    
    def getMode(self):
        """データのモードを取得"""
        if 'mode' in self.headers:
            return self.headers['mode']
        # フォールバック: 次元数から推定
        if self._dimensions[2] == 3:
            return 'RGB'
        elif self._dimensions[2] == 1:
            return 'L'
        else:
            return None
    
    def getDimensions(self):
        """データの次元を取得 (width, height, planes)"""
        return self._dimensions
    
    def getDiagonal2(self):
        """データの対角線の長さを取得"""
        width, height, _ = self.getDimensions()
        return (width*width + height*height)
    
    def getBlock(self, planeIndex, x, y):
        """指定位置からブロックを取得"""
        width, height, planeCount = self.getDimensions()
        if planeIndex >= planeCount or x >= width or y >= height:
            return None
        
        blockX = x // self._blockSize
        blockY = y // self._blockSize
        
        # 遅延ロード用のDataBlockを作成（データはNoneで初期化）
        return DataBlock(planeIndex, blockX * self._blockSize, blockY * self._blockSize, None, self)
    
    def getBlockCount(self):
        """ブロックの総数を取得"""
        width, height, planeCount = self.getDimensions()
        if planeCount == 0:
            return 0
        
        blocksX = (width + self._blockSize - 1) // self._blockSize
        blocksY = (height + self._blockSize - 1) // self._blockSize
        
        return planeCount * blocksX * blocksY
    
    def iterateBlocks(self):
        """全ブロックを順次取得するジェネレータ"""
        width, height, planeCount = self.getDimensions()
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
    
    @classmethod
    def _addToGlobalCache(cls, cacheKey, block, flowDataInstance):
        """ブロックをグローバルキャッシュに追加"""
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