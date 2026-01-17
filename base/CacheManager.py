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
    _globalCachedAll   = {}     # 全キャッシュ目次 {id:policy}
    _globalCached      = {}     # メモリキャッシュ目次 {id:((page,index),policy,dims)}
    _globalStoraged    = {}     # ストレージキャッシュ目次 {id:boolean}
    _cacheLock = threading.Lock()
    _globalObjCache    = {}     # オブジェクトキャッシュ {id:data}
    _globalCachePage   = []     # メモリキャッシュページ {page:numpy配列[BLOCK_CACHE_PAGE_SIZE,BLOCK_SIZE,BLOCK_SIZE]}
    _globalCacheFree   = deque([(i,j) for i in range(MAX_BLOCK_CACHE_PAGE-1,-1,-1) for j in range(BLOCK_CACHE_PAGE_SIZE-1,-1,-1)])
                                # 空いているメモリキャッシュ目次 [(page,index)]
    _globalStorageWait = {}     # ストレージキャッシュ待ち {id:data}
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
            cls._getCount += 1
            return cls.elapsed( cls._get, cacheKey)

    @classmethod
    def _get(cls, cacheKey):
        if cacheKey in cls._globalObjCache:
            # オブジェクトキャッシュにあるので採用
            data = cls._globalObjCache[cacheKey]
            return data
        elif cacheKey in cls._globalCached:
            # メモリキャッシュにあるので取り出して再追加(LRU)
            cache = cls._globalCached.pop(cacheKey)
            cls._globalCached[cacheKey] = cache # 最後尾に追加(LRU)
            (page, index), cachePolicy, dims = cache
            data = cls._globalCachePage[page][index,:dims[0],:dims[1]]
            return data
        elif cacheKey in cls._globalStorageWait:
            # ストレージ保存待ちなので取り出してメモリキャッシュに復帰
            data = cls._globalStorageWait.pop(cacheKey)
            cls._set(cacheKey, data, CachePolicy.PERSISTENT) # メモリキャッシュに復帰
            return data
        elif cacheKey in cls._globalStoraged:
            # ストレージに在るので復元してメモリキャッシュに復帰
            cls._cacheMissCount += 1
            cls._loadCount += 1
            data = cls._loadFromStorage(cacheKey)
            
            if not data is None:
                cls._set(cacheKey, data, CachePolicy.PERSISTENT) # メモリキャッシュに復帰
            else:
                #ここには来ないはず
                pass
            return data
        else:
            # ストレージに無いので、残念なら要再計算
            cls._cacheMissCount += 1
            cls._recalculateCount += 1
            return None
    
    @classmethod
    def set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        """キャッシュに保存"""
        with cls._cacheLock:
            cls._setCount += 1
            return cls.elapsed( cls._set, cacheKey, data, cachePolicy)

    @classmethod
    def _set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        cls._globalCachedAll[cacheKey] = cachePolicy
        cls._globalObjCache[cacheKey] = data
        
        if 100 <= len(cls._globalObjCache):
            CoalescingExecutor.submit(cls._lazySave1, cls._lazySave1) # メモリキャッシュへの遅延書き込み

    @classmethod
    def _lazySave1(cls):
        """メモリキャッシュへの遅延書き込み"""
        while True:
            # メインスレッドを可能な限り止めない為に、
            # このスレッドではロック時間を最小にする。
            # 大きなメモリ操作などはロックの外で行う。
            with cls._cacheLock:
                if not cls._globalObjCache:
                    break

                cacheKey, data = next(iter(cls._globalObjCache.items()))
                cachePolicy = cls._globalCachedAll[cacheKey]

                if cls._globalCacheFree:
                    # ページに空が在るので採用
                    pos = cls._globalCacheFree.pop()
                    page, index = pos

                    if page < len(cls._globalCachePage):
                        pageBody = cls._globalCachePage[page]
                    else:
                        pageBody = None
                else:
                    # ページに空が無いので古いデータから削除(LRU)
                    oldKey = next(iter(cls._globalCached))
                    pos, oldPolicy, oldDims = cls._globalCached.pop(oldKey)
                    page, index = pos
                    pageBody = cls._globalCachePage[page]
                
                    if CachePolicy.PERSISTENT != oldPolicy:
                        # ポリシー persistent ではないのでキャッシュから削除
                        cls._purgeCount += 1
                        cls._globalCachedAll.pop(oldKey)
            
            if pageBody is None:
                from utils import numpy_helpers as nh
                # 新しいページなので、新規作成
                pageBody = nh.empty((BLOCK_CACHE_PAGE_SIZE,BLOCK_SIZE,BLOCK_SIZE)) # ページ作成
                with cls._cacheLock:
                    cls._globalCachePage.append(pageBody)
            
            pageBody[index,:data.shape[0],:data.shape[1]] = data # メモリキャッシュへ書き込み
            
            with cls._cacheLock:
                cls._globalCached[cacheKey] = (pos, cachePolicy, data.shape)
                if cacheKey in cls._globalObjCache:
                    cls._globalObjCache.pop(cacheKey)
                if CachePolicy.PERSISTENT == cachePolicy:
                    cls._globalStorageWait[cacheKey] = data
                    if 100 <= len(cls._globalStorageWait):
                        CoalescingExecutor.submit(cls._lazySave2, cls._lazySave2) # ストレージキャッシュへの遅延書き込み

    @classmethod
    def _lazySave2(cls):
        """ストレージキャッシュへの遅延書き込み"""
        while True:
            with cls._cacheLock:
                if not cls._globalStorageWait:
                    break

                cacheKey, data = next(iter(cls._globalStorageWait.items()))

            if cls._saveToStorage(cacheKey, data): # ストレージへ書き込み
                with cls._cacheLock:
                    cls._saveCount += 1
                    cls._globalStoraged[cacheKey] = True
                    if cacheKey in cls._globalStorageWait:
                        cls._globalStorageWait.pop(cacheKey)

    @classmethod
    def isCached(cls, cacheKey):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalCachedAll

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
            cls._clearByPartialKey(cls._globalStoraged, cacheKey)
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
        storageCount = len(cls._globalStoraged)
        storageSize = storageCount * ESTIMATE_SIZE_BYTES_PER_BLOCK
        return cacheCount, cacheSize, storageCount, storageSize, cls._getCount, cls._cacheMissCount, cls._loadCount, cls._recalculateCount, cls._setCount, cls._purgeCount, cls._saveCount, cls._elapsedHis
