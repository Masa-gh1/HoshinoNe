'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import time
import sys
import os
import threading
import tempfile
import shutil
import atexit

from config import MAX_BLOCK_CACHE_SIZE, ESTIMATE_SIZE_PER_BLOCK, BLOCK_SIZE
from base.Constants import CachePolicy

# キャッシュ用巨大配列の一枚当たりサイズ bytes = CACHE_ARRAY_SIZE * BLOCK_SIZE * BLOCK_SIZE * DEFAULT_BLOCK_TYPE_BYTES
CACHE_ARRAY_SIZE = 1024
# キャッシュ用巨大配列の最大数
MAX_CACHE_ARRAY = MAX_BLOCK_CACHE_SIZE // 1024

class CacheManager:
    """統一キャッシュ管理"""
    _globalCacheArray  = [None] * MAX_CACHE_ARRAY
                                # キャッシュ用巨大配列のリスト {page:numpy配列}
    _globalCacheIndex  = {}     # メモリキャッシュ目次 {id:(page,index,policy,dims)}
    _globalCacheLast   = (-1,CACHE_ARRAY_SIZE)
                                # キャッシュで最後に使った位置 (page,index)
    _globalSerialIndex = {}     # ストレージ保存目次 {id:boolean}
    _cacheLock = threading.Lock()
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

        cache = cls._globalCacheIndex.pop(cacheKey,None)
        if not cache is None:
            page, index, cachePolicy, dims = cache
            data = cls._globalCacheArray[page][index,:dims[0],:dims[1]]
            if page == cls._globalCacheLast[0]:
                cls._globalCacheIndex[cacheKey] = cache # 最新ページにいるので目次だけ最後尾に追加(LRU)
            else:
                cls._set(cacheKey, data, cachePolicy) # 最新ページに居ないので最後尾に追加
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

        if cacheKey in cls._globalCacheIndex:
            # 既にあるので一度削除
            del cls._globalCacheIndex[cacheKey]

        page, index = cls._globalCacheLast
        index += 1
        if CACHE_ARRAY_SIZE <= index:
            index = 0
            page += 1
            page %= MAX_CACHE_ARRAY
            if not cls._globalCacheArray[page] is None:
                # 古いデータを破棄又はストレージへ保存
                oldArray = cls._globalCacheArray[page]
                while True:
                    oldKey = next(iter(cls._globalCacheIndex))
                    oldPage, oldIndex, oldPolicy, oldDims = cls._globalCacheIndex[oldKey]
                    if page != oldPage:
                        # 古いデータの処理終了
                        break
                    elif oldPolicy != CachePolicy.PERSISTENT:
                        # ポリシー persistent ではないのでキャッシュから削除
                        cls._purgeCount += 1
                        del cls._globalCacheIndex[oldKey]
                    elif cls._isStoraged(oldKey):
                        # ポリシー persistent であり、
                        # 既にストレージに保存ずみなのでキャッシュから削除
                        del cls._globalCacheIndex[oldKey]
                    elif cls._saveToStorage(oldKey, oldArray[oldIndex,:oldDims[0],:oldDims[1]]):
                        # ポリシー persistent であり、
                        # ストレージへ保存したのでキャッシュから削除
                        cls._saveCount += 1
                        cls._globalSerialIndex[oldKey] = True
                        del cls._globalCacheIndex[oldKey]
                    else:
                        # ストレージへの保存に失敗
                        # log は _saveToStorage に委譲
                        pass
            
            from utils import numpy_helpers as nh
            # 新しい配列を用意(配列を再利用すると numpy 配列に view が在る場合に破壊してしまう)
            cls._globalCacheArray[page] = nh.empty((CACHE_ARRAY_SIZE,BLOCK_SIZE,BLOCK_SIZE))
        
        cls._globalCacheArray[page][index,:data.shape[0],:data.shape[1]] = data
        cls._globalCacheIndex[cacheKey] = (page, index, cachePolicy, data.shape)
        cls._globalCacheLast = (page, index)

    @classmethod
    def isCached(cls, cacheKey):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock:
            return cacheKey in cls._globalCacheIndex

    @classmethod
    def isStoraged(cls, cacheKey):
        """ストレージ保存されているかどうかを判定"""
        with cls._cacheLock:
            return cls._isStoraged(cacheKey)

    @classmethod
    def _isStoraged(cls, cacheKey):
        return cacheKey in cls._globalSerialIndex

    @classmethod
    def _saveToStorage(cls, cacheKey, data):
        """ストレージに退避（永続化データのみ）"""
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
        """ストレージから読み込み（永続化データのみ）"""
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
            cls._clearByPartialKey(cls._globalSerialIndex, cacheKey)
            cls._clearByPartialKey(cls._globalCacheIndex, cacheKey)
    
    @classmethod
    def _clearByPartialKey(cls, cache, cacheKey):
        """key の部分一致でデータを削除"""
        keysToRemove = []
        # メモリキャッシュから対象キーを収集
        for key in cache.keys():
            if cacheKey in key:
                keysToRemove.append(key)

        # メモリキャッシュから削除
        for key in keysToRemove:
            del cache[key]
    
    @classmethod
    def elapsed(cls, func, *args, **kwargs):
        """ func の処理時間を計測する"""
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter_ns() - start)//1000
        elapsed = min( elapsed , 8191)

        globalBlockCacheCount = len(cls._globalCacheIndex)
        name = f"{func.__qualname__}:{MAX_BLOCK_CACHE_SIZE//16384*16384}+"
        for x in range(16384,MAX_BLOCK_CACHE_SIZE+1,16384):
            if globalBlockCacheCount < x-1:
                name = f"{func.__qualname__}:{x}"
                break
        
        his = cls._elapsedHis.setdefault( name, {10:0, 20:0, 40:0, 80:0, 160:0, 320:0, 640:0, 1280:0, 2560:0, 5120:0, 10240:0, 20480:0, 40960:0, 81920:0})
        x = 10
        while x<=8192:
            if elapsed < x:
                his[x] += 1
                break
            x = x*2
        return result
    
    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とストレージ使用量を取得"""
        cacheCount = len(cls._globalCacheIndex)
        cacheSize = cacheCount * ESTIMATE_SIZE_PER_BLOCK
        storageCount = len(cls._globalSerialIndex)
        storageSize = storageCount * ESTIMATE_SIZE_PER_BLOCK
        return cacheCount, cacheSize, storageCount, storageSize, cls._getCount, cls._cacheMissCount, cls._loadCount, cls._recalculateCount, cls._setCount, cls._purgeCount, cls._saveCount, cls._elapsedHis
