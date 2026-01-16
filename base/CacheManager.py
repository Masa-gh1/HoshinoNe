'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import time
from collections import deque
import sys
import os
import threading
import tempfile
import shutil
import atexit

from config import MAX_BLOCK_CACHE_SIZE, ESTIMATE_SIZE_BYTES_PER_BLOCK, BLOCK_SIZE, BLOCK_CACHE_PAGE_SIZE
from utils.ThreadPool import CoalescingExecutor
from base.Constants import CachePolicy

# キャッシュページの最大数
MAX_BLOCK_CACHE_PAGE = MAX_BLOCK_CACHE_SIZE // BLOCK_CACHE_PAGE_SIZE

class CacheManager:
    """統一キャッシュ管理"""
    _globalCached      = {}     # メモリキャッシュ目次 {id:((page,index),policy,dims)}
    _globalSerialized  = {}     # ストレージ保存目次 {id:boolean}
    _globalCachedAll   = {}     # 全キャッシュ保存目次 {id:boolean}
    _cacheLock = threading.Lock()
    _globalObjCache    = {}     # オブジェクトキャッシュ {id:data}
    _globalCachePage   = [None] * MAX_BLOCK_CACHE_PAGE
                                # メモリキャッシュページ {page:numpy配列[BLOCK_CACHE_PAGE_SIZE,BLOCK_SIZE,BLOCK_SIZE]}
    _globalCacheFree   = deque([(i,j) for i in range(MAX_BLOCK_CACHE_PAGE-1,-1,-1) for j in range(BLOCK_CACHE_PAGE_SIZE-1,-1,-1)])
                                # 空いているメモリキャッシュ目次 [(page,index)]
    _globalTempDir     = None   # 一時ディレクトリ
    _cleanupRegistered = False  # 後始末関数登録状態
    
    # 統計情報
    _setCount         = 0  # メモリに保存した回数
    _purgeCount       = 0  # メモリから破棄された回数
    _saveCount        = 0  # メモリからストレージに保存された回数
    _getCount         = 0  # メモリから取得した回数
    _cacheMissCount   = 0  # メモリでキャッシュミスした回数
    _recalculateCount = 0  # メモリに無く再計算となった回数
    _loadCount        = 0  # メモリに無くストレージから復元した回数
    _elapsedLog       = [] # 処理時間ログ
    _elapsedHis       = {} # 処理時間ヒストグラム
    
    @classmethod
    def _getGlobelTempDir(cls):
        """キャッシュディレクトリを取得"""
        if cls._globalTempDir is None:
            # 初回だけクリーンアップの実施と終了時の登録を行う
            atexit.register(cls._cleanupOldTempDirs)
            cls._cleanupOldTempDirs()
            cls._cleanupRegistered = True

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
    def get(cls, cacheKey):
        """キャッシュから取得"""
        with cls._cacheLock:
            return cls.elapsed( cls._get, cacheKey)

    @classmethod
    def _get(cls, cacheKey):
        cls._getCount += 1

        cache = cls._globalCached.pop(cacheKey,None)
        if not cache is None:
            cls._globalCached[cacheKey] = cache # 最後尾に追加(LRU)
            (page, index), cachePolicy, dims = cache
            if cacheKey in cls._globalObjCache:
                data = cls._globalObjCache[cacheKey]
            else:
                data = cls._globalCachePage[page][index,:dims[0],:dims[1]]
        else:
            cls._cacheMissCount += 1
            data = None
    
        if not data is None:
            return data
        elif cls._isStoraged(cacheKey):
            # ストレージに在るので復元
            cls._loadCount += 1
            data = cls._loadFromStorage(cacheKey)
            
            if not data is None:
                # ストレージから読み込んだので最後尾に追加
                cls._set(cacheKey, data, CachePolicy.PERSISTENT)
            else:
                #ここには来ないはず
                pass
            return data
        else:
            # ストレージに無いので、残念なら要再計算
            cls._recalculateCount += 1
            return None
    
    @classmethod
    def set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        """キャッシュに保存"""
        with cls._cacheLock:
            return cls.elapsed( cls._set, cacheKey, data, cachePolicy)

    @classmethod
    def _set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        cls._setCount += 1

        if cacheKey in cls._globalCached:
            # 既にキャッシュにあるので何もしない
            return
        
        if cls._globalCacheFree:
            pos = cls._globalCacheFree.pop()
            page, index = pos
        else:
            # 空が無いので古いデータから削除(LRU)
            oldKey = next(iter(cls._globalCached))
            pos, oldPolicy, oldDims = cls._globalCached.pop(oldKey)
            page, index = pos
            if oldKey in cls._globalObjCache:
                oldData = cls._globalObjCache.pop(oldKey)
            else:
                oldData = cls._globalCachePage[page][index,:oldDims[0],:oldDims[1]]
            if CachePolicy.PERSISTENT != oldPolicy:
                # ポリシー persistent ではないのでキャッシュから削除
                cls._globalCachedAll.pop(oldKey)
                cls._purgeCount += 1
            elif cls._isStoraged(oldKey):
                # ポリシー persistent であり、
                # 既にストレージに保存ずみなのでキャッシュから削除
                pass
            elif cls._saveToStorage(oldKey, oldData):
                # ポリシー persistent であり、
                # ストレージへ保存したのでキャッシュから削除
                cls._saveCount += 1
                cls._globalSerialized[oldKey] = True
            else:
                # ストレージへの保存に失敗
                # log は _saveToStorage に委譲
                pass

        if cls._globalCachePage[page] is None:
            from utils import numpy_helpers as nh
            cls._globalCachePage[page] = nh.empty((BLOCK_CACHE_PAGE_SIZE,BLOCK_SIZE,BLOCK_SIZE))
        
        cls._globalObjCache[cacheKey] = data
        cls._globalCached[cacheKey] = (pos, cachePolicy, data.shape)
        cls._globalCachedAll[cacheKey] = True

        CoalescingExecutor.submit(cls._lazySave, cls._lazySave) # キャッシュへの遅延書き込み

    @classmethod
    def _lazySave(cls):
        """キャッシュへの遅延書き込み"""
        with cls._cacheLock:
            tmplist = []
            for cacheKey, data in cls._globalObjCache.items():
                pos, cachePolicy, dims = cls._globalCached[cacheKey]
                tmplist.append((cacheKey, pos, cachePolicy, dims, data))
        
        for cacheKey, pos, cachePolicy, dims, data in tmplist:
            page, index = pos

            cls._globalCachePage[page][index,:data.shape[0],:data.shape[1]] = data
            if CachePolicy.PERSISTENT == cachePolicy:
                saved = cls._saveToStorage(cacheKey, data)
            else:
                saved = False
            
            with cls._cacheLock:
                cls._globalObjCache.pop(cacheKey)
                if saved:
                    cls._globalSerialized[cacheKey] = True

    @classmethod
    def isCached(cls, cacheKey):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalCachedAll

    @classmethod
    def _isStoraged(cls, cacheKey):
        """ストレージ保存されているかどうかを判定"""
        return cacheKey in cls._globalSerialized

    @classmethod
    def _saveToStorage(cls, cacheKey, data):
        """ストレージに退避"""
        import numpy as np

        try:
            tempDir = cls._getGlobelTempDir()

            filename = f"{cacheKey}".replace("/", "_").replace("\\", "_").replace(":", "_")
            pre = filename[:2]
            subDir = os.path.join( cls._globalTempDir, pre)
            os.makedirs(subDir, exist_ok=True)
            
            fileName = os.path.join(subDir, f"{filename}.npy")
            cls.elapsed(np.save, fileName, data, allow_pickle=False)
            
            return True
        except (OSError, IOError, ValueError):
            print(f"Warning: Unable to save block data to storage : key: {cacheKey}", file=sys.stderr)
            return False
    
    @classmethod
    def _loadFromStorage(cls, cacheKey):
        """ストレージから復元"""
        import numpy as np
        
        try:
            if cls._globalTempDir is None:
                return None
            
            filename = f"{cacheKey}".replace("/", "_").replace("\\", "_").replace(":", "_")
            pre = filename[:2]
            subDir = os.path.join( cls._globalTempDir, pre)
            
            fileName = os.path.join(subDir, f"{filename}.npy")
            data = cls.elapsed(np.load, fileName, allow_pickle=False)
            
            return data
        except (OSError, IOError, ValueError):
            print(f"Warning: Unable to load block data from storage : key: {cacheKey}", file=sys.stderr)
            return None
    
    @classmethod
    def clearByPartialKey(cls, cacheKey):
        """key の部分一致でデータを削除"""
        # ストレージを削除
        if cls._globalTempDir and os.path.exists(cls._globalTempDir):
            pre = cacheKey[:2]
            subDir = os.path.join( cls._globalTempDir, pre)
            if os.path.exists(subDir):
                for fileName in os.listdir(subDir):
                    basename, ext = os.path.splitext(fileName)
                    if cacheKey in basename and ext in [".pkl", ".npy"]:
                        # ファイルを削除
                        os.remove(os.path.join(subDir, fileName))
        
        with cls._cacheLock:
            # キャッシュを削除
            cls._clearByPartialKey(cls._globalSerialized, cacheKey)
            values = cls._clearByPartialKey(cls._globalCached, cacheKey)
            for pos, _, _ in values:
                cls._globalCacheFree.append(pos)
            cls._clearByPartialKey(cls._globalCachedAll, cacheKey)
    
    @classmethod
    def _clearByPartialKey(cls, cache, cacheKey):
        """key の部分一致でデータを削除"""
        keysToRemove = []
        # メモリキャッシュから対象キーを収集
        for key in cache.keys():
            if cacheKey in key:
                keysToRemove.append(key)
        removeValues = []
        # メモリキャッシュから削除
        for key in keysToRemove:
            removeValues.append(cache.pop(key))
        
        return removeValues
    
    @classmethod
    def elapsed(cls, func, *args, **kwargs):
        """ func の処理時間を計測する"""
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter_ns() - start)//1000
        cls._elapsedLog.append((func.__qualname__, elapsed))

        if 1000 <= len(cls._elapsedLog):
            tmp = cls._elapsedLog
            cls._elapsedLog = []
            CoalescingExecutor.submit(cls._updateElapsedHis, cls._updateElapsedHis, tmp)

        return result
    
    @classmethod
    def _updateElapsedHis(cls, elapsedLog):
        for log in elapsedLog:
            name, elapsed = log
            cacheCount = len(cls._globalCachedAll)

            elapsed = min( elapsed , 8191)
            x = 4096
            while True:
                if cacheCount < x:
                    key = f"{name}:{x}"
                    break
                x = x*2
            
            his = cls._elapsedHis.setdefault( key, {})
            x = 10
            while True:
                for values in cls._elapsedHis.values():
                    values.setdefault(x,0)
                
                if elapsed < x:
                    his[x] += 1
                    break
                x = x*2

    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とストレージ使用量を取得"""
        cacheCount = len(cls._globalCached)
        cacheSize = cacheCount * ESTIMATE_SIZE_BYTES_PER_BLOCK
        storageCount = len(cls._globalSerialized)
        storageSize = storageCount * ESTIMATE_SIZE_BYTES_PER_BLOCK
        return cacheCount, cacheSize, storageCount, storageSize, cls._getCount, cls._cacheMissCount, cls._loadCount, cls._recalculateCount, cls._setCount, cls._purgeCount, cls._saveCount, cls._elapsedHis
