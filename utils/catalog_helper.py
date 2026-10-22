'''
catalog_helper - 星カタログ読み込みおよび天球幾何計算ユーティリティ

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING, Any

import os

if TYPE_CHECKING:
    import numpy as np
    from scipy.spatial import KDTree

# カタログ配列の index 定義
IDX, RA, DEC, MAG = 0, 1, 2, 3

class Catalog:
    """星カタログのパース、キャッシュ管理、および幾何計算を行うユーティリティ"""
    _cachedSymbol    = None
    _cachedPath      = None
    _cachedCatalog   = None
    _cachedIds       = None
    _cachedRatioTree = None
    _cachedIdMap     = None
    _cachedValues    = None

    def __init__(self, symbol:str|None=None, catalog:np.ndarray|None=None):
        if symbol is None and catalog is None:
            from config import CATALOG_PATH
            symbol, filePath = CATALOG_PATH
            self.loadCatalog(symbol, filePath)
            assert not self._symbol    is None
            assert not self._path      is None
            assert not self._catalog   is None
            assert not self._ids       is None
            assert not self._ratioTree is None
            assert not self._idxMap    is None
            assert not self._values    is None
        else:
            assert not symbol is None and not catalog is None, "symbol and catalog must be specified together."
            self._symbol  = symbol
            self._path    = None
            self._catalog = catalog
            self._ids     = None
            ratioTree, idxMap, values = self.generateTriangleDatabase(symbol, catalog)
            self._ratioTree = ratioTree
            self._idxMap    = idxMap
            self._values    = values
            assert not self._ratioTree is None
            assert not self._idxMap    is None
            assert not self._values    is None
        
        # セルフテスト
        import numpy as np
        random = np.random.default_rng(2725) # 固定シードで再現性確保
        testCnt = 100
        errCnt = 0
        errMsg = None
        for _ in range(testCnt):
            s  = random.uniform(0.001, 10.0)  # 相似比
            n0 = random.uniform(0.999, 1.001) # ノイズ
            n1 = random.uniform(0.999, 1.001) # ノイズ
            n2 = random.uniform(0.999, 1.001) # ノイズ
            
            # ケース
            prm = random.choice(3)
            tidx = random.choice(len(self._values))
            roll = random.choice(3)
            cidx = self._values[tidx]
            cidx = np.roll(cidx, roll)
            re = random.uniform(0.002, 0.012)
            
            c0idx, c1idx, c2idx = cidx
            c0 = self._catalog[c0idx]
            c1 = self._catalog[c1idx]
            c2 = self._catalog[c2idx]
            c01d = self.angularDistance(c0[RA-1:DEC], c1[RA-1:DEC])
            c12d = self.angularDistance(c1[RA-1:DEC], c2[RA-1:DEC])
            c20d = self.angularDistance(c2[RA-1:DEC], c0[RA-1:DEC])
            
            if np.abs(1 - c01d/c12d) < 0.01: continue # 2辺の差がノイズより小さいのでパス
            if np.abs(1 - c12d/c20d) < 0.01: continue # 2辺の差がノイズより小さいのでパス
            if np.abs(1 - c20d/c01d) < 0.01: continue # 2辺の差がノイズより小さいのでパス
            
            _c01d, _c12d, _c20d = c01d*s*n0, c12d*s*n1, c20d*s*n2 # 外乱を混入
            
            # 実行
            if   0==prm: c = self.searchTriangle(_c01d, _c12d, _c20d, re)
            elif 1==prm: c = self.searchTriangle(_c01d, _c12d, _c20d, re, fixVertexIdx=(None,c1idx,None ))
            else       : c = self.searchTriangle(_c01d, _c12d, _c20d, re, fixVertexIdx=(None,c1idx,c2idx))
            
            # チェック
            chk0 = (c[:, 0, IDX] == c0idx)
            chk1 = (c[:, 1, IDX] == c1idx)
            chk2 = (c[:, 2, IDX] == c2idx)
            chk = chk0 & chk1 & chk2
            if not np.any(chk):
                errCnt += 1
                errMsg = ( f"Triangle search error: {_c01d:0.3f}, {_c12d:0.3f}, {_c20d:0.3f} {re:0.3f}"
                         +  " |"
                         + f" idx:{str(cidx)}"
                         + f" s:{s:0.3f} noise:{n0:0.6f} {n1:0.6f} {n2:0.6f}"
                         + f" error:{np.linalg.norm(self._makeKey([ c01d,  c12d,  c20d], [0, 1, 2])[0]
                                                   -self._makeKey([_c01d, _c12d, _c20d], [0, 1, 2])[0]):0.6f}"
                         + f" r:{np.linalg.norm(self._makeKey([_c01d, _c12d, _c20d], [0, 1, 2])[0]) * re:0.6f}"
                )
        
        assert 0==errCnt, f"Self test {errCnt}/{testCnt}: {errMsg}"
    
    def loadCatalog(self, symbol:str, filePath:str):
        """
        カタログファイルを読み込み
        
        Args:
            symbol: カタログシンボル
            filePath: カタログファイルパス        
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from config import CATALOG_HEADERS
        
        if self._cachedCatalog is not None and filePath == self._cachedPath: # キャッシュが有効な場合
            return self._cachedCatalog
        
        if not os.path.exists(filePath):
            raise FileNotFoundError(f"Catalog file not found: {filePath}")
        
        # キャッシュパス
        cachePath = os.path.splitext(filePath)[0] + ".npz"
        
        if(   self._cachedSymbol == symbol
          and self._cachedPath   == cachePath
          and self._cachedCatalog   is not None
          and self._cachedIds       is not None
          and self._cachedRatioTree is not None
          and self._cachedIdMap     is not None
          and self._cachedValues    is not None
          and os.path.exists(cachePath)
          and os.path.getmtime(filePath) < os.path.getmtime(cachePath)
          ):
            self._symbol    = self._cachedSymbol
            self._path      = self._cachedPath
            self._catalog   = self._cachedCatalog
            self._ids       = self._cachedIds
            self._ratioTree = self._cachedRatioTree
            self._idxMap    = self._cachedIdMap
            self._values    = self._cachedValues
        elif(   os.path.exists(cachePath)
            and os.path.getmtime(filePath) <= os.path.getmtime(cachePath)
            ):
            # キャッシュが存在し元ファイルより新しいので、キャッシュからロード
            cacheFile = np.load(cachePath, allow_pickle=True)
            self._cachedSymbol    = symbol
            self._cachedPath      = filePath
            self._cachedCatalog   = cacheFile["catalog"]           if "catalog"    in cacheFile else None
            self._cachedIds       = cacheFile["ids"]               if "ids"        in cacheFile else None
            self._cachedRatioTree = cacheFile["ratioTreee"].item() if "ratioTreee" in cacheFile else None
            self._cachedIdMap     = cacheFile["idxMap"].item()     if "idxMap"     in cacheFile else None
            self._cachedValues    = cacheFile["values"]            if "values"     in cacheFile else None
            self._symbol    = self._cachedSymbol
            self._path      = self._cachedPath
            self._catalog   = self._cachedCatalog
            self._ids       = self._cachedIds
            self._ratioTree = self._cachedRatioTree
            self._idxMap    = self._cachedIdMap
            self._values    = self._cachedValues
        else:
            pass

        if(  self._cachedCatalog   is None
          or self._cachedIds       is None
          ):
            # 元ファイル(TSV)からパース
            from utils.Debug import Debug
            Debug.log(self.__class__.__name__, f"load {symbol}")
            catalog = []
            ids     = []
            with open(filePath, "r", encoding="utf-8") as f:
                pos = {}
                for line in f:
                    if not line or not line.strip() or line.startswith("#"): # コメント行なので、スキップ
                        continue
                    
                    items = line.strip().split("\t")
                    
                    # ヘッダ読み込み
                    # 位置情報収集
                    for name,key in CATALOG_HEADERS:
                        if key in items:
                            idx = items.index(key)
                            pos[name] = idx
                    break
                
                names = ("ID", "RA", "Dec", "Mag") # 読み込むデータ名(CATALOG_HEADERS)
                maxIdx = max([pos[name] for name in names])
                
                for line in f:
                    if not line or not line.strip() or line.startswith("#"): # コメント行なので、スキップ
                        continue
                    
                    items = line.strip().split("\t")
                    if len(items) <= maxIdx: # 項目が足りないのでスキップ
                        from utils.Debug import Debug
                        Debug.log(self.__class__.__name__, f"skip: {line}")
                        continue
                    
                    data = []
                    for name in names:
                        data.append(items[pos[name]].strip())
                    
                    try:
                        for i in range(len(data)):
                            if 1<=i:
                                data[i] = float(data[i])
                        catalog.append(data[1:])
                        ids.append(symbol+data[0])
                    except ValueError:
                        Debug.log(self.__class__.__name__, f"ValueError: {line}")
                        continue
            
            catalog = nh.array(catalog)
            ids     = np.array(ids, dtype='object')
            
            self._cachedSymbol    = symbol
            self._cachedPath      = filePath
            self._cachedCatalog   = catalog
            self._cachedIds       = ids
            self._cachedRatioTree = None
            self._cachedIdMap     = None
            self._cachedValues    = None
            self._symbol    = self._cachedSymbol
            self._path      = self._cachedPath
            self._catalog   = self._cachedCatalog
            self._ids       = self._cachedIds
            self._ratioTree = None
            self._idMap     = None
            self._values    = None
            
        if(  self._cachedRatioTree is None
          or self._cachedIdMap     is None
          or self._cachedValues    is None
          ):
            # 検索辞書作成
            ratioTreee, idxMap, values = self.generateTriangleDatabase(symbol, self._cachedCatalog)
            
            self._cachedRatioTree = ratioTreee
            self._cachedIdMap     = idxMap
            self._cachedValues    = values
            self._ratioTree = self._cachedRatioTree
            self._idxMap    = self._cachedIdMap
            self._values    = self._cachedValues
            
            # 次回高速化のためにキャッシュ保存
            try:
                np.savez(cachePath, catalog=catalog, ids=ids, ratioTreee=ratioTreee, idxMap=idxMap, values=values, allow_pickle=True)
            except Exception:
                from utils.Debug import Debug
                Debug.log(self.__class__.__name__, "Warning: Save catalog cache failed.")
    
    def generateTriangleDatabase(self, symbol:str, catalog:np.ndarray) -> tuple[KDTree, dict, np.ndarray]:
        """三角形データベースの生成"""
        from config import CATALOG_DB_MAG, CATALOG_DB_NUM
        
        if catalog is None or 0 == len(catalog):
            return (None,None,None)

        # 統計情報の生成
        import numpy as np
        from scipy.spatial import KDTree
        from utils import numpy_helpers as nh
        from utils.Debug import Debug
        Debug.log(self.__class__.__name__, f" {symbol} [{len(catalog)} stars]")
        
        # 等級の10%毎のパーセンタイル
        p  = list(range(0, 101, 10))
        pS = " ".join(["%4d" % x for x in p])
        mag  = np.percentile(catalog[:, MAG-1], p)
        magS = " ".join(["%4.1f" % x for x in mag])
        Debug.log(self.__class__.__name__, f"         {pS}%")
        Debug.log(self.__class__.__name__, f"Mag: 0%: {magS} :100%")
        
        # 等級,画角毎に見える星の数の中央値
        magRad = []
        radius  = [1,2,4,8,16,32,64,128,180]
        radiusS = " ".join(["%5d"%(x) for x in radius])
        Debug.log(self.__class__.__name__, f"                    {radiusS}deg")
        random = np.random.default_rng(2725) # 固定シードで再現性確保
        for mag in range(9):
            count  = []
            for r in radius:
                s = []
                for i in range(100):
                    ra     = random.uniform(0, 360)     # RA は均等
                    sinDec = random.uniform(-1.0, 1.0)  # sin(-90°)=-1, sin(90°)=1
                    dec    = np.degrees(np.arcsin(sinDec)) # Dec は sin(Dec) 空間で一様分布させてから arcsin で戻す
                    s.append(len(self.queryStars( ra, dec, r, mag)))
                count.append(np.median(s))
            magRad.append([(r, n) for r, n in zip(radius, count)])

            countS = " ".join(["%5d"%(x) for x in count])
            Debug.log(self.__class__.__name__, f"Count: Mag {mag:2d} 1deg: {countS} :180deg")
        
        # 画角の中央に8等星までの星を置く
        # 自身より明るい CATALOG_DB_NUM 以上の星が見える画角の大きさを探す
        # 自身と他の星の総組み合わせで三角比のを作り kd-tree を作成する。
        #
        # データサイズは CATALOG_DB_NUM に対し nC2 で増え、
        # 8等星(CATALOG_DB_MAG = 8.0)までの星が 38,000 程度ある。
        # CATALOG_DB_NUM = 5 だと三角形の数は 5C2 * 38,000 = 380,000 ですが、「CATALOG_DB_NUM 以上」なので 970,000 程度(num=7～8)になる。
        # メモリ量は
        # kd-tree が 970,000 * (4 + 4)     =  7,764,000 これにオーバーヘッドが加わり 47 MB 程度になる。
        # idx map が 970,000 * (4 + 4 + 4) = 11,640,000 これにオーバーヘッドが加わり 14 MB 程度になる。
        # values  が 970,000 * (4 + 4 + 4) = 11,640,000 でこれはほぼこのまま。
        #
        # 同様に、8等星まで CATALOG_DB_NUM = 10 だと、10C2 * 38,000 = 1,710,000
        # 三角形の数   4,000,000 (num=14～15)
        # kd-tree   162 MB
        # idx map    49 MB
        # values     45 MB
        keys   = []
        values = []
        indices = np.where(catalog[:, MAG-1] <= CATALOG_DB_MAG)[0]
        starCount = len(indices)
        progress = 0
        Debug.log(self.__class__.__name__, f"Generate triangle database from {starCount} stars")
        for c0idx in indices:
            progress += 1
            if progress % (starCount//10+1) == 0:
                Debug.log(self.__class__.__name__, f"Progress: {progress}/{starCount} {progress*100//starCount}%  triangles: {len(keys)}")
            
            ra   = catalog[c0idx, RA-1]
            dec  = catalog[c0idx, DEC-1]
            mag  = catalog[c0idx, MAG-1]
            # CATALOG_DB_NUM 以上になる radius
            rn = magRad[max(0, min(len(magRad)-1, int(mag)))]
            radius = list(filter(lambda x: x[1] < CATALOG_DB_NUM, rn))[-1][0]
            selected = self.queryStars(ra, dec, radius, mag)
            while (CATALOG_DB_NUM+1) < len(selected) and 0.9 < radius: # (CATALOG_DB_NUM+1) 未満になるまで絞る
                radius /= 1.41421356237
                selected = self.queryStars(ra, dec, radius, mag)
            while len(selected) < (CATALOG_DB_NUM+1) and radius < 180.0: # (CATALOG_DB_NUM+1) 以上になるまで広げる
                radius *= 1.41421356237
                selected = self.queryStars(ra, dec, radius, mag)
            # 自身と他の星の総組み合わせで三角形をつくる
            other = selected[selected[:, IDX] != c0idx]
            x, y = self.gnomonicProjection(other[:, 1], other[:, 2], ra, dec)
            for j in range(len(other)):
                for k in range(j+1, len(other)):
                    c1idx = int(other[j,IDX])
                    c2idx = int(other[k,IDX])
                    c0 = catalog[c0idx]
                    c1 = catalog[c1idx]
                    c2 = catalog[c2idx]
                    x1, y1 = x[j], y[j]
                    x2, y2 = x[k], y[k]
                    if 0 < ((x1 - 0) * (y2 - 0)) - ((y1 - 0) * (x2 - 0)):
                        c1   , c2    = c2   , c1    # 時計回りに修正
                        c1idx, c2idx = c2idx, c1idx # 時計回りに修正
                    c01d = self.angularDistance(c0[RA-1:DEC], c1[RA-1:DEC])
                    c12d = self.angularDistance(c1[RA-1:DEC], c2[RA-1:DEC])
                    c20d = self.angularDistance(c2[RA-1:DEC], c0[RA-1:DEC])
                    key, cidx = self._makeKey([c01d, c12d, c20d], [c0idx, c1idx, c2idx])
                    keys.append(key)
                    values.append(cidx)
        Debug.log(self.__class__.__name__, f"Total triangle count: {len(keys)}")
        ratioTree = KDTree(nh.array(keys))
        values    = np.array(values, dtype=np.uint32)

        # idx map 作成
        # idx で values を引く
        idxMap = {}
        for idx, (c0idx, c1idx, c2idx) in enumerate(values):
            idxMap.setdefault(c0idx, [[], [], []])[0].append(idx)
            idxMap.setdefault(c1idx, [[], [], []])[1].append(idx)
            idxMap.setdefault(c2idx, [[], [], []])[2].append(idx)
        for cidx in idxMap: 
            idxMap[cidx][0] = np.array(idxMap[cidx][0], dtype=np.uint32)
            idxMap[cidx][1] = np.array(idxMap[cidx][1], dtype=np.uint32)
            idxMap[cidx][2] = np.array(idxMap[cidx][2], dtype=np.uint32)
        
        return (ratioTree, idxMap, values)
    
    def getSymbol(self) -> str:
        """カタログシンボルを取得"""
        assert not self._symbol is None, "Catalog symbol is not set."
        return self._symbol
    
    def count(self) -> int:
        if self._catalog is None:
            return 0
        else:
            return len(self._catalog)
    
    def searchTriangle(self, side01:np.ndarray|float, side12:np.ndarray|float, side20:np.ndarray|float, relativeError:float,
                             magLimit:float|None=None, fixVertexIdx:tuple|list|None=None,
                             outputLimit:int|None=None) -> np.ndarray:
        """
        三角比データベースを検索し、指定された三角形に相似な星の組み合わせを返す

        Args:
            side01: 辺01の長さ
            side12: 辺12の長さ
            side20: 辺20の長さ
            relativeError: 相似比の相対誤差
            magLimit: 等級制限 ( mag )
            fixVertexIdx: 頂点の ID を固定 (idx0,idx1,idx2) or (None,idx1,idx2) or ...
            outputLimit: 出力制限数

        Returns:
            np.ndarray: 星の組み合わせ配列 shape=(N, 3, 4) [[[idx, ra, dec, mag], [idx, ra, dec, mag], [idx, ra, dec, mag]],...]
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        assert(   not self._catalog   is None
              and not self._ratioTree is None
              and not self._idxMap    is None
              and not self._values    is None), "Catalog is not loaded or database is not generated."
        
        key, order = self._makeKey([side01, side12, side20], [0, 1, 2])
        invOrder = np.argsort(order) # 逆引き用
        r = np.linalg.norm(key) * relativeError
        
        if not fixVertexIdx is None:
            # 頂点を固定する
            cidx0, cidx1, cidx2 = fixVertexIdx
            assert not cidx0 is None or not cidx1 is None or not cidx2 is None
            tidx0 = self._idxMap[cidx0][invOrder[0]] if not cidx0 is None else None # key の順序に入れ替え
            tidx1 = self._idxMap[cidx1][invOrder[1]] if not cidx1 is None else None # key の順序に入れ替え
            tidx2 = self._idxMap[cidx2][invOrder[2]] if not cidx2 is None else None # key の順序に入れ替え
            # 共通する idx を抽出
            tidx = tidx0
            tidx = np.intersect1d(tidx, tidx1) if not tidx is None and not tidx1 is None else tidx if not tidx is None else tidx1
            tidx = np.intersect1d(tidx, tidx2) if not tidx is None and not tidx2 is None else tidx if not tidx is None else tidx2
            # 三角比を取得
            assert not tidx is None
            keyA = self._ratioTree.data[tidx]
            tidx = tidx[np.linalg.norm(key - keyA, axis=1) <= r] # 検索
        else:
            # 頂点を固定しない
            tidx = self._ratioTree.query_ball_point(key, r=r)  # 検索
        
        cidx = self._values[tidx] # カタログを取得
        cidx0 = cidx[:,invOrder[0]]   # 順序を戻す
        cidx1 = cidx[:,invOrder[1]]   # 順序を戻す
        cidx2 = cidx[:,invOrder[2]]   # 順序を戻す
        cidx = np.stack([cidx0, cidx1, cidx2], axis=1)
        
        if not magLimit is None:
            # 等級フィルタ
            mask = self._catalog[cidx, MAG-1] <= magLimit
            mask = np.all(mask, axis=1)
            cidx = cidx[mask]
        if outputLimit and outputLimit < len(cidx):
            # 出力行数制限
            cidx = np.random.choice(cidx, size=outputLimit, replace=False)
        
        if 0 == len(cidx):
            return nh.zeros((0, 3, 4), dtype=nh.BDTYPE)
        
        # idx からカタログへ変換
        return np.concatenate([[[[c0idx],[c1idx],[c2idx]] for c0idx,c1idx,c2idx in cidx], self._catalog[cidx]], axis=2)
    
    def _makeKey(self, side:np.ndarray|list, idx:np.ndarray|list) -> tuple[np.ndarray, np.ndarray]:
        """
        辺長の入力を受けて kd-treee 用の key を返す。
        Args:
            side: 辺長のリスト [side01, side12, side20,...]
            idx: 頂点の ID のリスト [idx0, idx1, idx2,...]
        Returns:
            key: kd-tree 用の key
            index: 対応頂点の位置
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        side = np.asanyarray(side, dtype=nh.BDTYPE)
        idx   = np.asanyarray(idx)
        n    = len(side)
        
        roll = n - 1 - np.argmax(side) # 最大長の辺を配列の末尾に移動
        side = np.roll(side, roll)
        idx   = np.roll(idx  , roll)
        
        base = side[-1]
        key = side[:-1] / base
        
        return key, idx
    
    def queryStars(self, centerRaDeg: float, centerDecDeg: float, radiusDeg: float, magLimit: float = 99.0) -> np.ndarray:
        """
        指定された中心座標と半径の範囲内にある星を抽出する
        
        Args:
            centerRaDeg: 中心赤経 ( deg )
            centerDecDeg: 中心赤緯 ( deg )
            radiusDeg: 検索半径 ( deg )
            magLimit: 等級上限 ( mag )
            
        Returns:
            np.ndarray: 抽出された星の配列 shape=(N, 4) [[idx, raDeg, decDeg, mag],...]
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        assert not self._catalog is None, "Catalog is not loaded."
        
        if 0 == len(self._catalog):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        
        # 等級フィルタ
        indices = np.where(self._catalog[:, MAG-1] <= magLimit)[0]
        if 0 == len(indices):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        catalog = self._catalog[indices]
        
        # 赤緯の粗い矩形フィルタ
        decMin = max(-90.0, centerDecDeg - radiusDeg)
        decMax = min( 90.0, centerDecDeg + radiusDeg)
        decMask = (decMin <= catalog[:, DEC-1]) & (catalog[:, DEC-1] <= decMax)
        if not np.any(decMask):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        indices = indices[decMask]
        catalog = self._catalog[indices]
        
        # 赤経の粗い矩形フィルタ
        cosDec = max(0.01, np.cos(np.radians(centerDecDeg)))
        raDelta = radiusDeg / cosDec
        if raDelta < 180.0:
            raMin = (centerRaDeg - raDelta) % 360.0
            raMax = (centerRaDeg + raDelta) % 360.0
            if raMin <= raMax:
                raMask = (raMin <= catalog[:, RA-1]) & (catalog[:, RA-1] <= raMax)
            else:
                raMask = (catalog[:, RA-1] >= raMin) | (catalog[:, RA-1] <= raMax)
            if not np.any(raMask):
                return nh.zeros((0, 4), dtype=nh.BDTYPE)
            indices = indices[raMask]
            catalog = self._catalog[indices]
        
        # 正確な角距離を計算
        dists = self.angularDistance(catalog[:, RA-1:DEC], [centerRaDeg, centerDecDeg])
        distMask = dists <= radiusDeg
        if not np.any(distMask):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        indices = indices[distMask]
        catalog = self._catalog[indices]
        
        # idx からカタログへ変換
        return np.concatenate([[[idx] for idx in indices], catalog], axis=1)
    
    @staticmethod
    def angularDistance(p0:np.ndarray|list, p1:np.ndarray|list) -> np.ndarray|float:
        """
        天球上の2点間の角距離 ( deg ) を計算する
        ハヴァースィン公式
        
        Args:
            p0: 点0 の緯度経度 [[raDeg,decDeg],...]
            p1: 点1 の緯度経度 [[raDeg,decDeg],...]
        Returns:
            角距離 ( deg )
        """
        import numpy as np
        
        p0 = np.radians(np.asanyarray(p0))
        p1 = np.radians(np.asanyarray(p1))
        
        p0r = p0[..., 0]
        p0d = p0[..., 1]
        p1r = p1[..., 0]
        p1d = p1[..., 1]
        
        deltaR = p1r - p0r
        deltaD = p1d - p0d
        
        # haversine formula: 
        # a = sin^2(Δdec/2) + cos(dec1) * cos(dec2) * sin^2(Δra/2)
        a = np.sin(deltaD / 2)**2 + np.cos(p0d) * np.cos(p1d) * np.sin(deltaR / 2)**2
        
        # 数値誤差により a が 1.0 を超えないようクリップ
        a = np.clip(a, 0.0, 1.0)
        
        # d = 2 * arcsin(sqrt(a))
        distRad = 2 * np.arcsin(np.sqrt(a))
        distDeg = np.degrees(distRad)

        if distDeg.ndim == 0:
            return distDeg.item()
        else:
            return distDeg
    
    @staticmethod
    def gnomonicProjection(raDeg, decDeg, crval1Deg, crval2Deg):
        """
        天球接平面投影 ( グノモン投影 / TAN 投影 )
        天球座標 ( ra, dec ) を基準点 ( crval1, crval2 ) の接平面直交座標 ( xi, eta ) [rad] に変換
        
        Args:
            raDeg: 対象の赤経 ( deg )
            decDeg: 対象の赤緯 ( deg )
            crval1Deg: 接点の赤経 ( deg )
            crval2Deg: 接点の赤緯 ( deg )
            
        Returns:
            tuple[np.ndarray, np.ndarray]: 接平面座標 ( xi, eta ) [rad]
        """
        import numpy as np
        
        alpha  = np.radians(raDeg)
        delta  = np.radians(decDeg)
        alpha0 = np.radians(crval1Deg)
        delta0 = np.radians(crval2Deg)

        deltaAlpha = alpha - alpha0
        cosC = np.sin(delta0) * np.sin(delta) + np.cos(delta0) * np.cos(delta) * np.cos(deltaAlpha)
        cosC = np.where(np.abs(cosC) < 1e-10, 1e-10, cosC) # 0 除算防止

        xi  = (np.cos(delta) * np.sin(deltaAlpha)) / cosC
        eta = (np.cos(delta0) * np.sin(delta) - np.sin(delta0) * np.cos(delta) * np.cos(deltaAlpha)) / cosC

        return xi, eta

    @staticmethod
    def gnomonicDeprojection(xiRad, etaRad, crval1Deg, crval2Deg):
        """
        天球接平面逆投影 ( グノモン逆投影 )
        接平面直交座標 ( xi, eta ) [rad] から天球座標 ( ra, dec ) [deg] に変換
        
        Args:
            xiRad: 接平面 X 座標 ( rad )
            etaRad: 接平面 Y 座標 ( rad )
            crval1Deg: 接点の赤経 ( deg )
            crval2Deg: 接点の赤緯 ( deg )
            
        Returns:
            tuple[np.ndarray, np.ndarray]: 天球座標 ( ra, dec ) [deg]
        """
        import numpy as np
        
        alpha0 = np.radians(crval1Deg)
        delta0 = np.radians(crval2Deg)

        rho   = np.sqrt(xiRad**2 + etaRad**2)
        c     = np.arctan(rho)
        sinC  = np.sin(c)
        cosC  = np.cos(c)

        # rho が 0 の特異点処理
        rhoSafe = np.where(rho < 1e-12, 1.0, rho)

        sinDelta = cosC * np.sin(delta0) + (etaRad * sinC * np.cos(delta0)) / rhoSafe
        sinDelta = np.clip(sinDelta, -1.0, 1.0)
        delta    = np.arcsin(sinDelta)

        yTerm = xiRad * sinC
        xTerm = rhoSafe * np.cos(delta0) * cosC - etaRad * np.sin(delta0) * sinC
        alpha = alpha0 + np.arctan2(yTerm, xTerm)

        raDeg  = np.degrees(alpha) % 360.0
        decDeg = np.degrees(delta)

        return raDeg, decDeg
