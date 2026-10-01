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

class CatalogHelper:
    """星カタログのパース、キャッシュ管理、および幾何計算を行うユーティリティ"""
    
    _cachedSymbol  = None
    _cachedPath    = None
    _cachedCatalog = None

    @classmethod
    def loadCatalog(cls) -> np.ndarray:
        """
        カタログファイルを読み込み、numpy 配列を返す
        
        Returns:
            np.ndarray: [N, 4] の配列 [[id, raDeg, decDeg, mag],...]
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from config import CATALOG_PATH, CATALOG_HEADERS

        symbol, filePath = CATALOG_PATH
        if cls._cachedCatalog is not None and filePath == cls._cachedPath: # キャッシュが有効な場合
            return cls._cachedCatalog

        if not os.path.exists(filePath):
            return None
        
        # バイナリキャッシュパス
        cachePath = os.path.splitext(filePath)[0] + ".npy"

        if os.path.exists(cachePath) and os.path.getmtime(filePath) <= os.path.getmtime(cachePath):
            # キャッシュが存在し元ファイルより新しいので、キャッシュからロード
            catalogData        = np.load(cachePath)
            cls._cachedSymbol  = symbol
            cls._cachedPath    = filePath
            cls._cachedCatalog = catalogData
            return catalogData
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
            
            catalogData = nh.array(rows)
            
            # 次回高速化のためにキャッシュ保存
            try:
                np.save(cachePath, catalogData)
            except Exception:
                from utils.Debug import Debug
                Debug.log(cls.__name__, "Warning: Save catalog cache failed.")

            cls._cachedCatalog = catalogData
            cls._cachedPath    = filePath
            return catalogData

    @classmethod
    def queryStars(cls,
                   catalogData: np.ndarray,
                   centerRaDeg: float,
                   centerDecDeg: float,
                   radiusDeg: float,
                   magLimit: float = 99.0) -> np.ndarray:
        """
        指定された中心座標と半径の範囲内にある星を抽出する
        
        Args:
            catalogData: 全カタログ配列
            centerRaDeg: 中心赤経 ( deg )
            centerDecDeg: 中心赤緯 ( deg )
            radiusDeg: 検索半径 ( deg )
            magLimit: 等級上限 ( mag )
            
        Returns:
            np.ndarray: 抽出された星の配列
        """
        import numpy as np
        from utils import numpy_helpers as nh

        if 0 == len(catalogData):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)

        # 等級フィルタ
        magMask = catalogData[:, 3] <= magLimit
        filtered = catalogData[magMask]
        if 0 == len(filtered):
            return nh.zeros((0, 4), dtype=nh.BDTYPE)

        # 赤緯の粗い矩形フィルタ
        decMin = max(-90.0, centerDecDeg - radiusDeg)
        decMax = min(90.0, centerDecDeg + radiusDeg)
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

        # 正確な角距離を計算
        dists = cls.angularDistance(filtered[:, 1], filtered[:, 2], centerRaDeg, centerDecDeg)
        distMask = dists <= radiusDeg
        return filtered[distMask]

    @staticmethod
    def angularDistance(ra1Deg, dec1Deg, ra2Deg, dec2Deg):
        """
        天球上の2点間の角距離 ( deg ) を計算する
        ハヴァースィン公式を用いて、小距離における数値的安定性を確保
        
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
