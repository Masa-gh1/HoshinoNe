'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import os
import pickle
import threading
import tempfile
import shutil
import time
import atexit
from config import MAX_BLOCK_CACHE_SIZE

class CacheManager:
    """キャッシュポリシーベースの統一キャッシュ管理"""
    
    # キャッシュポリシー定義
    PERSISTENT = 'persistent'    # 永続化（ディスク退避あり）
    HEAVY_CALC = 'heavy_calc'    # 重い計算（メモリ優先保持）
    LIGHT_CALC = 'light_calc'    # 軽い計算（優先削除）
    
    _globalBlockCache = {}
    _globalTempDir = None
    _cleanup_registered = False
    _lock = threading.Lock()
    
    @classmethod
    def _ensureTempDir(cls):
        """テンポラリディレクトリの初期化"""
        if not cls._cleanup_registered:
            atexit.register(cls._cleanupOldTempDirs)
            cls._cleanupOldTempDirs()
            cls._cleanup_registered = True
        
        if cls._globalTempDir is None:
            cls._globalTempDir = tempfile.mkdtemp(prefix="FlowData_")
        
        return cls._globalTempDir
    
    @classmethod
    def _cleanupOldTempDirs(cls):
        """古いテンポラリディレクトリを削除"""
        try:
            tempRoot = tempfile.gettempdir()
            currentTime = time.time()
            
            for item in os.listdir(tempRoot):
                if item.startswith("FlowData_"):
                    itemPath = os.path.join(tempRoot, item)
                    if os.path.isdir(itemPath):
                        isOld = currentTime - os.path.getmtime(itemPath) > 24*60*60
                        isEmpty = len(os.listdir(itemPath)) == 0
                        
                        if isOld or isEmpty:
                            shutil.rmtree(itemPath, ignore_errors=True)
                            if cls._globalTempDir == itemPath:
                                cls._globalTempDir = None
        except (OSError, IOError):
            pass
    
    @classmethod
    def get(cls, cacheKey):
        """キャッシュから取得"""
        with cls._lock:
            cached = cls._globalBlockCache.get(cacheKey)
            if cached is not None:
                return cached[0]  # (blockData, cachePolicy)のタプルからblockDataを返す
            return None
    
    @classmethod
    def set(cls, cacheKey, blockData, cachePolicy=HEAVY_CALC):
        """キャッシュに保存"""
        with cls._lock:
            if len(cls._globalBlockCache) >= MAX_BLOCK_CACHE_SIZE:
                cls._evictOldest(cachePolicy)
            cls._globalBlockCache[cacheKey] = (blockData, cachePolicy)
    
    @classmethod
    def _evictOldest(cls, requestingPolicy):
        """最古エントリの退避・削除"""
        if not cls._globalBlockCache:
            return
        
        # 削除優先順位: light_calc > heavy_calc > persistent
        priorities = {cls.LIGHT_CALC: 0, cls.HEAVY_CALC: 1, cls.PERSISTENT: 2}
        
        # 優先順位の低いデータから削除
        sortedKeys = sorted(cls._globalBlockCache.keys(), 
                           key=lambda k: priorities.get(cls._globalBlockCache[k][1], 3))
        
        oldestKey = sortedKeys[0]
        blockData, policy = cls._globalBlockCache[oldestKey]
        
        # persistentポリシーのみディスク退避
        if policy == cls.PERSISTENT:
            cls._saveToDisk(oldestKey, blockData)
        
        del cls._globalBlockCache[oldestKey]
    
    @classmethod
    def _saveToDisk(cls, cacheKey, blockData):
        """ディスクに退避（永続化データのみ）"""
        try:
            tempDir = cls._ensureTempDir()
            instanceId, planeIndex, blockX, blockY = cacheKey
            fileName = os.path.join(tempDir, f"{instanceId}_{planeIndex}_{blockX}_{blockY}.pkl")
            with open(fileName, 'wb') as f:
                pickle.dump(blockData, f)
        except (OSError, IOError, ValueError):
            pass  # 退避失敗は無視
    
    @classmethod
    def loadFromDisk(cls, cacheKey):
        """ディスクから読み込み（永続化データのみ）"""
        try:
            if cls._globalTempDir is None:
                return None
            
            instanceId, planeIndex, blockX, blockY = cacheKey
            fileName = os.path.join(cls._globalTempDir, f"{instanceId}_{planeIndex}_{blockX}_{blockY}.pkl")
            with open(fileName, 'rb') as f:
                blockData = pickle.load(f)
            # 読み込み成功時はキャッシュに復帰
            cls.set(cacheKey, blockData, cls.PERSISTENT)
            return blockData
        except (FileNotFoundError, EOFError, ValueError):
            return None
    
    @classmethod
    def clearByInstanceId(cls, instanceId):
        """指定instanceIdの全データを削除"""
        with cls._lock:
            keysToRemove = []
            diskFilesToRemove = []
            
            # メモリキャッシュから対象キーを収集
            for key in cls._globalBlockCache.keys():
                if len(key) > 0 and key[0] == instanceId:
                    keysToRemove.append(key)
            
            # ディスクファイルも削除対象に含める
            if cls._globalTempDir and os.path.exists(cls._globalTempDir):
                try:
                    for fileName in os.listdir(cls._globalTempDir):
                        if fileName.startswith(f"{instanceId}_") and fileName.endswith(".pkl"):
                            diskFilesToRemove.append(os.path.join(cls._globalTempDir, fileName))
                except (OSError, IOError):
                    pass
            
            # メモリキャッシュから削除
            for key in keysToRemove:
                del cls._globalBlockCache[key]
            
            # ディスクファイルを削除
            for filePath in diskFilesToRemove:
                try:
                    os.remove(filePath)
                except (OSError, IOError):
                    pass
    
    @classmethod
    def clearByPolicy(cls, cachePolicy):
        """指定ポリシーのデータを削除（instanceId無関係）"""
        with cls._lock:
            keysToRemove = []
            
            for key, (_, policy) in cls._globalBlockCache.items():
                if policy == cachePolicy:
                    keysToRemove.append(key)
            
            for key in keysToRemove:
                del cls._globalBlockCache[key]
    
    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とディスク使用量を取得"""
        from config import BLOCK_SIZE
        
        cacheCount = len(cls._globalBlockCache)
        cacheSize = cacheCount * BLOCK_SIZE * BLOCK_SIZE * 8  # 1ブロック = BLOCK_SIZE x BLOCK_SIZE x 8バイト(float64)
        
        diskSize = 0
        diskFileCount = 0
        if cls._globalTempDir and os.path.exists(cls._globalTempDir):
            try:
                for root, dirs, files in os.walk(cls._globalTempDir):
                    for file in files:
                        if file.endswith('.pkl'):
                            diskFileCount += 1
                            diskSize += os.path.getsize(os.path.join(root, file))
            except (OSError, IOError):
                pass
        
        return cacheSize, diskSize
    
    @classmethod
    def listDiskFiles(cls):
        """ディスクファイルの一覧を表示"""
        if not cls._globalTempDir or not os.path.exists(cls._globalTempDir):
            print("No temp directory exists")
            return
        
        try:
            files = [f for f in os.listdir(cls._globalTempDir) if f.endswith('.pkl')]
            print(f"Disk files in {cls._globalTempDir}:")
            for file in files:
                filePath = os.path.join(cls._globalTempDir, file)
                size = os.path.getsize(filePath)
                print(f"  {file} ({size} bytes)")
        except (OSError, IOError) as e:
            print(f"Error listing disk files: {e}")