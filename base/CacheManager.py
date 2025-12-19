'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
import sys
import os
import threading
import tempfile
import shutil
import time
import atexit

from config import MAX_BLOCK_CACHE_SIZE, ESTIMATE_SIZE_PER_BLOCK, BLOCK_SIZE
from base.Constants import CachePolicy

class CacheManager:
    """統一キャッシュ管理"""
    _globalBlockCache = {}
    _globalBlockSerial = {}
    _cacheLock = threading.RLock()
    _globalTempDir = None
    _cleanup_registered = False
    
    _cacheMissCount = 0
    _purgeCount = 0
    _saveCount = 0
    _loadCount = 0
    _elapsedHis = {}
    
    @classmethod
    def _getGlobelTempDir(cls):
        """キャッシュディレクトリを取得"""
        if cls._globalTempDir is None:
            # 初回だけクリーンアップの実施と終了時の登録を行う
            atexit.register(cls._cleanupOldTempDirs)
            cls._cleanupOldTempDirs()
            cls._cleanup_registered = True

            # 初回だけテンポラリディレクトリを作製する
            cahedir = os.path.join(os.path.expanduser("~"), ".hoshinone", "cache")
            os.makedirs( cahedir, exist_ok=True)
            cls._globalTempDir = tempfile.mkdtemp( dir=cahedir, prefix="FlowData_")
        
        # platformdirs 使う場合
        #if cls._globalTempDir is None:
        #    try:
        #        from platformdirs import user_cache_dir
        #        cls._globalTempDir = user_cache_dir("HoshinoNe")
        #    except ImportError:
        #        # フォールバック: 一時ディレクトリ使用
        #        cls._globalTempDir = tempfile.mkdtemp(prefix="FlowData_")
        #    os.makedirs(cls._globalTempDir, exist_ok=True)
        return cls._globalTempDir
    
    @classmethod
    def _cleanupOldTempDirs(cls):
        """古いテンポラリディレクトリを削除"""
        try:
            tempRoot = os.path.join(os.path.expanduser("~"), ".hoshinone", "cache")
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
            print("Warning: Failed to clean up temporary directories.", file=sys.stderr)
    
    @classmethod
    def get(cls, cacheKey, cachePolicy):
        """キャッシュから取得"""
        with cls._cacheLock:
            cache = cls._globalBlockCache.pop(cacheKey,None)
        if cache is None:
            data = None
        else:
            cls._globalBlockCache[cacheKey] = cache # 最後尾に再追加(LRU)
            _, data = cache
        
        if data is not None:
            return data
        elif CachePolicy.PERSISTENT == cachePolicy:
            # ポリシー persistent なのでストレージから復元
            cls._loadCount += 1
            return cls._loadFromStorage(cacheKey)
        else:
            # ポリシー persistent ではないので、残念なら要再計算
            cls._cacheMissCount += 1
            return None
    
    @classmethod
    def set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        """キャッシュに保存"""
        with cls._cacheLock:
            if MAX_BLOCK_CACHE_SIZE <= len(cls._globalBlockCache):
                # 古いデータから削除(LRU)
                oldestKey = next(iter(cls._globalBlockCache))
                oldPolicy, oldData = cls._globalBlockCache[oldestKey]
                
                if oldPolicy != CachePolicy.PERSISTENT:
                    # ポリシー persistent ではないのでキャッシュから削除
                    cls._purgeCount += 1
                    del cls._globalBlockCache[oldestKey]
                elif cls.isStoraged( oldestKey, oldPolicy):
                    # ポリシー persistent であり、
                    # 既にストレージに保存ずみなのでキャッシュから削除
                    del cls._globalBlockCache[oldestKey]
                elif cls._saveToStorage(oldestKey, oldData):
                    # ポリシー persistent であり、
                    # ストレージへ保存したのでキャッシュから削除
                    cls._saveCount += 1
                    del cls._globalBlockCache[oldestKey]
            cls._globalBlockCache[cacheKey] = (cachePolicy, data)
    
    @classmethod
    def isCached(cls, cacheKey, cachePolicy):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalBlockCache

    @classmethod
    def isStoraged(cls, cacheKey, cachePolicy):
        """ストレージ保存されているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalBlockSerial

    @classmethod
    def _saveToStorage(cls, cacheKey, data):
        """ストレージに退避（永続化データのみ）"""
        try:
            tempDir = cls._getGlobelTempDir()

            pre = f"{cacheKey}"[2:4]
            subDir = os.path.join( cls._globalTempDir, pre)
            os.makedirs(subDir, exist_ok=True)

            fileName = os.path.join(subDir, f"{cacheKey}.npy")
            cls.elapsed(np.save, fileName, data.pop("data"), allow_pickle=False)
            cls._globalBlockSerial[f"{cacheKey}"] = data
            
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
            
            pre = f"{cacheKey}"[2:4]
            subDir = os.path.join( cls._globalTempDir, pre)

            fileName = os.path.join(subDir, f"{cacheKey}.npy")
            data = cls._globalBlockSerial[f"{cacheKey}"].copy()
            data["data"] = cls.elapsed(np.load, fileName, allow_pickle=False)
            
            # 読み込み成功時はキャッシュに復帰
            cls.set(cacheKey, data, CachePolicy.PERSISTENT)
            return data
        except (OSError, IOError, ValueError):
            print(f"Warning: Unable to load block data from storage : key: {cacheKey}", file=sys.stderr)
            return None
    
    @classmethod
    def clearByInstanceId(cls, instanceId):
        """指定instanceIdの全データを削除"""
        # ファイルも削除対象に含める
        if cls._globalTempDir and os.path.exists(cls._globalTempDir):
            pre = f"{instanceId}"[:2]
            subDir = os.path.join( cls._globalTempDir, pre)
            if os.path.exists(subDir):
                for fileName in os.listdir(subDir):
                    cacheKey, ext = os.path.splitext(fileName)
                    if instanceId in cacheKey and ext in [".pkl", ".npy"]:
                        # ファイルを削除
                        os.remove(os.path.join(subDir, fileName))
                        del cls._globalBlockSerial[f"{cacheKey}"]
        
        with cls._cacheLock:
            keysToRemove = []
            # メモリキャッシュから対象キーを収集
            for key in cls._globalBlockCache.keys():
                if len(key) > 0 and key[0] == instanceId:
                    keysToRemove.append(key)
            
            # メモリキャッシュから削除
            for key in keysToRemove:
                del cls._globalBlockCache[key]
    
    @classmethod
    def elapsed(cls, func, *args, **kwargs):
        """ func の処理時間を計測する"""
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = int((time.time() - start)*1000)
        elapsed = min( elapsed , 8191)
        his = cls._elapsedHis.setdefault( func.__qualname__, {1:0, 2:0, 4:0, 8:0, 16:0, 32:0, 64:0, 128:0, 256:0, 512:0, 1024:0, 2048:0, 4096:0, 8192:0})
        x = 1
        while x<=8192:
            if elapsed < x:
                his[x] += 1
                break
            x = x*2
        return result

    
    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とストレージ使用量を取得"""
        cacheCount = len(cls._globalBlockCache)
        cacheSize = cacheCount * ESTIMATE_SIZE_PER_BLOCK
        storageCount = len(cls._globalBlockSerial)
        storageSize = storageCount * ESTIMATE_SIZE_PER_BLOCK
        return cacheCount, cacheSize, storageCount, storageSize, cls._cacheMissCount, cls._purgeCount, cls._saveCount, cls._loadCount, cls._elapsedHis
