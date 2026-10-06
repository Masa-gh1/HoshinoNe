'''
catalog_helper - 星カタログ読み込みおよび天球幾何計算ユーティリティ

Copyright (c) 2026 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

import os

if TYPE_CHECKING:
    import numpy as np

class Catalog:
    """星カタログのパース、キャッシュ管理、および幾何計算を行うユーティリティ"""
    _cachedSymbol    = None
    _cachedPath      = None
    _cachedCatalog   = None
    _cachedRatioTree = None
    _cachedIdMap     = None
    _cachedValues    = None

    def __init__(self, catalog:np.ndarray=None):
        self._symbol    = None
        self._path      = None
        self._catalog   = None
        self._ratioTree = None
        self._idMap     = None
        self._values    = None

        if not catalog is None:
            self._symbol  = ""
            self._catalog = catalog
        else:
            from config import CATALOG_PATH
            symbol, filePath = CATALOG_PATH
            self.loadCatalog(symbol, filePath)
            self._symbol    = self._cachedSymbol
            self._path      = self._cachedPath
            self._catalog   = self._cachedCatalog
            self.generateTriangleDatabase()
            self._ratioTree = self._cachedRatioTree
            self._idMap     = self._cachedIdMap
            self._values    = self._cachedValues
        
        # セルフテスト
        for _ in range(100):
            import numpy as np
            roll = np.random.randint(3)        # 順序違い
            r  = np.random.rand() * 10 + 0.001 # 相似比
            n0 = np.random.rand()*0.001 + 1.0  # ノイズ
            n1 = np.random.rand()*0.001 + 1.0  # ノイズ
            n2 = np.random.rand()*0.001 + 1.0  # ノイズ
            e = 0.002                          # 許容ズレ
            
            # ケース
            prm = np.random.randint(3)
            cid = self._values[np.random.randint(len(self._values))]
            cid = np.roll(cid, roll)
            re = np.random.rand() * 0.01 + e
            
            c0idx = np.searchsorted(self._catalog[:, 0], cid[0])
            c1idx = np.searchsorted(self._catalog[:, 0], cid[1])
            c2idx = np.searchsorted(self._catalog[:, 0], cid[2])
            c0 = self._catalog[c0idx]
            c1 = self._catalog[c1idx]
            c2 = self._catalog[c2idx]
            c01d = self.angularDistance(c0[1], c0[2], c1[1], c1[2])
            c12d = self.angularDistance(c1[1], c1[2], c2[1], c2[2])
            c20d = self.angularDistance(c2[1], c2[2], c0[1], c0[2])
            
            # 実行
            if   0==prm: c = self.searchTriangle(c01d*r*n0, c12d*r*n1, c20d*r*n2, re)
            elif 1==prm: c = self.searchTriangle(c01d*r*n0, c12d*r*n1, c20d*r*n2, re, fixVertexId=(None,cid[1],None  ))
            else       : c = self.searchTriangle(c01d*r*n0, c12d*r*n1, c20d*r*n2, re, fixVertexId=(None,cid[1],cid[2]))
            
            # チェック
            chk0 = (c[:, 0, 0] == cid[0])
            chk1 = (c[:, 1, 0] == cid[1])
            chk2 = (c[:, 2, 0] == cid[2])
            chk = chk0 & chk1 & chk2
            assert np.any(chk), f"Self test: Triangle search error: {str(cid)} {re:0.3f} r:{r} noise:{n0} {n1} {n2}"
    
    def loadCatalog(self, symbol, filePath):
        """
        カタログファイルを読み込み、numpy 配列を返す
        
        Returns:
            np.ndarray: [N, 4] の配列 [[id, raDeg, decDeg, mag],...]
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from config import CATALOG_HEADERS
        
        if self._cachedCatalog is not None and filePath == self._cachedPath: # キャッシュが有効な場合
            return self._cachedCatalog
        
        if not os.path.exists(filePath):
            return None
        
        # キャッシュパス
        cachePath = os.path.splitext(filePath)[0] + ".npy"
        
        if(   self._cachedSymbol == symbol
          and self._cachedPath == cachePath
          and self._cachedCatalog is not None
          and os.path.exists(cachePath)
          and os.path.getmtime(filePath) < os.path.getmtime(cachePath)
          ):
            pass
        elif(   os.path.exists(cachePath)
            and os.path.getmtime(filePath) <= os.path.getmtime(cachePath)
            ):
            # キャッシュが存在し元ファイルより新しいので、キャッシュからロード
            catalog = np.load(cachePath)
            self._cachedSymbol  = symbol
            self._cachedPath    = filePath
            self._cachedCatalog = catalog
        else:
            # 元ファイル(TSV)からパース
            rows = []
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
                    
                for line in f:
                    if not line or not line.strip() or line.startswith("#"): # コメント行なので、スキップ
                        continue
                    
                    items = line.strip().split("\t")
                    
                    names = ("ID", "RA", "Dec", "Mag") # 読み込むデータ名(CATALOG_HEADERS)
                    data = []
                    for name in names:
                        p = pos[name]
                        if len(items) <= p:
                            # 項目が足りないの中止
                            break
                        data.append(items[p].strip())
                    
                    if len(names) == len(data):
                        try:
                            for i in range(len(data)):
                                data[i] = float(data[i])
                            rows.append(data)
                        except ValueError:
                            continue
            
            catalog = nh.array(rows)
            
            # id 順にソート
            catalog = catalog[np.argsort(catalog[:, 0])]
            
            # 次回高速化のためにキャッシュ保存
            try:
                np.save(cachePath, catalog)
            except Exception:
                from utils.Debug import Debug
                Debug.log(self.__class__.__name__, "Warning: Save catalog cache failed.")
            
            self._cachedSymbol  = symbol
            self._cachedPath    = filePath
            self._cachedCatalog = catalog
    
    def generateTriangleDatabase(self):
        """三角形データベースの生成"""
        from config import CATALOG_DB_MAG, CATALOG_DB_NUM
        
        if self._catalog is None or 0 == len(self._catalog):
            self._ratioTree = None
            self._idMap     = None
            self._values    = None
            return

        # キャッシュパス
        ratioCachePath = os.path.splitext(self._path)[0] + "_ratioIndex.pkl"
        idCachePath    = os.path.splitext(self._path)[0] + "_idIndex.pkl"
        valueCachePath = os.path.splitext(self._path)[0] + "_triangleVal.npy"
        if(     not self._cachedRatioTree is None
            and not self._cachedIdMap     is None
            and not self._cachedValues    is None
            and os.path.exists(ratioCachePath)
            and os.path.exists(idCachePath   )
            and os.path.exists(valueCachePath)
            and os.path.getmtime(self._path) <= os.path.getmtime(ratioCachePath)
            and os.path.getmtime(self._path) <= os.path.getmtime(idCachePath   )
            and os.path.getmtime(self._path) <= os.path.getmtime(valueCachePath)
          ):
            pass
        elif(   os.path.exists(ratioCachePath)
            and os.path.exists(idCachePath   )
            and os.path.exists(valueCachePath)
            and os.path.getmtime(self._path) <= os.path.getmtime(ratioCachePath)
            and os.path.getmtime(self._path) <= os.path.getmtime(idCachePath   )
            and os.path.getmtime(self._path) <= os.path.getmtime(valueCachePath)
            ):
            # キャッシュが存在し元ファイルより新しいので、キャッシュからロード
            import numpy as np
            import pickle
            with open(ratioCachePath, "rb") as f: self._cachedRatioTree = pickle.load(f)
            with open(idCachePath   , "rb") as f: self._cachedIdMap = pickle.load(f)
            self._cachedValues = np.load(valueCachePath)
        else:
            # 統計情報の生成
            import numpy as np
            from scipy.spatial import KDTree
            from utils import numpy_helpers as nh
            from utils.Debug import Debug
            Debug.log(self.__class__.__name__, f" {self._symbol} [{len(self._catalog)} stars]")
            
            # 等級の10%毎のパーセンタイル
            p  = list(range(0, 101, 10))
            pS = " ".join(["%4d" % x for x in p])
            mag  = np.percentile(self._catalog[:, 3], p)
            magS = " ".join(["%4.1f" % x for x in mag])
            Debug.log(self.__class__.__name__, f"         {pS}%")
            Debug.log(self.__class__.__name__, f"Mag: 0%: {magS} :100%")
            
            # 等級,画角毎に見える星の数の平均
            magRad = []
            radius  = [1,2,4,8,16,32,64,128,180]
            radiusS = " ".join(["%5d"%(x) for x in radius])
            Debug.log(self.__class__.__name__, f"                    {radiusS}deg")
            for mag in range(9):
                count  = []
                for r in radius:
                    s = []
                    np.random.seed(0) # 固定シードで再現性確保
                    for i in range(100):
                        ra     = np.random.uniform(0, 360)     # RA は均等
                        sinDec = np.random.uniform(-1.0, 1.0)  # sin(-90°)=-1, sin(90°)=1
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
            # データサイズは nC2 で増える。
            # 8等星までの星が 38,000 位あり、
            # CATALOG_DB_NUM = 5 だと三角形の数は 5C2 * 38,000 = 380,000 ですが、「CATALOG_DB_NUM 以上」なので 970,000 程度(num=7～8)になる。
            # メモリ量は
            # kd-tree が 970,000 * (4 + 4 + 4) = 11,640,000 これにオーバーヘッドが加わり 47,000,000 程度になる。
            # values  が 970,000 * (4 + 4 + 4) = 11,640,000 でこれはほぼこのまま。
            #
            # 同様に、8等星まで CATALOG_DB_NUM = 10 だと、10C2 * 38,000 = 1,710,000
            # 三角形の数   4,000,000 (num=14～15)
            # kd-tree   193,000,000
            # values     45,000,000
            keys   = []
            values = []
            indices = np.where(self._catalog[:, 3] <= CATALOG_DB_MAG)[0]
            starCount = len(indices)
            progress = 0
            Debug.log(self.__class__.__name__, f"Generate triangle database from {starCount} stars")
            for idx in indices:
                progress += 1
                if progress % (starCount//10+1) == 0:
                    Debug.log(self.__class__.__name__, f"Progress: {progress}/{starCount} {progress*100//starCount}%  triangles: {len(keys)}")
                
                cid  = self._catalog[idx, 0]
                ra  = self._catalog[idx, 1]
                dec = self._catalog[idx, 2]
                mag = self._catalog[idx, 3]
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
                other = selected[selected[:, 0] != cid]
                x, y = self.gnomonicProjection(other[:, 1], other[:, 2], ra, dec)
                for j in range(len(other)):
                    for k in range(j+1, len(other)):
                        c0 = self._catalog[idx]
                        c1 = other[j]
                        c2 = other[k]
                        x1, y1 = x[j], y[j]
                        x2, y2 = x[k], y[k]
                        if 0 < ((x1 - 0) * (y2 - 0)) - ((y1 - 0) * (x2 - 0)):
                            c1,c2 = c2,c1 # 時計回りに修正
                        c01d = self.angularDistance(c0[1], c0[2], c1[1], c1[2])
                        c12d = self.angularDistance(c1[1], c1[2], c2[1], c2[2])
                        c20d = self.angularDistance(c2[1], c2[2], c0[1], c0[2])
                        key, cid = self.makeKey([c01d, c12d, c20d], [c0[0], c1[0], c2[0]])
                        keys.append(key)
                        values.append(cid)
            Debug.log(self.__class__.__name__, f"Total triangle count: {len(keys)}")
            ratioTree = KDTree(nh.array(keys))
            values    = np.array(values, dtype=np.int32)

            # id map 作成
            # id で values を引く
            idMap = {}
            for idx, (cid0, cid1, cid2) in enumerate(values):
                idMap.setdefault(cid0, [[], [], []])[0].append(idx)
                idMap.setdefault(cid1, [[], [], []])[1].append(idx)
                idMap.setdefault(cid2, [[], [], []])[2].append(idx)
            for cid in idMap: 
                idMap[cid][0] = np.array(idMap[cid][0], dtype=np.int32)
                idMap[cid][1] = np.array(idMap[cid][1], dtype=np.int32)
                idMap[cid][2] = np.array(idMap[cid][2], dtype=np.int32)
            
            # 次回高速化のためにキャッシュ保存
            try:
                import pickle
                with open(ratioCachePath, "wb") as f: pickle.dump(ratioTree, f, protocol=pickle.HIGHEST_PROTOCOL)
                Debug.log(self.__class__.__name__, f"Key   file size {os.path.getsize(ratioCachePath)//1024//1024} MiB")
                
                with open(idCachePath   , "wb") as f: pickle.dump(idMap    , f, protocol=pickle.HIGHEST_PROTOCOL)
                Debug.log(self.__class__.__name__, f"Value file size {os.path.getsize(idCachePath   )//1024//1024} MiB")
                
                np.save(valueCachePath, values)
                Debug.log(self.__class__.__name__, f"Value file size {os.path.getsize(valueCachePath)//1024//1024} MiB")
            except Exception:
                Debug.log(self.__class__.__name__, "Warning: Save triangle database cache failed.")
            
            self._cachedRatioTree = ratioTree
            self._cachedIdMap     = idMap
            self._cachedValues    = values
    
    def count(self) -> int:
        return len(self._catalog)
    
    def searchTriangle(self, side01:float, side12:float, side20:float, relativeError:float,
                             magLimit:float|None=None, fixVertexId:tuple|list|None=None,
                             outputLimit:int|None=None) -> np.ndarray:
        """
        三角比データベースを検索し、指定された三角形に相似な星の組み合わせを返す

        Args:
            side01: 辺01の長さ
            side12: 辺12の長さ
            side20: 辺20の長さ
            relativeError: 相似比の相対誤差
            magLimit: 等級制限 ( mag )
            fixVertexId: 頂点の ID を固定 (id0,id1,id2) or (None,id1,id2) or ...
            outputLimit: 出力制限数

        Returns:
            np.ndarray: 星の組み合わせ [N, 3, 4] の配列 [[star0, star1, star2], ...]
                        star0 = [id, ra, dec, mag]
        """
        import numpy as np
        key, orderder = self.makeKey([side01, side12, side20], [0, 1, 2])
        invOrder = np.argsort(orderder) # 逆引き用
        r = np.linalg.norm(key)*relativeError
        
        if not fixVertexId is None:
            # 頂点を固定する
            cid0, cid1, cid2 = fixVertexId
            assert not cid0 is None or not cid1 is None or not cid2 is None
            cidx0 = self._idMap[cid0][invOrder[0]] if not cid0 is None else None # key の順序に入れ替え
            cidx1 = self._idMap[cid1][invOrder[1]] if not cid1 is None else None # key の順序に入れ替え
            cidx2 = self._idMap[cid2][invOrder[2]] if not cid2 is None else None # key の順序に入れ替え
            # 共通する idx を抽出
            cidx = cidx0
            cidx = np.intersect1d(cidx, cidx1) if not cidx is None and not cidx1 is None else cidx if not cidx is None else cidx1
            cidx = np.intersect1d(cidx, cidx2) if not cidx is None and not cidx2 is None else cidx if not cidx is None else cidx2
            # 三角比を取得
            keyA = self._ratioTree.data[cidx]
            cidx = cidx[np.linalg.norm(key - keyA, axis=1) <= r] # 検索
        else:
            # 頂点を固定しない
            cidx = self._ratioTree.query_ball_point(key, r=r)  # 検索
        
        cid = self._values[cidx] # カタログIDを取得
        cid0 = cid[:,invOrder[0]]   # 順序を戻す
        cid1 = cid[:,invOrder[1]]   # 順序を戻す
        cid2 = cid[:,invOrder[2]]   # 順序を戻す
        cid = np.stack([cid0, cid1, cid2], axis=1)
        
        if not magLimit is None:
            # 等級フィルタ
            cidx = np.searchsorted(self._catalog[:,0], cid)
            mask = self._catalog[cidx, 3] <= magLimit
            mask = np.all(mask, axis=1)
            cid = cid[mask]
        if outputLimit and outputLimit < len(cid):
            # 出力行数制限
            cidx = np.random.choice(len(cid), size=outputLimit, replace=False)
            cid = cid[cidx]
        # id からカタログへ変換
        n = len(cid)
        #cid = np.concatenate([cid[:,0], cid[:,1], cid[:,2]], axis=0)
        cidx = np.searchsorted(self._catalog[:,0], cid)
        #c0 = self._catalog[cidx[   :n  ]]
        #c1 = self._catalog[cidx[n  :n+n]]
        #c2 = self._catalog[cidx[n+n:   ]]
        #c = np.stack([c0, c1, c2], axis=1)
        c = self._catalog[cidx]
        return c
    
    def makeKey(self, side:np.ndarray|list, id:np.ndarray|list) -> tuple[np.ndarray, np.ndarray]:
        """
        辺長の入力を受けて kd-treee 用の key を返す。
        Args:
            side: 辺長のリスト [side01, side12, side20, ...]
            id: 頂点の ID のリスト [id0, id1, id2, ...]
        Returns:
            key: kd-tree 用の key
            index: 対応頂点の位置
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        side = np.asanyarray(side, dtype=nh.BDTYPE)
        id   = np.asanyarray(id)
        n    = len(side)
        
        roll = n - 1 - np.argmax(side) # 最大長の辺を配列の末尾に移動
        side = np.roll(side, roll)
        id   = np.roll(id  , roll)
        
        base = side[-1]
        key = side[:-1] / base
        
        return key, id
    
    def queryStars(self,
                   centerRaDeg: float,
                   centerDecDeg: float,
                   radiusDeg: float,
                   magLimit: float = 99.0) -> np.ndarray:
        """
        指定された中心座標と半径の範囲内にある星を抽出する
        
        Args:
            centerRaDeg: 中心赤経 ( deg )
            centerDecDeg: 中心赤緯 ( deg )
            radiusDeg: 検索半径 ( deg )
            magLimit: 等級上限 ( mag )
            
        Returns:
            np.ndarray: 抽出された星の配列
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        if 0 == len(self._catalog):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        
        # 等級フィルタ
        magMask = self._catalog[:, 3] <= magLimit
        filtered = self._catalog[magMask]
        if 0 == len(filtered):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        
        # 赤緯の粗い矩形フィルタ
        decMin = max(-90.0, centerDecDeg - radiusDeg)
        decMax = min( 90.0, centerDecDeg + radiusDeg)
        decMask = (decMin <= filtered[:, 2]) & (filtered[:, 2] <= decMax)
        filtered = filtered[decMask]
        if 0 == len(filtered):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        
        # 赤経の粗い矩形フィルタ
        cosDec = max(0.01, np.cos(np.radians(centerDecDeg)))
        raDelta = radiusDeg / cosDec
        if raDelta < 180.0:
            raMin = (centerRaDeg - raDelta) % 360.0
            raMax = (centerRaDeg + raDelta) % 360.0
            if raMin <= raMax:
                raMask = (raMin <= filtered[:, 1]) & (filtered[:, 1] <= raMax)
            else:
                raMask = (filtered[:, 1] >= raMin) | (filtered[:, 1] <= raMax)
            filtered = filtered[raMask]
        
        if 0 == len(filtered):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)
        else:
            # 正確な角距離を計算
            dists = self.angularDistance(filtered[:, 1], filtered[:, 2], centerRaDeg, centerDecDeg)
            distMask = dists <= radiusDeg
            return filtered[distMask]
    
    @staticmethod
    def angularDistance(ra1Deg, dec1Deg, ra2Deg, dec2Deg):
        """
        天球上の2点間の角距離 ( deg ) を計算する
        ハヴァースィン公式
        
        Args:
            ra1Deg: 点1の赤経 ( deg )
            dec1Deg: 点1の赤緯 ( deg )
            ra2Deg: 点2の赤経 ( deg )
            dec2Deg: 点2の赤緯 ( deg )
            
        Returns:
            角距離 ( deg )
        """
        import numpy as np
        
        r1 = np.asanyarray(np.radians(ra1Deg))
        d1 = np.asanyarray(np.radians(dec1Deg))
        r2 = np.asanyarray(np.radians(ra2Deg))
        d2 = np.asanyarray(np.radians(dec2Deg))

        deltaR = r2 - r1
        deltaD = d2 - d1

        # haversine formula: 
        # a = sin^2(Δdec/2) + cos(dec1) * cos(dec2) * sin^2(Δra/2)
        a = np.sin(deltaD / 2)**2 + np.cos(d1) * np.cos(d2) * np.sin(deltaR / 2)**2
        
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
