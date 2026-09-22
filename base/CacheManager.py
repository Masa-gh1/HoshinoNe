'''
CacheManager - 統一キャッシュ管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    import numpy as np

# キャッシュページの最大数
MAX_CACHE_PAGES = MAX_CACHE_SIZE // BLOCK_CACHE_PAGE_SIZE

# ブロックスケール指数上限
END_SCALE = (BLOCK_CACHE_PAGE_SIZE-1).bit_length() + 1

class LockWrapper():
    """ロックラッパークラス"""
    def __init__(self):
        self._lock = threading.Lock()
        self._local = threading.local()
    
    def __call__(self, name:str|None=None):
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

def getScaleLog(size:int) -> int:
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

class CacheManagerImpl:
    """キャッシュ管理実装"""
    def __init__(self):
        # キャッシュ目次
        self._cachedIndex       = {}            # 全キャッシュ目次 {id:policy}
        self._memCachedIndex    = OrderedDict() # メモリキャッシュ目次(LRU) {id:((scale,page,index) or value or data, (dims,dtype,size,ctype))}
        self._storagedIndex     = {}            # ストレージキャッシュ目次 {id:boolean or (value or data, (dims,dtype,size,ctype))}

        # キャッシュ本体
        self._objectCache       = {}            # オブジェクトキャッシュ {id:data}
        self._memCachePage      = []            # メモリキャッシュページ [page:numpy配列 uint8 * BLOCK_CACHE_PAGE_SIZE * MAX_BLOCK_SIZE_BYTES]
        self._storageDir        = None          # ストレージキャッシュディレクトリ
        
        # キャッシュ操作
        self._memCacheEvent     = {}            # メモリキャッシュ使用通知 {id:lastTime}

        # キャッシュ管理
        self._memCacheRemovable = OrderedDict() # 削除可能キャッシュ(LRU) {id:lastTime} スケール外は実体無し保存用
        self._memCacheBitmap    = 0             # 使用中メモリキャッシュbitmap 0/1=未使用/使用
        self._memCachePageCnt   = 0             # メモリキャッシュページ数

        self._cacheLock         = LockWrapper() # 時間計測機能付きロック
        
        # 後始末関数登録状態
        self._cleanupRegistered = False
        
        # 統計情報
        self._save1Count       = 0       # メモリに保存した回数
    
    def _getGlobelTempDir(self) -> str:
        """キャッシュディレクトリを取得"""
        if self._storageDir is None:
            # 初回だけクリーンアップの実施と終了時の登録を行う
            atexit.register(self._cleanupOldTempDirs)
            self._cleanupOldTempDirs()
            self._cleanupRegistered = True

            # 初回だけテンポラリディレクトリを作製する
            cahedir = os.path.join(os.path.expanduser("~"), ".hoshinone", "cache")
            os.makedirs( cahedir, exist_ok=True)
            self._storageDir = tempfile.mkdtemp( dir=cahedir, prefix="FlowData_")
        
        return self._storageDir
    
    def _cleanupOldTempDirs(self):
        """古いテンポラリディレクトリを削除"""
        try:
            tempRoot = os.path.join(os.path.expanduser("~"), ".hoshinone", "cache")
            currentTime = time.time()
            
            if self._storageDir:
                shutil.rmtree(self._storageDir, ignore_errors=True) # 現在のテンポラリディレクトリを削除

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
            Debug.log(self.__class__.__name__, "Warning: Failed to clean up temporary directories.")
    
    def get(self, cacheKey:str) -> np.ndarray|None:
        """キャッシュから取得"""
        CacheManager._getCount += 1
        return CacheManager.elapsed( self._get, cacheKey)

    def _get(self, cacheKey:str) -> np.ndarray|None:
        start = time.perf_counter_ns()
        with self._cacheLock("CacheManager._get.locked.A"):
            t = time.perf_counter_ns() - start
            if 1000 < t:
                CacheManager.elapsedLogging("CacheManager._get.locked.A lock waitting", t)
            loadStorage = False
            if cacheKey in self._objectCache:
                # オブジェクトキャッシュにあるので採用
                CacheManager._cacheHitCount += 1
                data = self._objectCache[cacheKey]
                return data
            elif cacheKey in self._memCachedIndex:
                # メモリキャッシュにあるので採用
                CacheManager._cacheHitCount += 1
                pos, meta = self._memCachedIndex[cacheKey]
                dims, dtype, size, ctype = meta
                if CType.ALL == ctype:
                    import numpy as np
                    value = pos
                    data = np.full(dims, value, dtype=dtype)
                elif CType.TINY == ctype:
                    data = pos
                else:
                    scale, page, index = pos
                    s = 1<<scale
                    pageBody = self._memCachePage[page]
                    pageBody = pageBody.reshape(BLOCK_CACHE_PAGE_SIZE//s, CACHE_BLOCK_SIZE_BYTES*s)
                    data = pageBody[index,:size].view(dtype).reshape(dims)
                    self._memCacheEvent[cacheKey] = time.perf_counter_ns() # LRU の順序を更新
                return data
            else:
                loadStorage = self._storagedIndex[cacheKey] if cacheKey in self._storagedIndex else False

        if True == loadStorage:
            # ストレージに在るので復元してメモリキャッシュに復帰
            CacheManager._loadCount += 1
            data = self._loadFromStorage(cacheKey)
            
            if not data is None:
                with self._cacheLock():
                    objectCacheCount = len(self._objectCache)
                
                if 1000 <= objectCacheCount:
                    # メモリキャッシュへの遅延書き込みが間に合っていないので少し待つ
                    # 1000:0.0010s, 1200:0.0073s 1400:0.053s 1800:2.8s
                    time.sleep(0.001*(1.01**(objectCacheCount-1000)))
                
                with self._cacheLock("CacheManager._get.locked.B"):
                    self.__set(cacheKey, data, CachePolicy.PERSISTENT) # メモリキャッシュに復帰
            else:
                #ここには来ないはず
                pass
            return data
        elif isinstance(loadStorage, tuple):
            # meta からのデータ復元
            CacheManager._loadCount += 1
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
            CacheManager._recalculateCount += 1
            return None
    
    def set(self, cacheKey:str, data:np.ndarray, cachePolicy:str=CachePolicy.CALCULABLE):
        """キャッシュに保存"""
        with self._cacheLock():
            objectCacheCount = len(self._objectCache)
        
        if 1000 <= objectCacheCount:
            # メモリキャッシュへの遅延書き込みが間に合っていないので少し待つ
            # 1000:0.0010s, 1200:0.0073s 1400:0.053s 1800:2.8s
            time.sleep(0.001*(1.01**(objectCacheCount-1000)))
        
        CacheManager._setCount += 1
        return CacheManager.elapsed( self._set, cacheKey, data, cachePolicy)

    def _set(self, cacheKey:str, data:np.ndarray, cachePolicy:str=CachePolicy.CALCULABLE):
        start = time.perf_counter_ns()
        with self._cacheLock("CacheManager._set.locked.A"):
            t = time.perf_counter_ns() - start
            if 1000 < t:
                CacheManager.elapsedLogging("CacheManager._set.locked.A lock waitting", t)
            self.__set(cacheKey, data, cachePolicy)

    def __set(self, cacheKey:str, data:np.ndarray, cachePolicy:str=CachePolicy.CALCULABLE):
        self._cachedIndex[cacheKey] = cachePolicy
        self._objectCache[cacheKey] = data
        
        if 100 <= len(self._objectCache):
            CoalescingExecutor.submit(self._lazySave1, self._lazySave1) # メモリキャッシュへの遅延書き込み

    def _lazySave1(self):
        """
        メモリキャッシュへの遅延書き込み
        ここはシングルスレッドで実行される。
        メインスレッドとの競合を避ける為に、ロック時間を最小にする。
        """
        import numpy as np
        
        with self._cacheLock("CacheManager._lazySave1.locked.A"):
            # イベントの在ったキャッシュの LRU 順序を更新する
            for cacheKey in self._memCacheEvent:
                if cacheKey in self._memCachedIndex:
                    self._memCachedIndex.move_to_end(cacheKey) # 最後尾に移動(LRU)
                if cacheKey in self._memCacheRemovable:
                    self._memCacheRemovable[cacheKey] = self._memCacheEvent[cacheKey]
                    self._memCacheRemovable.move_to_end(cacheKey) # 最後尾に移動(LRU)
            self._memCacheEvent.clear()
        
        while True:
            # メインスレッドを可能な限り止めない為に、
            # このスレッドではロック時間を最小にする。
            # 大きなメモリ操作などはロックの外で行う。
            with self._cacheLock("CacheManager._lazySave1.locked.B"):
                if not self._objectCache:
                    break
                
                cacheKey, data = next(iter(self._objectCache.items()))
                cachePolicy = self._cachedIndex[cacheKey]
            dims  = data.shape
            dtype = data.dtype
            size  = data.nbytes
            value = data.ravel()[0]
            if np.isnan(data).all() or (data == value).all():
                # 配列の全要素が同じなので値だけ保存する
                ctype = CType.ALL
                pos   = value.item()
            elif size <= CACHE_BLOCK_SIZE_BYTES // 256:
                # 配列の小さいのでデータのまま保存する
                ctype = CType.TINY
                pos   = data
            else:
                ctype = CType.NORMAL
                pos   = None
            
            meta = (dims, dtype, size, ctype)
            if CType.ALL == ctype or CType.TINY == ctype:
                # データを保存する
                scale = -1

                time.sleep(0) # 連続的にロックするのを抑制する
                with self._cacheLock("CacheManager._lazySave1.locked.C"):
                    CacheManager._save1Count += 1
                    self._save1Count += 1
                    self._objectCache.pop(cacheKey, None)
                    self._memCachedIndex[cacheKey] = (pos, meta)
                    
                    if CachePolicy.PERSISTENT != cachePolicy:
                        self._memCacheRemovable[cacheKey] = time.perf_counter_ns()
            else:
                scale      = getScaleLog(size)
                createPage = None
                pos        = None
                while not pos:
                    time.sleep(0) # 連続的にロックするのを抑制する
                    with self._cacheLock("CacheManager._lazySave1.locked.D"):
                        pos = self._memCacheFindFree(scale)
                        if pos:
                            # 空きが有るので採用
                            scale, page, index = pos
                            self._memCacheUse(scale, page, index)
                            if len(self._memCachePage) <= page:
                                createPage = page
                            else:
                                createPage = None
                        elif not self._memCacheRemovable:
                            # 空きが無く、削除出来るデータも無いので、ストレージキャッシュへの遅延書き込みが進むのを待つ
                            createPage = None
                            pos        = None
                            break
                        else:
                            # 空きが無いので、古い方から削除出来るデータ探す
                            createPage = None
                            oldKey, oldLast = self._memCacheRemovable.popitem(last=False)
                            oldPos, oldMeta = self._memCachedIndex.pop(oldKey)
                            oldPolicy       = self._cachedIndex[oldKey]
                            oldDims, oldDtype, oldSize, oldCtype = oldMeta

                            if oldKey in self._memCacheEvent:
                                # 最近イベントが在ったようなので、プッシュバックして中断する
                                self._memCachedIndex[oldKey] = (oldPos, oldMeta)
                                self._memCacheRemovable[oldKey] = self._memCacheEvent.pop(oldKey)
                                pos = None
                            else:
                                if CachePolicy.PERSISTENT != oldPolicy:
                                    # ポリシー persistent ではないのでキャッシュから削除
                                    CacheManager._purgeCount += 1
                                    self._cachedIndex.pop(oldKey)
                                
                                if CType.ALL == oldCtype or CType.TINY == oldCtype:
                                    # データ保存なので、メモリキャッシュの解放は不要
                                    pass
                                else:
                                    oldScale, oldPage, oldIndex = oldPos
                                
                                    if oldScale == scale:
                                        # 同じスケールに削除出来るデータが有るので再利用する
                                        pos = oldPos
                                        break
                                    else:
                                        # 他のスケールに削除出来るデータが有るので解放する
                                        oldDims, oldDtype, oldSize, oldCtype = oldMeta
                                        if CType.ALL == oldCtype or CType.TINY == oldCtype:
                                            pass
                                        else:
                                            # メモリキャッシュの解放
                                            oldScale, oldPage, oldIndex = oldPos
                                            self._memCacheFree(oldScale, oldPage, oldIndex)
                
                if not createPage is None:
                    # 新しいページなので、新規作成
                    pageBody = np.empty((BLOCK_CACHE_PAGE_SIZE*CACHE_BLOCK_SIZE_BYTES), dtype=np.uint8)
                    with self._cacheLock("CacheManager._lazySave1.locked.E"):
                        if len(self._memCachePage) <= createPage:
                            self._memCachePage.append(pageBody) # ページ作成
                            self._memCachePageCnt += 1
                
                if not pos:
                    # 空が無かったのでストレージキャッシュへの遅延書き込みが進むのを待つ
                    CoalescingExecutor.submit(self._lazySave2, self._lazySave2) # ストレージキャッシュへの遅延書き込み
                    time.sleep(0.1)
                else:
                    scale, page, index = pos
                    s = 1<<scale
                    pageBody = self._memCachePage[page]
                    pageBody = pageBody.reshape(BLOCK_CACHE_PAGE_SIZE//s, CACHE_BLOCK_SIZE_BYTES*s)
                    pageBody[index, :size] = data.reshape(-1).view(np.uint8) # メモリキャッシュへ書き込み
                    
                    with self._cacheLock("CacheManager._lazySave1.locked.E"):
                        CacheManager._save1Count += 1
                        self._save1Count += 1
                        self._objectCache.pop(cacheKey, None)
                        self._memCachedIndex[cacheKey] = (pos, meta)
                        if CachePolicy.PERSISTENT != cachePolicy:
                            self._memCacheRemovable[cacheKey] = time.perf_counter_ns()
                        if(   (BLOCK_CACHE_PAGE_SIZE*MAX_CACHE_PAGES*95//100) < self._memCacheBitmap.bit_count()
                          and 0 == self._save1Count % (BLOCK_CACHE_PAGE_SIZE//8)
                          ):
                            # 空きが5%以下に成ったのでストレージキャッシュを開始
                            CoalescingExecutor.submit(self._lazySave2, self._lazySave2) # ストレージキャッシュへの遅延書き込み
                    time.sleep(0) # 連続的にロックするのを抑制する
    
    def _lazySave2(self):
        """
        ストレージキャッシュへの遅延書き込み
        ここはシングルスレッドで実行される。
        メインスレッドとの競合を避ける為に、ロック時間を最小にする。
        """
        # 古いデータから連続する PERSISTENT を抽出する
        end = False
        req = {}
        step = BLOCK_CACHE_PAGE_SIZE // 8
        for s in range(0, BLOCK_CACHE_PAGE_SIZE, step): # 古いデータから1ページ分を検索する
            with self._cacheLock("CacheManager._lazySave2.locked.A"):
                for i, cacheKey in enumerate(self._memCachedIndex.keys()):
                    if s + step <= i:
                        end = True
                        break
                    elif i < s:
                        pass
                    elif CachePolicy.PERSISTENT != self._cachedIndex.get(cacheKey, None):
                        end = True
                        break
                    
                    pos, meta = self._memCachedIndex[cacheKey]
                    dims, dtype, size, ctype = meta
                    if CType.ALL == ctype or CType.TINY == ctype:
                        scale, page, index = (-1, None, None)
                        if cacheKey in self._memCacheRemovable:
                            # 既に削除可能なので何もしない
                            pass
                        else:
                            # データ保持なので即時削除可能
                            CacheManager._save2Count += 1
                            self._storagedIndex[cacheKey] = (pos, meta)
                            req[cacheKey] = (scale, True)
                    else:
                        scale, page, index = pos
                        if cacheKey in self._memCacheRemovable:
                            # 既に削除可能なので何もしない
                            pass
                        elif cacheKey in self._storagedIndex:
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
                with self._cacheLock("CacheManager._lazySave2.locked.B"):
                    if cacheKey in self._memCachedIndex:
                        lastTime = next(iter(self._memCacheRemovable.values())) if self._memCacheRemovable else time.perf_counter_ns()
                        self._memCacheRemovable[cacheKey] = lastTime
                        self._memCacheRemovable.move_to_end(cacheKey, last=False) # 先頭に移動(LRU)
            else:
                with self._cacheLock("CacheManager._lazySave2.locked.C"):
                    if cacheKey in self._memCachedIndex:
                        pos, meta = self._memCachedIndex[cacheKey]
                        scale, page, index = pos
                        dims, dtype, size, ctype = meta
                        s = 1<<scale
                        pageBody = self._memCachePage[page]
                        pageBody = pageBody.reshape(BLOCK_CACHE_PAGE_SIZE//s, CACHE_BLOCK_SIZE_BYTES*s)
                        data = pageBody[index,:size].view(dtype).reshape(dims)
                    else:
                        data = None
                
                if (not data is None) and self._saveToStorage(cacheKey, data): # ストレージへ書き込み
                    # 書き込み成功
                    with self._cacheLock("CacheManager._lazySave2.locked.D"):
                        if cacheKey in self._memCachedIndex:
                            CacheManager._save2Count += 1
                            self._storagedIndex[cacheKey] = True
                            lastTime = next(iter(self._memCacheRemovable.values())) if self._memCacheRemovable else time.perf_counter_ns()
                            self._memCacheRemovable[cacheKey] = lastTime
                            self._memCacheRemovable.move_to_end(cacheKey, last=False) # 先頭に移動(LRU)
            time.sleep(0) # 連続的にロックするのを抑制する

    def isCached(self, cacheKey:str) -> bool:
        """キャッシュされているかどうかを判定"""
        start = time.perf_counter_ns()
        with self._cacheLock("CacheManager.isCached.locked.A"):
            t = time.perf_counter_ns() - start
            if 1000 < t:
                CacheManager.elapsedLogging("CacheManager.isCached lock waitting", t)
            if cacheKey in self._cachedIndex:
                self._memCacheEvent[cacheKey] = time.perf_counter_ns() # LRU の順序を更新
                return True
            else:
                return False

    def _saveToStorage(self, cacheKey:str, data:np.ndarray) -> bool:
        """ストレージに退避"""
        import numpy as np

        try:
            tempDir = self._getGlobelTempDir()

            filename = f"{cacheKey}".replace("/", "_").replace("\\", "_").replace(":", "_")
            pre = filename[:2]
            subDir = os.path.join( tempDir, pre)
            os.makedirs(subDir, exist_ok=True)
            
            fileName = os.path.join(subDir, f"{filename}.npy")
            CacheManager.elapsed(np.save, fileName, data, allow_pickle=False)
            
            return True
        except (OSError, IOError, ValueError):
            from utils.Debug import Debug
            Debug.log(self.__class__.__name__, f"Warning: Unable to save block data to storage : key: {cacheKey}")
            return False
    
    def _loadFromStorage(self, cacheKey:str) -> np.ndarray|None:
        """ストレージから復元"""
        import numpy as np
        
        try:
            if self._storageDir is None:
                return None
            
            filename = f"{cacheKey}".replace("/", "_").replace("\\", "_").replace(":", "_")
            pre = filename[:2]
            subDir = os.path.join( self._storageDir, pre)
            
            fileName = os.path.join(subDir, f"{filename}.npy")
            data = CacheManager.elapsed(np.load, fileName, allow_pickle=False)
            
            return data
        except (OSError, IOError, ValueError):
            from utils.Debug import Debug
            Debug.log(self.__class__.__name__, f"Warning: Unable to load block data from storage : key: {cacheKey}")
            return None
    
    def clearByPartialKey(self, cacheKey:str):
        """key の部分一致でデータを削除"""
        # ストレージを削除
        if self._storageDir and os.path.exists(self._storageDir):
            pre = cacheKey[:2]
            subDir = os.path.join( self._storageDir, pre)
            if os.path.exists(subDir):
                for fileName in os.listdir(subDir):
                    basename, ext = os.path.splitext(fileName)
                    if cacheKey in basename and ext in [".pkl", ".npy"]:
                        # ファイルを削除
                        os.remove(os.path.join(subDir, fileName))
        
        with self._cacheLock("CacheManager.clearByPartialKey.locked.A"):
            # キャッシュを削除
            self._clearByPartialKey(self._storagedIndex, cacheKey)
            values = self._clearByPartialKey(self._memCachedIndex, cacheKey)
            for pos, meta in values:
                (dims, dtype, size, ctype) = meta
                if CType.ALL == ctype or CType.TINY == ctype:
                    pass
                else:
                    scale, page, index = pos
                    self._memCacheFree(scale, page, index)
            self._clearByPartialKey(self._memCacheRemovable, cacheKey) 
            self._clearByPartialKey(self._cachedIndex      , cacheKey)
            self._clearByPartialKey(self._objectCache      , cacheKey)
    
    def _clearByPartialKey(self, cache:dict, cacheKey:str) -> list:
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
    
    # _memCacheBitmap 用ビット定義  [0]=11....11, [0]=0101....0101, [0]=00010001....00010001
    _scaleBit = [0 for s in range(END_SCALE)]
    for i in range(MAX_CACHE_PAGES):
        _scaleBit[END_SCALE-1] |= 1 << (BLOCK_CACHE_PAGE_SIZE * i)
    for i in range(END_SCALE-1, 0, -1):
        _scaleBit[i-1] = _scaleBit[i] | _scaleBit[i] << (BLOCK_CACHE_PAGE_SIZE >> (END_SCALE-i))
    
    PAGE_SHIFT = (BLOCK_CACHE_PAGE_SIZE).bit_length() - 1
    PAGE_MASK  = BLOCK_CACHE_PAGE_SIZE - 1
    
    def _memCacheFindFree(self, scale:int) -> tuple[int,int,int]|None:
        """
        空いているメモリキャッシュ位置を検索

        _memCacheBitmap の解説
        メモリキャッシュの使用状態を表す。
        1:使用中
        0:未使用
        各スケールでメモリキャッシュの実体は共有なので、
        使用状態は各スケールで連動している必要がある
        
        prams:
            scale:スケール指数
        
        returns:
            (scale, page, index) or None
        """
        bitmap = ~self._memCacheBitmap
        if 0==scale:
            bitmap = bitmap & self._scaleBit[0]
            if 0==bitmap:
                return None
            x = bitmap & -bitmap   # 最下位の 1 を取得
            i = x.bit_length() - 1 # 最下位の 1 の位置を取得
            page = i >> self.PAGE_SHIFT
            index = i & self.PAGE_MASK
            return (scale, page, index)
        elif 1==scale:
            bitmap &= bitmap >> 1
            bitmap = bitmap & self._scaleBit[1]
            if 0==bitmap:
                return None
            
            x = bitmap & -bitmap   # 最下位の 1 を取得
            i = x.bit_length() - 1 # 最下位の 1 の位置を取得
            page = i >> self.PAGE_SHIFT
            index = (i & self.PAGE_MASK) >> 1
            return (scale, page, index)
        else:
            # 一般化
            for i in range(scale):
                bitmap &= bitmap >> (1<<i)
            
            bitmap = bitmap & self._scaleBit[scale]
            if 0==bitmap:
                return None
            
            x = bitmap & -bitmap   # 最下位の 1 を取得
            i = x.bit_length() - 1 # 最下位の 1 の位置を取得
            page = i >> self.PAGE_SHIFT
            index = (i & self.PAGE_MASK) >> scale
            return (scale, page, index)
    
    def _memCacheUse(self, scale:int, page:int, index:int):
        """メモリキャッシュ使用中にセット"""
        if 0==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + index
            bit = 1 << i
            self._memCacheBitmap |= bit
        elif 1==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << 1)
            bit = 3 << i
            self._memCacheBitmap |= bit
        else:
            # 一般化
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << scale)
            bit = (1<<(1<<scale)) - 1
            bit = bit << i
            self._memCacheBitmap |= bit
    
    def _memCacheFree(self, scale:int, page:int, index:int):
        """メモリキャッシュ使用中を解放"""
        if 0==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + index
            bit = 1 << i
            self._memCacheBitmap &= ~bit
        elif 1==scale:
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << 1)
            bit = 3 << i
            self._memCacheBitmap &= ~bit
        else:
            # 一般化
            i = page * BLOCK_CACHE_PAGE_SIZE + (index << scale)
            bit = (1<<(1<<scale)) - 1
            bit = bit << i
            self._memCach似合ってますeBitmap &= ~bit

class CacheManager:
    """キャッシュ管理クラス"""
    instance = CacheManagerImpl() # キャッシュ管理 シングルトン
    
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
    def get(cls, cacheKey:str) -> np.ndarray|None:
        return cls.instance.get(cacheKey)
    
    @classmethod
    def set(cls, cacheKey:str, data:np.ndarray, cachePolicy:str=CachePolicy.CALCULABLE):
        return cls.instance.set(cacheKey, data, cachePolicy)
    
    @classmethod
    def isCached(cls, cacheKey:str) -> bool:
        return cls.instance.isCached(cacheKey)
    
    @classmethod
    def clearByPartialKey(cls, cacheKey:str):
        cls.instance.clearByPartialKey(cacheKey)
    
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
    def elapsedLogging(cls, name:str, elapsed_ns:int):
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
            cacheCount = len(cls.instance._cachedIndex)
            
            key = None
            x   = 0
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
    def getCacheStats(cls) -> tuple:
        """キャッシュ量とストレージ使用量を取得"""
        objCacheCount    = len(cls.instance._objectCache)
        cacheCount       = len(cls.instance._memCachedIndex)
        cacheSize        = cacheCount * CACHE_BLOCK_SIZE_BYTES
        storageCount     = len(cls.instance._storagedIndex)
        storageSize      = storageCount * CACHE_BLOCK_SIZE_BYTES
        return (objCacheCount, cacheCount, cacheSize, storageCount, storageSize,
                cls._getCount, cls._cacheHitCount, cls._recalculateCount, cls._loadCount,
                cls._setCount, cls._purgeCount, cls._save1Count, cls._save2Count,
                cls._elapsedHis)
