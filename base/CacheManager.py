'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import time
from collections import deque, OrderedDict
import os
import threading
import tempfile
import shutil
import atexit

from config import MAX_CACHE_SIZE, CACHE_BLOCK_SIZE_BYTES, BLOCK_CACHE_PAGE_SIZE
from utils.ThreadPool import CoalescingExecutor
from base.Constants import CachePolicy

# キャッシュページの最大数
MAX_BLOCK_CACHE_PAGE = MAX_CACHE_SIZE // BLOCK_CACHE_PAGE_SIZE
END_SCALE = (BLOCK_CACHE_PAGE_SIZE-1).bit_length() + 1

class LockWrapper():
    """ロックラッパークラス"""
    def __init__(self):
        self._lock = threading.Lock()
        self._local = threading.local()
    
    def __call__(self, name=None):
        # ロック時間の計測
        #if name:
        #    self._local.name = name
        #    return self
        #else:
            return self._lock
    
    def __enter__(self):
        ret = self._lock.acquire()
        self.start = time.perf_counter_ns()
        return ret
    
    def __exit__(self, exc_type, exc_value, traceback):
        elapsed_ns = time.perf_counter_ns() - self.start
        CacheManager.elapsedLogging(self._local.name, elapsed_ns)
        return self._lock.release()

def getScaleLog(size):
    """スケール指数を取得"""
    # 1 - 2^0*max:0
    #   - 2^1*max:1
    #   - 2^2*max:2
    # :
    n = (size - 1) // CACHE_BLOCK_SIZE_BYTES
    return n.bit_length()

class CType:
    NORMAL = 0
    ALL    = 1 # 全要素が同じ値
    TINY   = 2 # サイズが小さい

class CacheManager:
    """統一キャッシュ管理"""
    # キャッシュ目次
    _cachedIndex       = {}                                            # 全キャッシュ目次 {id:policy}
    _memCachedIndex    = OrderedDict()                                 # メモリキャッシュ目次(LRU) OrderedDict({id:((scale,page,index) or first or data, (dims,dtype,size,ctype))})
    _storagedIndex     = {}                                            # ストレージキャッシュ目次 {id:boolean or (first or data, (dims,dtype,size,ctype))}

    # キャッシュ本体
    _objectCache       = {}                                            # オブジェクトキャッシュ {id:data}
    _memCachePage      = []                                            # メモリキャッシュページ [page:numpy配列 uint8 * BLOCK_CACHE_PAGE_SIZE * MAX_BLOCK_SIZE_BYTES]
    _storageDir        = None                                          # ストレージキャッシュディレクトリ
    
    # キャッシュ操作
    _memCacheEvent     = {}                                            # メモリキャッシュ使用通知 {id:boolean}

    # キャッシュ管理
    _memCacheRemovable = [OrderedDict() for _ in range(END_SCALE + 1)] # 削除可能キャッシュ(LRU) [scale:OrderedDict({id:lastTime})] スケール外は実体無し保存用
    _memCacheBitmap    = 0                                             # 使用中メモリキャッシュbitmap 0/1=未使用/使用
    _memCachePageCnt   = 0                                             # メモリキャッシュページ数

    _cacheLock         = LockWrapper()                                 # 時間計測機能付きロック
    
    # 後始末関数登録状態
    _cleanupRegistered = False
    
    # 統計情報
    _setCount         = 0       # キャッシュに保存した回数
    _purgeCount       = 0       # メモリから破棄された回数
    _save1Count       = 0       # メモリに保存した回数
    _save2Count       = 0       # メモリからストレージに保存された回数
    _getCount         = 0       # キャッシュから取得した回数
    _cacheHitCount    = 0       # メモリでキャッシュヒットした回数
    _recalculateCount = 0       # メモリに無く再計算となった回数
    _loadCount        = 0       # メモリに無くストレージから復元した回数
    _elapsedLog       = deque() # 処理時間ログ
    _elapsedHis       = {}      # 処理時間ヒストグラム
    
    @classmethod
    def _getGlobelTempDir(cls):
        """キャッシュディレクトリを取得"""
        if cls._storageDir is None:
            # 初回だけクリーンアップの実施と終了時の登録を行う
            atexit.register(cls._cleanupOldTempDirs)
            cls._cleanupOldTempDirs()
            cls._cleanupRegistered = True

            # 初回だけテンポラリディレクトリを作製する
            cahedir = os.path.join(os.path.expanduser("~"), ".hoshinone", "cache")
            os.makedirs( cahedir, exist_ok=True)
            cls._storageDir = tempfile.mkdtemp( dir=cahedir, prefix="FlowData_")
        
        return cls._storageDir
    
    @classmethod
    def _cleanupOldTempDirs(cls):
        """古いテンポラリディレクトリを削除"""
        try:
            tempRoot = os.path.join(os.path.expanduser("~"), ".hoshinone", "cache")
            currentTime = time.time()
            
            if cls._storageDir:
                shutil.rmtree(cls._storageDir, ignore_errors=True) # 現在のテンポラリディレクトリを削除

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
            from utils.Debug import Debug
            Debug.log(cls.__name__, "Warning: Failed to clean up temporary directories.")
    
    @classmethod
    def get(cls, cacheKey):
        """キャッシュから取得"""
        cls._getCount += 1
        return cls.elapsed( cls._get, cacheKey)

    @classmethod
    def _get(cls, cacheKey):
        with cls._cacheLock("_get.locked.A"):
            loadStorage = False
            if cacheKey in cls._objectCache:
                # オブジェクトキャッシュにあるので採用
                cls._cacheHitCount += 1
                data = cls._objectCache[cacheKey]
                return data
            elif cacheKey in cls._memCachedIndex:
                # メモリキャッシュにあるので採用
                cls._cacheHitCount += 1
                pos, meta = cls._memCachedIndex[cacheKey]
                dims, dtype, size, ctype = meta
                if CType.ALL == ctype:
                    import numpy as np
                    all = pos
                    data = np.full(dims, all, dtype=dtype)
                elif CType.TINY == ctype:
                    data = pos
                else:
                    scale, page, index = pos
                    s = 1<<scale
                    pageBody = cls._memCachePage[page]
                    pageBody = pageBody.reshape(BLOCK_CACHE_PAGE_SIZE//s, CACHE_BLOCK_SIZE_BYTES*s)
                    data = pageBody[index,:size].view(dtype).reshape(dims)
                    cls._memCacheEvent[cacheKey] = True # LRU の順序を更新
                return data
            else:
                loadStorage = cls._storagedIndex[cacheKey] if cacheKey in cls._storagedIndex else False

        if True == loadStorage:
            # ストレージに在るので復元してメモリキャッシュに復帰
            cls._loadCount += 1
            data = cls._loadFromStorage(cacheKey)
            
            if not data is None:
                with cls._cacheLock():
                    objectCacheCount = len(cls._objectCache)
                
                if 1000 <= objectCacheCount:
                    # メモリキャッシュへの遅延書き込みが間に合っていないので少し待つ
                    # 1000:0.0010s, 1200:0.0073s 1400:0.053s 1800:2.8s
                    time.sleep(0.001*(1.01**(objectCacheCount-1000)))
                
                with cls._cacheLock("_get.locked.B"):
                    cls.__set(cacheKey, data, CachePolicy.PERSISTENT) # メモリキャッシュに復帰
            else:
                #ここには来ないはず
                pass
            return data
        elif isinstance(loadStorage, tuple):
            # meta からのデータ復元
            cls._loadCount += 1
            pos, meta = loadStorage
            dims, dtype, size, ctype = meta
            if CType.ALL == ctype:
                import numpy as np
                all = pos
                data = np.full(dims, all, dtype=dtype)
                return data
            elif CType.TINY == ctype:
                data = pos
                return data
            else:
                #ここには来ないはず
                pass
        else:
            # キャッシュに無いので、残念なら要再計算
            cls._recalculateCount += 1
            return None
    
    @classmethod
    def set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        """キャッシュに保存"""
        with cls._cacheLock():
            objectCacheCount = len(cls._objectCache)
        
        if 1000 <= objectCacheCount:
            # メモリキャッシュへの遅延書き込みが間に合っていないので少し待つ
            # 1000:0.0010s, 1200:0.0073s 1400:0.053s 1800:2.8s
            time.sleep(0.001*(1.01**(objectCacheCount-1000)))
        
        cls._setCount += 1
        return cls.elapsed( cls._set, cacheKey, data, cachePolicy)

    @classmethod
    def _set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        with cls._cacheLock("_set.locked.A"):
            cls.__set(cacheKey, data, cachePolicy)

    @classmethod
    def __set(cls, cacheKey, data, cachePolicy=CachePolicy.CALCULABLE):
        cls._cachedIndex[cacheKey] = cachePolicy
        cls._objectCache[cacheKey] = data
        
        if 100 <= len(cls._objectCache):
            CoalescingExecutor.submit(cls._lazySave1, cls._lazySave1) # メモリキャッシュへの遅延書き込み

    @classmethod
    def _lazySave1(cls):
        """メモリキャッシュへの遅延書き込み"""
        import numpy as np
        
        with cls._cacheLock("_lazySave1.locked.9"):
            for cacheKey in cls._memCacheEvent:
                if cacheKey in cls._memCachedIndex:
                    pos, meta = cls._memCachedIndex[cacheKey]
                    dims, dtype, size, ctype = meta
                    if CType.ALL == ctype or CType.TINY == ctype:
                        scale, page, index = (-1, None, None)
                    else:
                        scale, page, index = pos
                    cls._memCachedIndex.move_to_end(cacheKey) # 最後尾に移動(LRU)
                    if cacheKey in cls._memCacheRemovable[scale]:
                        cls._memCacheRemovable[scale][cacheKey] = time.perf_counter_ns()
                        cls._memCacheRemovable[scale].move_to_end(cacheKey) # 最後尾に移動(LRU)
            cls._memCacheEvent.clear()
        
        while True:
            # メインスレッドを可能な限り止めない為に、
            # このスレッドではロック時間を最小にする。
            # 大きなメモリ操作などはロックの外で行う。
            with cls._cacheLock("_lazySave1.locked.A"):
                if not cls._objectCache:
                    break
                
                cacheKey, data = next(iter(cls._objectCache.items()))
                cachePolicy = cls._cachedIndex[cacheKey]
            dims  = data.shape
            dtype = data.dtype
            size  = data.nbytes
            first = data.reshape(-1)[0]
            if np.isnan(data).all() or (data == first).all():
                ctype = CType.ALL
            elif size <= CACHE_BLOCK_SIZE_BYTES // 256:
                ctype = CType.TINY
            else:
                ctype = CType.NORMAL
            meta = (dims, dtype, size, ctype)
            if CType.ALL == ctype or CType.TINY == ctype:
                # 配列の全要素が同じなので meta データだけ保存する
                scale = -1
                with cls._cacheLock("_lazySave1.locked.E"):
                    cls._save1Count += 1
                    cls._objectCache.pop(cacheKey, None)
                    cls._memCachedIndex[cacheKey] = (first.item(), meta) if CType.ALL == ctype else (data, meta)
                    
                    if BLOCK_CACHE_PAGE_SIZE  <= len(cls._memCacheRemovable[scale]):
                        # 数が多く成ったので古いデータから削除(LRU)
                        oldKey, oldLast    = cls._memCacheRemovable[scale].popitem(last=False)
                        pos, oldMeta       = cls._memCachedIndex.pop(oldKey)
                        oldPolicy          = cls._cachedIndex[oldKey]
                        
                        if CachePolicy.PERSISTENT != oldPolicy:
                            # ポリシー persistent ではないのでキャッシュから削除
                            cls._purgeCount += 1
                            cls._cachedIndex.pop(oldKey)
                    
                    if CachePolicy.PERSISTENT != cachePolicy:
                        cls._memCacheRemovable[scale][cacheKey] = time.perf_counter_ns()
            elif CType.TINY == ctype:
                # サイズが小さいのでそのまま保存する
                with cls._cacheLock("_lazySave1.locked.F"):
                    cls._save1Count += 1
                    cls._objectCache.pop(cacheKey, None)
                    cls._memCachedIndex[cacheKey] = (data, meta)
                    
                    if BLOCK_CACHE_PAGE_SIZE <= len(cls._memCacheRemovable[scale]):
                        # 数が多く成ったので古いデータから削除(LRU)
                        oldKey, oldLast    = cls._memCacheRemovable[scale].popitem(last=False)
                        pos, oldMeta       = cls._memCachedIndex.pop(oldKey)
                        oldPolicy          = cls._cachedIndex[oldKey]
                        
                        if CachePolicy.PERSISTENT != oldPolicy:
                            # ポリシー persistent ではないのでキャッシュから削除
                            cls._purgeCount += 1
                            cls._cachedIndex.pop(oldKey)
                    
                    if CachePolicy.PERSISTENT != cachePolicy:
                        cls._memCacheRemovable[scale][cacheKey] = time.perf_counter_ns()
            else:
                scale = getScaleLog(size)
                time.sleep(0) # 連続的にロックするのを抑制する
                
                with cls._cacheLock("_lazySave1.locked.B"):
                    if pos := cls._memCacheFindFree(scale):
                        # ページに空が在るので採用
                        scale, page, index = pos
                        cls._memCacheUse(scale, page, index)
                        if len(cls._memCachePage) <= page:
                            pageBody = None
                        else:
                            pageBody = cls._memCachePage[page]
                    elif cls._memCacheRemovable[scale]:
                        # ページに空が無いので古いデータから削除(LRU)
                        oldKey, oldLast    = cls._memCacheRemovable[scale].popitem(last=False)
                        pos, oldMeta       = cls._memCachedIndex.pop(oldKey)
                        scale, page, index = pos
                        oldPolicy          = cls._cachedIndex[oldKey]
                        pageBody           = cls._memCachePage[page]
                    
                        if CachePolicy.PERSISTENT != oldPolicy:
                            # ポリシー persistent ではないのでキャッシュから削除
                            cls._purgeCount += 1
                            cls._cachedIndex.pop(oldKey)
                    else:
                        # ページに空きが無く、削除出来るデータもないので、メモリキャッシュへの遅延書き込みを保留
                        # ストレージキャッシュへの遅延書き込みが進むのを待つ
                        pos      = None
                        page     = None
                        index    = None
                        pageBody = None
                
                if index is None:
                    with cls._cacheLock("_lazySave1.locked.B2"):
                        while not cls._memCacheFindFree(scale):
                            if not cls._memCacheRemovable[scale]:
                                # 一番古いデータを探す
                                lastTime = 0
                                for s,x in enumerate(cls._memCacheRemovable):
                                    t = next(iter(x.values())) if x else 0
                                    if lastTime < t:
                                        lastTime = t
                                        scale = s
                                if 0 < lastTime:
                                    # 他のスケールに削除出来るデータがあるので古い方から解放する
                                    oldKey, oldLast = cls._memCacheRemovable[s].popitem(last=False)
                                    pos, meta = cls._memCachedIndex.pop(oldKey)
                                    dims, dtype, size, ctype = meta
                                    if CType.ALL == ctype or CType.TINY == ctype:
                                        pass
                                    else:
                                        scale, page, index = pos
                                        cls._memCacheFree(scale, page, index)
                    
                    # ストレージキャッシュへの遅延書き込みが進むのを待つ
                    time.sleep(0.1)
                else:
                    if pageBody is None:
                        # 新しいページなので、新規作成
                        pageBody    = np.empty((BLOCK_CACHE_PAGE_SIZE*CACHE_BLOCK_SIZE_BYTES), dtype=np.uint8) # ページ作成
                        with cls._cacheLock("_lazySave1.locked.C"):
                            cls._memCachePage.append(pageBody)
                            cls._memCachePageCnt += 1
                    s = 1<<scale
                    pageBody = pageBody.reshape(BLOCK_CACHE_PAGE_SIZE//s, CACHE_BLOCK_SIZE_BYTES*s)
                    pageBody[index, :size] = data.reshape(-1).view(np.uint8) # メモリキャッシュへ書き込み
                    
                    with cls._cacheLock("_lazySave1.locked.D"):
                        cls._save1Count += 1
                        cls._objectCache.pop(cacheKey, None)
                        cls._memCachedIndex[cacheKey] = (pos, meta)
                        if CachePolicy.PERSISTENT != cachePolicy:
                            cls._memCacheRemovable[scale][cacheKey] = time.perf_counter_ns()
                        if MAX_BLOCK_CACHE_PAGE <= cls._memCachePageCnt and 0 == cls._save1Count % (BLOCK_CACHE_PAGE_SIZE//8):
                            # 空きが1ページ以下に成ったのでストレージキャッシュを開始
                            CoalescingExecutor.submit(cls._lazySave2, cls._lazySave2) # ストレージキャッシュへの遅延書き込み
                time.sleep(0) # 連続的にロックするのを抑制する
    
    @classmethod
    def _lazySave2(cls):
        """ストレージキャッシュへの遅延書き込み"""
        # 古いデータから連続する PERSISTENT を抽出する
        end = False
        req = {}
        step = BLOCK_CACHE_PAGE_SIZE // 8
        for s in range(0, BLOCK_CACHE_PAGE_SIZE, step): # 古いデータから1ページ分を検索する
            with cls._cacheLock("_lazySave2.locked.A"):
                for i, cacheKey in enumerate(cls._memCachedIndex.keys()):
                    if s + step <= i:
                        end = True
                        break
                    elif i < s:
                        pass
                    elif CachePolicy.PERSISTENT != cls._cachedIndex.get(cacheKey, None):
                        end = True
                        break
                    
                    pos, meta = cls._memCachedIndex[cacheKey]
                    dims, dtype, size, ctype = meta
                    if CType.ALL == ctype or CType.TINY == ctype:
                        scale, page, index = (-1, None, None)
                        if cacheKey in cls._memCacheRemovable[scale]:
                            # 既に削除可能なので何もしない
                            pass
                        else:
                            # 実体無しなので即時削除可能
                            cls._save2Count += 1
                            cls._storagedIndex[cacheKey] = (pos, meta)
                            req[cacheKey] = (scale, True)
                    else:
                        scale, page, index = pos
                        if cacheKey in cls._memCacheRemovable[scale]:
                            # 既に削除可能なので何もしない
                            pass
                        elif cacheKey in cls._storagedIndex:
                            # 既に保存済みなので削除可能
                            req[cacheKey] = (scale, True)
                        else:
                            # 未保存なのでまだ削除できない
                            req[cacheKey] = (scale, False)
                if end:
                    break
            time.sleep(0) # 連続的にロックするのを抑制する

        for cacheKey, (scale, isRemovable) in reversed(req.items()):
            # メインスレッドを可能な限り止めない為に、
            # このスレッドではロック時間を最小にする。
            # ストレージ操作などはロックの外で行う。
            if isRemovable:
                with cls._cacheLock("_lazySave2.locked.B"):
                    if cacheKey in cls._memCachedIndex:
                        lastTime = next(iter(cls._memCacheRemovable[scale].values())) if cls._memCacheRemovable[scale] else time.perf_counter_ns()
                        cls._memCacheRemovable[scale][cacheKey] = lastTime
                        cls._memCacheRemovable[scale].move_to_end(cacheKey, last=False) # 先頭に移動(LRU)
            else:
                with cls._cacheLock("_lazySave2.locked.C"):
                    if cacheKey in cls._memCachedIndex:
                        pos, meta = cls._memCachedIndex[cacheKey]
                        scale, page, index = pos
                        dims, dtype, size, ctype = meta
                        s = 1<<scale
                        pageBody = cls._memCachePage[page]
                        pageBody = pageBody.reshape(BLOCK_CACHE_PAGE_SIZE//s, CACHE_BLOCK_SIZE_BYTES*s)
                        data = pageBody[index,:size].view(dtype).reshape(dims)
                
                if cls._saveToStorage(cacheKey, data): # ストレージへ書き込み
                    # 書き込み成功
                    with cls._cacheLock("_lazySave2.locked.D"):
                        if cacheKey in cls._memCachedIndex:
                            cls._save2Count += 1
                            cls._storagedIndex[cacheKey] = True
                            lastTime = next(iter(cls._memCacheRemovable[scale].values())) if cls._memCacheRemovable[scale] else time.perf_counter_ns()
                            cls._memCacheRemovable[scale][cacheKey] = lastTime
                            cls._memCacheRemovable[scale].move_to_end(cacheKey, last=False) # 先頭に移動(LRU)
            time.sleep(0) # 連続的にロックするのを抑制する

    @classmethod
    def isCached(cls, cacheKey):
        """キャッシュされているかどうかを判定"""
        with cls._cacheLock():
            if cacheKey in cls._cachedIndex:
                cls._memCacheEvent[cacheKey] = True # LRU の順序を更新
                return True
            else:
                return False

    @classmethod
    def _saveToStorage(cls, cacheKey, data):
        """ストレージに退避"""
        import numpy as np

        try:
            tempDir = cls._getGlobelTempDir()

            filename = f"{cacheKey}".replace("/", "_").replace("\\", "_").replace(":", "_")
            pre = filename[:2]
            subDir = os.path.join( cls._storageDir, pre)
            os.makedirs(subDir, exist_ok=True)
            
            fileName = os.path.join(subDir, f"{filename}.npy")
            cls.elapsed(np.save, fileName, data, allow_pickle=False)
            
            return True
        except (OSError, IOError, ValueError):
            from utils.Debug import Debug
            Debug.log(cls.__name__, f"Warning: Unable to save block data to storage : key: {cacheKey}")
            return False
    
    @classmethod
    def _loadFromStorage(cls, cacheKey):
        """ストレージから復元"""
        import numpy as np
        
        try:
            if cls._storageDir is None:
                return None
            
            filename = f"{cacheKey}".replace("/", "_").replace("\\", "_").replace(":", "_")
            pre = filename[:2]
            subDir = os.path.join( cls._storageDir, pre)
            
            fileName = os.path.join(subDir, f"{filename}.npy")
            data = cls.elapsed(np.load, fileName, allow_pickle=False)
            
            return data
        except (OSError, IOError, ValueError):
            from utils.Debug import Debug
            Debug.log(cls.__name__, f"Warning: Unable to load block data from storage : key: {cacheKey}")
            return None
    
    @classmethod
    def clearByPartialKey(cls, cacheKey):
        """key の部分一致でデータを削除"""
        # ストレージを削除
        if cls._storageDir and os.path.exists(cls._storageDir):
            pre = cacheKey[:2]
            subDir = os.path.join( cls._storageDir, pre)
            if os.path.exists(subDir):
                for fileName in os.listdir(subDir):
                    basename, ext = os.path.splitext(fileName)
                    if cacheKey in basename and ext in [".pkl", ".npy"]:
                        # ファイルを削除
                        os.remove(os.path.join(subDir, fileName))
        
        with cls._cacheLock("clearByPartialKey.locked.A"):
            # キャッシュを削除
            cls._clearByPartialKey(cls._storagedIndex, cacheKey)
            values = cls._clearByPartialKey(cls._memCachedIndex, cacheKey)
            for pos, meta in values:
                (dims, dtype, size, ctype) = meta
                if CType.ALL == ctype or CType.TINY == ctype:
                    pass
                else:
                    scale, page, index = pos
                    cls._memCacheFree(scale, page, index)
            for d in cls._memCacheRemovable:
                cls._clearByPartialKey(d, cacheKey) 
            cls._clearByPartialKey(cls._cachedIndex, cacheKey)
            cls._clearByPartialKey(cls._objectCache, cacheKey)
    
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
    
    # _memCacheBitmap 用ビット定義  0:11, 1:0101, 2:00010001....
    _scaleBit = [0 for s in range(END_SCALE)]
    for i in range(END_SCALE):
        for j in range(0,MAX_BLOCK_CACHE_PAGE):
            _scaleBit[i] |= 1 << (BLOCK_CACHE_PAGE_SIZE * j)
    for i in range(END_SCALE):
        for j in range(i+1):
            _scaleBit[j] |= _scaleBit[j] << (1<<i)
    
    PAGE_SHIFT = (BLOCK_CACHE_PAGE_SIZE).bit_length() - 1
    PAGE_MASK  = BLOCK_CACHE_PAGE_SIZE - 1
    
    @classmethod
    def _memCacheFindFree(cls, scale):
        """
        空いているメモリキャッシュ位置を検索

        _memCacheBitmap の解説
        メモリキャッシュの使用状態を表す。
        1:使用中
        0:未使用
        各スケールでメモリキャッシュの実体は共有なので、
        使用状態は各スケールで連動している必要がある
        """
        bitmap = ~cls._memCacheBitmap
        if 0==scale:
            bitmap = bitmap & cls._scaleBit[0]
            if 0==bitmap:
                return None
            x = bitmap & -bitmap   # 最下位の 1 を取得
            i = x.bit_length() - 1 # 最下位の 1 の位置を取得
            page = i >> cls.PAGE_SHIFT
            index = i & cls.PAGE_MASK
            return (scale, page, index)
        elif 1==scale:
            bitmap &= bitmap >> 1
            bitmap = bitmap & cls._scaleBit[1]
            if 0==bitmap:
                return None
            
            x = bitmap & -bitmap   # 最下位の 1 を取得
            i = x.bit_length() - 1 # 最下位の 1 の位置を取得
            page = i >> cls.PAGE_SHIFT
            index = (i & cls.PAGE_MASK) >> 1
            return (scale, page, index)
        else:
            # 一般化
            for i in range(scale):
                bitmap &= bitmap >> (1<<i)
            
            bitmap = bitmap & cls._scaleBit[scale]
            if 0==bitmap:
                return None
            
            x = bitmap & -bitmap   # 最下位の 1 を取得
            i = x.bit_length() - 1 # 最下位の 1 の位置を取得
            page = i >> cls.PAGE_SHIFT
            index = (i & cls.PAGE_MASK) >> scale
            return (scale, page, index)
    
    @classmethod
    def _memCacheUse(cls, scale, page, index):
        """メモリキャッシュ使用中にセット"""
        if 0==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + index
            bit = 1 << i
            cls._memCacheBitmap |= bit
        elif 1==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << 1)
            bit = 3 << i
            cls._memCacheBitmap |= bit
        else:
            # 一般化
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << scale)
            bit = (1<<(1<<scale)) - 1
            bit = bit << i
            cls._memCacheBitmap |= bit
    
    @classmethod
    def _memCacheFree(cls, scale, page, index):
        """メモリキャッシュ使用中を解放"""
        if 0==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + index
            bit = 1 << i
            cls._memCacheBitmap &= ~bit
        elif 1==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << 1)
            bit = 3 << i
            cls._memCacheBitmap &= ~bit
        else:
            # 一般化
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << scale)
            bit = (1<<(1<<scale)) - 1
            bit = bit << i
            cls._memCacheBitmap &= ~bit
    
    @classmethod
    def elapsed(cls, func, *args, **kwargs):
        """ func の処理時間を計測する"""
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        elapsed_ns = (time.perf_counter_ns() - start)

        cls._elapsedLog.append((func.__qualname__, elapsed_ns))

        if 1000 <= len(cls._elapsedLog):
            CoalescingExecutor.submit(cls._updateElapsedHis, cls._updateElapsedHis, cls._elapsedLog)

        return result
    
    @classmethod
    def elapsedLogging(cls, name, elapsed_ns):
        cls._elapsedLog.append((name, elapsed_ns))

        if 1000 <= len(cls._elapsedLog):
            CoalescingExecutor.submit(cls._updateElapsedHis, cls._updateElapsedHis, cls._elapsedLog)

    @classmethod
    def _updateElapsedHis(cls, elapsedLog):
        """処理時間のヒストグラムを更新"""
        logs = list(elapsedLog)
        elapsedLog.clear()
        for log in logs:
            name, elapsed = log
            cacheCount = len(cls._cachedIndex)
            
            key = None
            for e in range(10):
                x = int(4096*(1.4142136**e))
                if cacheCount < x:
                    key = f"{x}:{name}"
                    break
            if key is None:
                key = f"{x}+:{name}"
            
            his = cls._elapsedHis.setdefault( key, {})
            elapsed = min( elapsed//1000 , 8191)

            for e in range(20):
                x = int(10*(2**e))
                for values in cls._elapsedHis.values():
                    values.setdefault(x,0)
                
                if elapsed < x:
                    his[x] += 1
                    break

    @classmethod
    def getCacheStats(cls):
        """キャッシュ量とストレージ使用量を取得"""
        objCacheCount    = len(cls._objectCache)
        cacheCount       = len(cls._memCachedIndex)
        cacheSize        = cacheCount * CACHE_BLOCK_SIZE_BYTES
        storageCount     = len(cls._storagedIndex)
        storageSize      = storageCount * CACHE_BLOCK_SIZE_BYTES
        return (objCacheCount, cacheCount, cacheSize, storageCount, storageSize,
                cls._getCount, cls._cacheHitCount, cls._recalculateCount, cls._loadCount,
                cls._setCount, cls._purgeCount, cls._save1Count, cls._save2Count,
                cls._elapsedHis)
