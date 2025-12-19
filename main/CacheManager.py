'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import sys
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
    CALCULABLE = 'calculable'    # 計算可能（キャッシュする:上限まで保持）
    TEMPORARY  = 'temporary'     # 一時データ(キャッシュしない：削除されるまで保持)
    
    _globalBlockCache = {}
    _globalBlockTemp = {}
    _cacheLock = threading.Lock()
    _tempLock = threading.Lock()
    _globalTempDir = None
    _cleanup_registered = False
    
    _cacheMissCount = 0
    _purgeCount = 0
    _saveDiskCount = 0
    _loadDiskCount = 0
    
    @classmethod
    def _getGlobelTempDir(cls):
        """テンポラリディレクトリを取得"""
        if not cls._cleanup_registered:
            # 初回だけクリーンアップの実施を登録を行う
            atexit.register(cls._cleanupOldTempDirs)
            cls._cleanupOldTempDirs()
            cls._cleanup_registered = True
        
            # 初回だけテンポラリディレクトリを作製する
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
    def isCached(cls, cacheKey, cachePolicy):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalBlockCache
    
    @classmethod
    def get(cls, cacheKey, cachePolicy):
        """キャッシュから取得"""
        if CacheManager.TEMPORARY == cachePolicy:
            with cls._tempLock:
                cached = cls._globalBlockTemp.get(cacheKey)
        else:
            with cls._cacheLock:
                cached = cls._globalBlockCache.get(cacheKey)
        
        if cached is None:
            data = None
            cls._cacheMissCount += 1
        else:
            data = cached[0]  # (blockData, cachePolicy) のタプルから blockData を返す

        if data is not None:
            return data
        elif CacheManager.PERSISTENT == cachePolicy:
            cls._loadDiskCount += 1
            return CacheManager.loadFromDisk(cacheKey)
        else:
            return None
    
    @classmethod
    def set(cls, cacheKey, blockData, cachePolicy=CALCULABLE):
        """キャッシュに保存"""
        if cls.TEMPORARY == cachePolicy:
            with cls._tempLock:
                cls._globalBlockTemp[cacheKey] = (blockData, cachePolicy)
        else:
            with cls._cacheLock:
                if len(cls._globalBlockCache) >= MAX_BLOCK_CACHE_SIZE:
                    cls._evictOldest()
                cls._globalBlockCache[cacheKey] = (blockData, cachePolicy)
    
    @classmethod
    def _evictOldest(cls):
        """最古エントリの退避・削除"""
        if not cls._globalBlockCache:
            return
        
        # 優先順位: calculable > persistent > temporary # persistent は永続化されるので先に追い出す。 temporary はキャッシュには居ないはず 
        priorities = {cls.CALCULABLE: 2, cls.PERSISTENT: 1, cls.TEMPORARY: 0}
        
        # 優先順位が低く古いデータから削除
        sortedKeys = sorted(cls._globalBlockCache.keys(), 
                            key=lambda k: priorities.get(cls._globalBlockCache[k][1], 2)) # (blockData, cachePolicy) のタプルから cachePolicy 使う
        
        oldestKey = sortedKeys[0]
        blockData, policy = cls._globalBlockCache[oldestKey]
        
        # persistentポリシーのみディスク退避
        if policy == cls.PERSISTENT:
            if cls._saveToDisk(oldestKey, blockData):
                cls._saveDiskCount += 1
                del cls._globalBlockCache[oldestKey]
        else:
            cls._purgeCount += 1
            del cls._globalBlockCache[oldestKey]
    
    @classmethod
    def _saveToDisk(cls, cacheKey, blockData):
        """ディスクに退避（永続化データのみ）"""
        try:
            tempDir = cls._getGlobelTempDir()
            fileName = os.path.join(tempDir, f"{cacheKey}.pkl")
            with open(fileName, 'wb') as f:
                pickle.dump(blockData, f)
            
            return True
        except (OSError, IOError, ValueError):
            print(f"Warning: Unable to save block data to disk : key: {cacheKey}", file=sys.stderr)
            return False
        
    
    @classmethod
    def loadFromDisk(cls, cacheKey):
        """ディスクから読み込み（永続化データのみ）"""
        try:
            if cls._globalTempDir is None:
                return None
            
            fileName = os.path.join(cls._globalTempDir, f"{cacheKey}.pkl")
            with open(fileName, 'rb') as f:
                blockData = pickle.load(f)
            # 読み込み成功時はキャッシュに復帰
            cls.set(cacheKey, blockData, cls.PERSISTENT)
            return blockData
        except (OSError, IOError, ValueError):
            print(f"Warning: Unable to load block data from disk : key: {cacheKey}", file=sys.stderr)
            return None
    
    @classmethod
    def clearByInstanceId(cls, instanceId):
        """指定instanceIdの全データを削除"""
        with cls._tempLock:
            for key in list(cls._globalBlockTemp.keys()):
                if len(key) > 0 and key[0] == instanceId:
                    del cls._globalBlockTemp[key]
        
        with cls._cacheLock:
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
        
        return cacheSize, diskSize, cls._cacheMissCount, cls._purgeCount, cls._saveDiskCount, cls._loadDiskCount
