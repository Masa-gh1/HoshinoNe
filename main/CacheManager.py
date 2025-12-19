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
from config import MAX_BLOCK_CACHE_SIZE, ESTIMATE_SIZE_PER_BLOCK

class CacheManager:
    """キャッシュポリシーベースの統一キャッシュ管理"""
    
    # キャッシュポリシー定義
    PERSISTENT = 'persistent'    # 永続化（ストレージ退避あり）
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
    _saveCount = 0
    _loadCount = 0
    
    @classmethod
    def _getGlobelTempDir(cls):
        """テンポラリディレクトリを取得"""
        if not cls._cleanup_registered:
            # 初回だけクリーンアップの実施と終了時の登録を行う
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
            
            if cls._globalTempDir:
                shutil.rmtree(cls._globalTempDir, ignore_errors=True) # 現在のテンポラリディレクトリを削除

            for item in os.listdir(tempRoot):
                itemPath = os.path.join(tempRoot, item)
                if not item.startswith("FlowData_"):
                    pass
                elif not os.path.isdir(itemPath):
                    pass
                elif( (24*60*60 < currentTime - os.path.getmtime(itemPath)) # 24時間以上前
                    or(0 == len(os.listdir(itemPath))) # ディレクトリが空
                    ):
                    shutil.rmtree(itemPath, ignore_errors=True)
                            
        except (OSError, IOError):
            pass
    
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
            cls._loadCount += 1
            return CacheManager._loadFromStorage(cacheKey)
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
    def isCached(cls, cacheKey, cachePolicy):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalBlockCache

    @classmethod
    def isStoraged(cls, cacheKey, cachePolicy):
        """ストレージ保存されているかどうかを判定"""
        tempDir = cls._getGlobelTempDir()
        fileName = os.path.join(tempDir, f"{cacheKey}.pkl")
        return os.path.exists(fileName)

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
        
        if policy == cls.PERSISTENT:
            # persistent ポリシーのみストレージに退避
            if cls.isStoraged( oldestKey, policy):
                # 既に保存ずみなのでキャッシュから削除
                del cls._globalBlockCache[oldestKey]
            elif cls._saveToStorage(oldestKey, blockData):
                # 保存成功したのでキャッシュから削除
                cls._saveCount += 1
                del cls._globalBlockCache[oldestKey]
        else:
            cls._purgeCount += 1
            del cls._globalBlockCache[oldestKey]
    
    @classmethod
    def _saveToStorage(cls, cacheKey, blockData):
        """ストレージに退避（永続化データのみ）"""
        try:
            tempDir = cls._getGlobelTempDir()
            fileName = os.path.join(tempDir, f"{cacheKey}.pkl")
            with open(fileName, 'wb') as f:
                pickle.dump(blockData, f)
                f.flush()
                os.fsync(f.fileno())
            
            return True
        except (OSError, IOError, ValueError):
            print(f"Warning: Unable to save block data to storage : key: {cacheKey}", file=sys.stderr)
            return False
        
    
    @classmethod
    def _loadFromStorage(cls, cacheKey):
        """ストレージから読み込み（永続化データのみ）"""
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
            print(f"Warning: Unable to load block data from storage : key: {cacheKey}", file=sys.stderr)
            return None
    
    @classmethod
    def clearByInstanceId(cls, instanceId):
        """指定instanceIdの全データを削除"""
        # ファイルも削除対象に含める
        if cls._globalTempDir and os.path.exists(cls._globalTempDir):
            for fileName in os.listdir(cls._globalTempDir):
                if instanceId in fileName and fileName.endswith(".pkl"):
                    try:
                        # ファイルを削除
                        os.remove(os.path.join(cls._globalTempDir, fileName))
                    except (OSError, IOError):
                        pass
        
        with cls._cacheLock:
            keysToRemove = []
            # メモリキャッシュから対象キーを収集
            for key in cls._globalBlockCache.keys():
                if len(key) > 0 and key[0] == instanceId:
                    keysToRemove.append(key)
            
            # メモリキャッシュから削除
            for key in keysToRemove:
                del cls._globalBlockCache[key]
            
        with cls._tempLock:
            for key in list(cls._globalBlockTemp.keys()):
                if len(key) > 0 and key[0] == instanceId:
                    del cls._globalBlockTemp[key]
        
    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とストレージ使用量を取得"""
        from config import BLOCK_SIZE
        
        cacheCount = len(cls._globalBlockCache)
        cacheSize = cacheCount * ESTIMATE_SIZE_PER_BLOCK
        
        storageSize = 0
        storageFileCount = 0
        if cls._globalTempDir and os.path.exists(cls._globalTempDir):
            try:
                for root, dirs, files in os.walk(cls._globalTempDir):
                    for file in files:
                        if file.endswith('.pkl'):
                            storageFileCount += 1
                            storageSize += os.path.getsize(os.path.join(root, file))
            except (OSError, IOError):
                pass
        
        return cacheSize, storageSize, cls._cacheMissCount, cls._purgeCount, cls._saveCount, cls._loadCount
