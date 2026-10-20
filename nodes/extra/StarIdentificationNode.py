'''
StarIdentificationNode - 星同定ノード

画像から天体（星点）を検出し、星カタログ（HIP2等）と照合して確定した星のリストを生成するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from types import SimpleNamespace

import hashlib

import tkinter as tk
from tkinter import messagebox

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

if TYPE_CHECKING:
    import numpy as np
    from utils.catalog_helper import Catalog
    from base.FlowData import FlowData

# 結果配列 index 定義
ID, RA, DEC, MAG, X, Y, BRI, AR, U, V, W = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

class StarIdentificationNode(FlowNode, ConfigurableNode):
    """画像から星を抽出し、カタログデータと照合して星リストを出力するノード"""
    
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'star_identification'
    # ノード名
    name      = '星同定'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_AUX
    
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # 設定パラメーター
        # 画像パラメーター
        self.fovDeg                 = 2.0                   # 画角 [deg]
        self.useHeaderFovDeg        = True                  # 画像ヘッダから推定する
        
        # カタログ照合パラメーター
        self.catalog                = SimpleNamespace()
        self.catalog.matchLimit     = 1.0                   # カタログ照合許容比 [%]
        self.catalog.magLimit       = 8.0                   # カタログ等級上限 [mag]
        
        # 星像選択パラメーター
        self.star                   = SimpleNamespace()
        self.star.grid              = SimpleNamespace()
        self.star.grid.rows         = 1                     # グリッド行数
        self.star.grid.cols         = 1                     # グリッド列数
        self.star.grid.starsPerGrid = 8                     # グリッド当たりの選択星数
        self.star.minMatchedStars   = 5                     # 少なくとも同定したい星の数
        self.star.ransac            = SimpleNamespace()
        self.star.ransac.iterations = 100                   # RANSAC試行回数
        self.star.ransac.seed       = 2725                  # RANSAC乱数シード
    
    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nMatch:{self.catalog.matchLimit}% Mag:{self.catalog.magLimit}"
        return displayText

    def store(self, nodeData):
        """ノード設定を辞書に保存"""
        nodeData["fovDeg"]              = self.fovDeg
        nodeData["useHeaderFovDeg"]     = self.useHeaderFovDeg
        nodeData["catalog.matchLimit"]  = self.catalog.matchLimit
        nodeData["catalog.magLimit"]    = self.catalog.magLimit
        nodeData["gridRows"]            = self.star.grid.rows
        nodeData["gridCols"]            = self.star.grid.cols
        nodeData["starsPerGrid"]        = self.star.grid.starsPerGrid
        nodeData["minMatchedStars"]     = self.star.minMatchedStars
        nodeData["ransacIterations"]    = self.star.ransac.iterations
        nodeData["ransacSeed"]          = self.star.ransac.seed

    def restore(self, nodeData):
        """辞書からノード設定を復元"""
        if "fovDeg" in nodeData:
            self.fovDeg = nodeData["fovDeg"]
        if "useHeaderFovDeg" in nodeData:
            self.useHeaderFovDeg = nodeData["useHeaderFovDeg"]
        if "catalog.matchLimit" in nodeData:
            self.catalog.matchLimit = nodeData["catalog.matchLimit"]
        if "catalog.magLimit" in nodeData:
            self.catalog.magLimit = nodeData["catalog.magLimit"]
        if "gridRows" in nodeData:
            self.star.grid.rows = nodeData["gridRows"]
        if "gridCols" in nodeData:
            self.star.grid.cols = nodeData["gridCols"]
        if "starsPerGrid" in nodeData:
            self.star.grid.starsPerGrid = nodeData["starsPerGrid"]
        if "minMatchedStars" in nodeData:
            self.star.minMatchedStars = nodeData["minMatchedStars"]
        if "ransacIterations" in nodeData:
            self.star.ransac.iterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.star.ransac.seed = nodeData["ransacSeed"]
    
    def process(self, context=None):
        """星抽出処理のメイン実行"""
        self.reportProgress(context, "開始")

        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)

        # primary/auxiliaryで分類
        primaryStreams = self.preprocessStreams(inputStreams)
        if 0 == len(primaryStreams) or not primaryStreams[0]:
            self.flowDatas = []
            return

        inputStream = primaryStreams[0]

        # カタログの準備
        catalog = self._getCatalog()

        # 各画像から星を抽出し、カタログ照合
        outputFlowDatas = []
        totalImages     = len(inputStream)
        
        for i, flowData in enumerate(inputStream):
            self.reportProgress(context, f"画像 {i + 1}/{totalImages} 処理中", i, totalImages)
            
            # カタログ照合
            matchedStars = self.matchCatalog(flowData, catalog)

            # 出力 Table FlowData を作成
            flowData = self.createFlowData(flowData, catalog, matchedStars)
            outputFlowDatas.append(flowData)

        self.flowDatas = outputFlowDatas
        self.reportProgress(context, "完了")

    def preprocessStreams(self, inputStreams:list[list[FlowData]]) -> list[list[FlowData]]:
        """入力データの前処理：primary/auxiliaryで分類"""
        primaryStreams = []
        auxiliaryStreams = []
        
        for stream in inputStreams:
            category = stream[0].headers.get('category', _OUT_CAT_PRI)
            if _OUT_CAT_AUX == category:
                auxiliaryStreams.append(stream)
            else:
                primaryStreams.append(stream)

        self._catalogStream = auxiliaryStreams[0] if 0 < len(auxiliaryStreams) else None
        return primaryStreams
    
    def _getCatalog(self) -> Catalog:
        """カタログデータを取得（入力ストリームまたはファイルから）"""
        from utils import numpy_helpers as nh
        from utils.catalog_helper import Catalog
        if self._catalogStream and self._catalogStream[0]:
            flowData = self._catalogStream[0]
            width, height = flowData.getDimensions()
            
            planes  = flowData.headers["planes"]
            columns = flowData.headers["columns"]
            lines   = flowData.headers["lines"]
            raIdx   = columns.index("ra")
            decIdx  = columns.index("dec")
            magIdx  = columns.index("mag")
            
            # Table FlowData から配列化
            table = nh.nans((len(planes), height, width))
            for block in flowData.iterateBlocks():
                if block:
                    planeIndex = block.planeIndex
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    table[planeIndex, y:y+h, x:x+w] = block.data
            
            symbol = planes[0]
            table = table.reshape((planes * height, width)) # plaen を縦に並べ替え
            table = table[:, [raIdx, decIdx, magIdx]] # RA, DEC, MAG の順に並べ替え
            
            return Catalog( symbol, table)
            
        # ファイルから読み込み
        return Catalog()

    def _selectDistributedStars(self, stars:np.ndarray, width:int, height:int) -> tuple[np.ndarray, list[int]]:
        """
        画像全体に分散した星を選択
        
        Args:
            stars: 星の座標と明度の配列 (x, y, brightness, area)
            width: 画像の幅
            height: 画像の高さ
        
        Returns:
            distributedStars: 分散した星の配列 (x, y, brightness, area)
            gridSelectedCounts: 各グリッドから選択された星の数のリスト
        """
        import numpy as np
        
        if 0 == len(stars):
            return stars, []

        gridRows, gridCols = self.star.grid.rows, self.star.grid.cols
        
        # 各グリッド領域のサイズ
        cellH = height // gridRows
        cellW = width  // gridCols
        
        distributedStars   = []
        gridSelectedCounts = []

        # 各グリッドから最大 n 個の明るい星を選択
        for row in range(gridRows):
            for col in range(gridCols):
                yMin = row * cellH
                yEnd = (row + 1) * cellH if row < gridRows - 1 else height
                xMin = col * cellW
                xEnd = (col + 1) * cellW if col < gridCols - 1 else width
                
                # このグリッド内の星を抽出
                gridStars = [(x, y, br, ar) for x, y, br, ar in stars if xMin <= x < xEnd and yMin <= y < yEnd]
                
                # 明度順でソートして上位指定数を選択
                gridStars.sort(key=lambda x: x[2], reverse=True)
                selected = gridStars[:self.star.grid.starsPerGrid]
                distributedStars.extend(selected)
                gridSelectedCounts.append(len(selected))
        
        distributedStars = np.array(distributedStars)
        
        return distributedStars, gridSelectedCounts
    
    def matchCatalog(self, flowData:FlowData, catalog:Catalog):
        """
        画像座標と天球座標の間で投影（Mapping）を行わず、
        幾何学的な相似の比較のみで全星の同定（インライア判定）を行う。
        これにより、レンズ歪みの影響を最小化する。
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from utils.catalog_helper import Catalog

        columnCnt, rowCnt = flowData.getDimensions()
        
        if rowCnt < 4 or catalog.count() < 4:
            raise ValueError("少なくとも星数が 4 つ必要です。")
        
        # RANSAC用固定シードを設定
        random = np.random.default_rng(self.star.ransac.seed)

        # 画像側の点像を読み込み
        data = nh.nans((rowCnt, columnCnt))
        for block in flowData.iterateBlocks():
            if block:
                x, y = block.x, block.y
                h, w = block.data.shape
                data[y:y+h, x:x+w] = block.data
        
        stars = []
        columns = flowData.headers["columns"]
        for name in ["x", "y", "brightness", "aspect_ratio"]:
            idx = columns.index(name)
            stars.append(data[:,idx])
        stars = np.stack(stars, axis=1)
        
        # 元画像の大きさが分からないので大体のサイズを設定
        # 星均等に写っていると想定し、周囲の余白は同じであるとする。
        width, height = np.min(stars[:, 0:2], axis=0) + np.max(stars[:, 0:2], axis=0)
        
        # 画像側のサンプリング
        stars, _ = self._selectDistributedStars(stars, width, height)
        starCnt = len(stars)
        if starCnt < 4:
            return []
        
        # 星の座標をレンズ中心からの単位 vector に変換
        if self.useHeaderFovDeg:
            # 画像のヘッダからレンズ中心と焦点距離を得て計算
            from utils import exif_helper as eh
            
            focalCenter_px   = eh.getFocalCenter(flowData.headers) # [px]
            focalLength_mm   = eh.getFocalLength(flowData.headers) # [mm]
            resolution_pxpmm = eh.getResolution(flowData.headers)  # [px/mm]
            if focalLength_mm is None or resolution_pxpmm is None:
                raise ValueError("画像のヘッダに焦点情報が設定されていません。")
            
            starsX = (stars[:, 0] - focalCenter_px[0]) / resolution_pxpmm[0] # 中心を原点に [mm]
            starsY = (stars[:, 1] - focalCenter_px[1]) / resolution_pxpmm[1] # 中心を原点に [mm]
            f = float(focalLength_mm)                                        # 焦点距離 [mm]
            f = np.broadcast_to(f, starsX.shape)
        else:
            # 設定値の画角から計算
            starsX = stars[:, 0] - (width  / 2) # 中心を原点に [px]
            starsY = stars[:, 1] - (height / 2) # 中心を原点に [px]
            f = (width * width + height * height) ** 0.5 / (2.0 * np.tan(np.radians(self.fovDeg) / 2.0)) # 焦点距離を計算 [px]
            f = np.broadcast_to(f, starsX.shape)
        starsV = np.stack([starsX, starsY, f]).T
        starsV = starsV / np.linalg.norm(starsV, axis=1, keepdims=True) # 単位ベクトルに変換
        
        # 結果配列の構造に変換
        stars = np.concatenate([nh.nans((stars.shape[0],4)), stars, starsV], axis=1) # id, ra, dec, mag, x, y, brightness, aspectRatio, u, v, w
        
        # 探索結果
        bestMatchCount = 0
        bestMatchError = np.inf
        bestMatchStars = [] # [(id, ra, dec, mag, x, y, brightness, aspectRatio, u, v, w),...]
        catalogTotal = 0
        
        # 4 点による 2 つの三角形のパターン
        COMB_TRIANGLE_PAIRS = np.array([
            [[0, 1, 2], [0, 1, 3]],
            [[0, 1, 3], [0, 1, 2]],
            [[0, 2, 1], [0, 2, 3]],
            [[0, 2, 3], [0, 2, 1]],
            [[0, 3, 1], [0, 3, 2]],
            [[0, 3, 2], [0, 3, 1]],
            [[1, 2, 0], [1, 2, 3]],
            [[1, 2, 3], [1, 2, 0]],
            [[1, 3, 0], [1, 3, 2]],
            [[1, 3, 2], [1, 3, 0]],
            [[2, 3, 0], [2, 3, 1]],
            [[2, 3, 1], [2, 3, 0]],
        ], dtype=np.int8)

        i = 0
        for i in range(self.star.ransac.iterations): # RANSAC試行回数
            # 画像側で 4 点をランダムに選択し接する時計回りの三角形 2 つを作成する
            idx = random.choice(starCnt, 4, replace=False)
            idx = idx[COMB_TRIANGLE_PAIRS]
            star = stars[idx] # 3点2組の組み合わせ
            s0x = star[:, :, 0, X]
            s0y = star[:, :, 0, Y]
            s1x = star[:, :, 1, X]
            s1y = star[:, :, 1, Y]
            s2x = star[:, :, 2, X]
            s2y = star[:, :, 2, Y]
            valid = np.all(((s1x - s0x) * (s2y - s0y) - (s1y - s0y) * (s2x - s0x)) < 0, axis=1) # 時計回り判定
            sel = random.choice(np.where(valid)[0]) # valid==True の中から1つを選択
            pidx = idx[sel, 0]
            qidx = idx[sel, 1]
            
            # 三角形 P を作成
            p = stars[pidx]
            p0, p1, p2 = p
            dp01 = self.calcAngDistance(p0[U:W+1], p1[U:W+1])
            dp12 = self.calcAngDistance(p1[U:W+1], p2[U:W+1])
            dp20 = self.calcAngDistance(p2[U:W+1], p0[U:W+1])
            dp = np.stack([dp01, dp12, dp20])
            if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)
            
            # 三角形 Q を作成
            q = stars[qidx]
            q0, q1, q2 = q
            dq01 = self.calcAngDistance(q0[U:W+1], q1[U:W+1])
            dq12 = self.calcAngDistance(q1[U:W+1], q2[U:W+1])
            dq20 = self.calcAngDistance(q2[U:W+1], q0[U:W+1])
            dq = np.stack([dq01, dq12, dq20])
            if np.any(dq < 1e-7) or np.min(dq) / np.max(dq) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)

            dp2q2 = self.calcAngDistance(p2[U:W+1], q2[U:W+1])
            if np.any(dp2q2 < 1e-7) or dp2q2 / np.max(dq) < 0.2: continue # 二つの三角形が近いのでスキップ(検証に不適切)

            # 三角形 P をカタログから検索し C とする
            c = catalog.searchTriangle(dp01, dp12, dp20, self.catalog.matchLimit/100.0, self.catalog.magLimit) # 相似な三角形を取得
            catalogTotal += len(c)
            if 0 == len(c): continue # 相似の三角形が見つからないのでスキップ

            # 三角形 Q をカタログから検索し G とする
            g = catalog.searchTriangle(dq01, dq12, dq20, self.catalog.matchLimit/100.0, self.catalog.magLimit) # 相似な三角形を取得
            catalogTotal += len(g)
            if 0 == len(g): continue # 相似の三角形が見つからないのでスキップ
            
            # C G の 1,2 点目共にが同じ ID 物を抽出
            cid0 = c[:, 0, ID].astype(np.uint64)
            cid1 = c[:, 1, ID].astype(np.uint64)
            gid0 = g[:, 0, ID].astype(np.uint64)
            gid1 = g[:, 1, ID].astype(np.uint64)
            cid01Hash = cid0 * 0x9E3779B97F4A7C15 + cid1 # 2^64 / φ
            gid01Hash = gid0 * 0x9E3779B97F4A7C15 + gid1 # 2^64 / φ
            _, cidx, gidx = np.intersect1d(cid01Hash, gid01Hash, return_indices=True)
            
            if 0 < len(cidx) and 0 < len(gidx):
                idx = random.choice(len(cidx)) # 複数ある場合はランダムに選択
                c = c[cidx[idx]]
                g = g[gidx[idx]]
                
                # 画像 4 点とカタログ 4 点が相似だった
                currentInliers = 4
                currentMatched = [
                    nh.array([float(cat[ID ]),
                              float(cat[RA ]),
                              float(cat[DEC]),
                              float(cat[MAG]),
                              float(sta[X  ]),
                              float(sta[Y  ]),
                              float(sta[BRI]),
                              float(sta[AR ]),
                              float(sta[U  ]),
                              float(sta[V  ]),
                              float(sta[W  ]),
                    ]) for cat,sta in ((c[0],p[0]),(c[1],p[1]),(c[2],p[2]),(g[2],q[2]))
                ]
                
                currentCatalogIds = [
                    c[0,0],
                    c[1,0],
                    c[2,0],
                    g[2,0],
                ]
                
                # 確定済み以外の星配列を作成
                otherStars = stars[np.logical_not(np.isin(np.arange(starCnt), pidx) | np.isin(np.arange(starCnt), qidx))]
                
                # 一致した星に対し、画像内の全星について位置関係をランダムに検証
                indices = random.choice(len(otherStars), len(otherStars), replace=False)
                for j, idx in enumerate(indices):
                    if currentInliers + len(otherStars) - j < bestMatchCount:
                        # このあと全て inlier でも bestMatchCount に届かないので早期終了 
                        break
                    
                    p0 = otherStars[idx]
                    idx = random.choice(len(currentMatched), 2, replace=False) # currentMatched の中からランダムに 2 つ選択する。
                    n1 = currentMatched[idx[0]]
                    n2 = currentMatched[idx[1]]
                    
                    if 0 < (n1[X] - p0[X]) * (n2[Y] - p0[Y]) - (n1[Y] - p0[Y]) * (n2[X] - p0[X]):
                        n1,n2 = n2,n1 # 時計回りに修正
                    
                    dp01 = self.calcAngDistance(p0[U:W+1], n1[U:W+1])
                    dp12 = self.calcAngDistance(n1[U:W+1], n2[U:W+1])
                    dp20 = self.calcAngDistance(n2[U:W+1], p0[U:W+1])
                    dp = np.stack([dp01, dp12, dp20])
                    
                    # 検証に不適切な三角形をスキップする
                    if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ
                    
                    # カタログから検索
                    c = catalog.searchTriangle(dp01, dp12, dp20, self.catalog.matchLimit/100.0, self.catalog.magLimit, (None, n1[ID], n2[ID]))
                    catalogTotal += len(c)
                    c = c[np.all(c[:,0,0,np.newaxis] != nh.array([currentCatalogIds]), axis=1)] # 既知の点を除く
                    if 0 < len(c):
                        c0 = c[random.choice(len(c)),0] # 複数候補からランダムに選択
                    elif j < 1:
                        break # 安易に見つかるはずのタイミングで失敗したので早期終了
                    else:
                        continue # 相似の三角形が見つからないのでスキップ
                    
                    currentInliers += 1
                    currentMatched.append(
                        nh.array([float(c0[ID ]),
                                  float(c0[RA ]),
                                  float(c0[DEC]),
                                  float(c0[MAG]),
                                  float(p0[X  ]),
                                  float(p0[Y  ]),
                                  float(p0[BRI]),
                                  float(p0[AR ]),
                                  float(p0[U  ]),
                                  float(p0[V  ]),
                                  float(p0[W  ]),
                        ])
                    )
                    
                    #重複チェック
                    x1s, x2s = np.triu_indices(len(currentMatched), k=1) # 表の右上だけ選択
                    for x1,x2 in zip(x1s,x2s):
                        assert np.all(currentMatched[x1][ID] != currentMatched[x2][ID]), "重複が発生しています。"
                    
                    currentCatalogIds.append(c0[ID])
                
                # インライア数が閾値を超えた場合、モデル情報を更新
                if 3 <= currentInliers and bestMatchCount <= currentInliers:
                    currentMatched.sort(key=lambda x: x[MAG]) # カタログ等級順にソート
                    # 誤差算出
                    # 画像側とカタログ側の全ペア間角距離マトリクス (N x N)を作成
                    p = nh.array([star[U :W+1  ] for star in currentMatched])
                    c = nh.array([star[RA:DEC+1] for star in currentMatched])
                    dp = self.calcAngDistance(  p[:, np.newaxis, :], p[np.newaxis, :, :])
                    dc = catalog.angularDistance(c[:, np.newaxis, :], c[np.newaxis, :, :])
                    assert isinstance(dc, np.ndarray), "this should be a numpy array"
                    currentError = self.calcError( dp, dc)
                    
                    # インライア数が同じでも、誤差が小さい方が優先
                    if bestMatchCount < currentInliers or currentError < bestMatchError:
                        bestMatchCount = currentInliers
                        bestMatchError = currentError
                        bestMatchStars = currentMatched
                
                if(   5 <= bestMatchCount
                  and self.star.minMatchedStars <= bestMatchCount
                  and bestMatchError < self.catalog.matchLimit/100.0
                  and np.log(1-0.9999) / np.log(1-(bestMatchCount/starCnt)**4) < i # 初期一致数(最小インライア数):4
                  ):
                    # 99.99% の確率で外れ値を除外するのに十分な試行回数に到達
                    break
        i += 1
        
        if 3 <= bestMatchCount:
            # RANSAC 結果から向きと画角を推定する(デバッグ用)
            from utils.Debug import Debug
            if Debug.isTestMode() or Debug.LEVEL_NONE < Debug.LEVEL:
                import cv2
                from utils import numpy_helpers as nh
                src_pts = nh.array([[star[X ], star[Y  ]] for star in bestMatchStars])
                dst_pts = nh.array([[star[RA], star[DEC]] for star in bestMatchStars])
                M, inliers_mask = cv2.estimateAffine2D(src_pts, dst_pts)
                if M is not None:
                    center = nh.array([width / 2.0, height / 2.0, 1.0])
                    coords = M @ center
                    est_ra, est_dec = coords[0], coords[1]
                else:
                    est_ra, est_dec = np.mean(dst_pts[:, 0]), np.mean(dst_pts[:, 1])
                
                s = bestMatchStars
                
                dc = [
                    Catalog.angularDistance(s[0][RA:DEC+1], s[1][RA:DEC+1]),
                    Catalog.angularDistance(s[1][RA:DEC+1], s[2][RA:DEC+1]),
                    Catalog.angularDistance(s[2][RA:DEC+1], s[0][RA:DEC+1]),
                ]
                dcMean = np.mean(dc)
                
                dp = [
                    np.hypot(s[0][X]-s[1][X], s[0][Y]-s[1][Y]),
                    np.hypot(s[1][X]-s[2][X], s[1][Y]-s[2][Y]),
                    np.hypot(s[2][X]-s[0][X], s[2][Y]-s[0][Y]),
                ]
                apMean = np.mean(dp)
                
                est_fov  = np.hypot(width, height) * (dcMean / apMean)
                
                n = int(np.log10(starCnt))+1
                debug  = f"estimated"
                debug += f" ra:{ est_ra :-07.3f}"
                debug += f" dec:{est_dec:+07.3f}"
                debug += f" fov:{est_fov:-07.3f}"
                debug += f" ransac:"
                debug += f" inlier:{bestMatchCount:0{n}d}/{starCnt:0{n}d}"
                debug += f" catalog:{catalogTotal//i}"
                debug += f" error:{bestMatchError:0.3f}"
                debug += f" iter:{i}"
                Debug.log(type(self).__name__, f"{debug}")
            return bestMatchStars
        else:
            from utils.Debug import Debug
            n = int(np.log10(starCnt))+1
            debug  = f"failed ransac:"
            debug += f" inlier:{bestMatchCount:0{n}d}/{starCnt:0{n}d}"
            debug += f" catalog:{catalogTotal//i}"
            debug += f" error:{bestMatchError:0.3f}"
            debug += f" iter:{i}"
            Debug.log(type(self).__name__, f"{debug}")
            return []
    
    def calcAngDistance(self, vector0:np.ndarray, vector1:np.ndarray) -> np.ndarray:
        """2点への単位 vector の角距離を求める
        Args:
            vector0: 1つ目の単位 vector [[x,y,z],...]
            vector1: 2つ目の単位 vector [[x,y,z],...]
        Returns:
            2点間の角距離 (度)
        """
        import numpy as np
        cosTheta = np.vecdot(vector0, vector1)  # ベクトルの内積 x1*x2 + y1*y2 + z1*z2
        cosTheta = np.clip(cosTheta, -1.0, 1.0) # 浮動小数点誤差により -1.0 未満や 1.0 を超えることがあるのでクリップ
        return np.degrees(np.arccos(cosTheta))
    
    def calcError(self, d0:np.ndarray, d1:np.ndarray) -> float:
        """星の配置から誤差を計算する
        
        Args:
            d0: 星が作る形の辺長
            d1: 星が作る形の辺長
        Returns:
            誤差
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        assert len(d0) == len(d1), "Arrays must be of the same length"
        
        # カタログ側で 2σ 以上離れた角距離を排除
        x1, x2 = np.triu_indices(len(d1), k=1) # 表の右上だけ選択
        d1h = d1[x1, x2]
        d1h = np.sort(d1h)[:len(d1)] # 簡単な図形で考えた場合、外周は短い辺となるので、短い側を採用して統計を採る
        mean = np.mean(d1h)
        std = np.std(d1h)
        valid = (0 < d1) & (d1 < mean + 2.0 * std) # カタログ側で 2σ より短い接続を残す
        # 全点で隣接する2辺の角距離で比を計算する
        d0Ratio = []
        d1Ratio = []
        
        for j in range(len(d1)):
            xIdx = np.where(valid[j])[0]
            if 2 <= len(xIdx):
                x1, x2 = np.triu_indices(len(xIdx), k=1) # 表の右上だけ選択
                x1idx = xIdx[x1]
                x2idx = xIdx[x2]
                d0Ratio.extend(d0[j, x1idx] / d0[j, x2idx]) # 画像側2辺の比
                d1Ratio.extend(d1[j, x1idx] / d1[j, x2idx]) # カタログ側2辺の比
        
        if 0 == len(d0Ratio) or 0 == len(d1Ratio):
            error = np.inf
        else:
            d0Ratio = nh.array(d0Ratio)
            d1Ratio = nh.array(d1Ratio)
            # RMS を計算し error 値とする
            diff = (d0Ratio - d1Ratio) / d0Ratio # 分母に画像側を持ってきているのはカタログ検索(catalog.searchTriangle)の仕様に合わせる為
            error = np.sqrt(np.mean(diff**2))
        
        return error
    
    def createFlowData(self, inputData:FlowData, catalog:Catalog, matchedStars:list) -> FlowData:
        """星リストから Table 型 FlowData を作成"""
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        from base import FlowData
        
        # 等級でソート
        matchedStars.sort(key=lambda x: x[MAG])

        symbol = catalog.getSymbol()
        columns = ['ra', 'dec', 'mag', 'x', 'y', 'brightness']
        lines   = [f"{symbol}{int(star[ID])}" for star in matchedStars]

        tableRows = []
        for star in matchedStars:
            row = [
                star[RA ],
                star[DEC],
                star[MAG],
                star[X  ],
                star[Y  ],
                star[BRI],
            ]
            tableRows.append(row)

        if 0 < len(tableRows):
            tableArray = nh.array(tableRows, dtype=nh.BDTYPE)
        else:
            tableArray = nh.zeros((0, len(columns)), dtype=nh.BDTYPE)

        # headers を生成
        headers = inputData.headers.copy()
        headers.update({
            'category': self.getOutputCategory(),
            'type'    : 'table',
            'mode'    : '2D',
            'columns' : columns,
            'lines'   : lines,
            'planes'  : ['star_identification'],
        })
        
        flowData = FlowData(headers)
        rows, cols = tableArray.shape
        flowData.setDimensions(cols, rows)

        for y in range(0, rows, BLOCK_SIZE):
            blockHeight = min(BLOCK_SIZE, rows - y)
            blockData   = tableArray[y:y + blockHeight, :]
            flowData.setBlock(DataBlock(blockData, 0, 0, y))

        return flowData
    
    def createSettingWindow(self):
        """設定ダイアログを作成"""
        return StarIdentificationSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config =(f"{self.minorType}_"
                 f"{self._outputCat}_"
                 f"{self.fovDeg}_"
                 f"{self.useHeaderFovDeg}_"
                 f"{self.catalog.matchLimit}_"
                 f"{self.catalog.magLimit}_"
                 f"{self.star.grid.rows}_"
                 f"{self.star.grid.cols}_"
                 f"{self.star.grid.starsPerGrid}_"
                 f"{self.star.minMatchedStars}"
                 f"{self.star.ransac.iterations}_"
                 f"{self.star.ransac.seed}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class StarIdentificationSettingsDialog(tk.Toplevel):
    """StarIdentificationNode 用設定ダイアログ"""
    
    def __init__(self, parent, node:StarIdentificationNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("450x400")
        
        self._createWidgets()
    
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 画像パラメーター
        tk.Label(mainFrame, text="■ 画像パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 画角
        fovDegFrame = tk.Frame(mainFrame)
        fovDegFrame.pack(fill=tk.X, pady=2)
        tk.Label(fovDegFrame, text="  画角:").pack(side=tk.LEFT)
        self.fovDegEntry = tk.Entry(fovDegFrame, width=6)
        self.fovDegEntry.insert(0, str(self.node.fovDeg))
        self.fovDegEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(fovDegFrame, text="deg").pack(side=tk.LEFT)
        self.useHeaderFovDegVar = tk.BooleanVar(value=self.node.useHeaderFovDeg)
        tk.Checkbutton(fovDegFrame, text="ヘッダー情報から画角を推定", variable=self.useHeaderFovDegVar).pack(side=tk.LEFT)
        
        # カタログ照合パラメーター
        tk.Label(mainFrame, text="■ カタログ照合パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 許容半径
        radFrame = tk.Frame(mainFrame)
        radFrame.pack(fill=tk.X, pady=2)
        tk.Label(radFrame, text="  照合許容半径:").pack(side=tk.LEFT)
        self.catalogMatchLimitEntry = tk.Entry(radFrame, width=6)
        self.catalogMatchLimitEntry.insert(0, str(self.node.catalog.matchLimit))
        self.catalogMatchLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(radFrame, text="% (カタログとのズレ許容比)").pack(side=tk.LEFT)
        
        # 等級上限
        magFrame = tk.Frame(mainFrame)
        magFrame.pack(fill=tk.X, pady=2)
        tk.Label(magFrame, text="  等級上限:").pack(side=tk.LEFT)
        self.magLimitEntry = tk.Entry(magFrame, width=6)
        self.magLimitEntry.insert(0, str(self.node.catalog.magLimit))
        self.magLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(magFrame, text="mag (カタログの暗い星を除外)").pack(side=tk.LEFT)
        
        # 星像選択パラメーター
        tk.Label(mainFrame, text="■ 星像選択パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(8, 2))
        
        # グリッド設定
        gridFrame = tk.Frame(mainFrame)
        gridFrame.pack(fill=tk.X, pady=2)
        tk.Label(gridFrame, text="  グリッド:").pack(side=tk.LEFT)
        self.gridRowsEntry = tk.Entry(gridFrame, width=5)
        self.gridRowsEntry.insert(0, str(self.node.star.grid.rows))
        self.gridRowsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="x").pack(side=tk.LEFT)
        self.gridColsEntry = tk.Entry(gridFrame, width=5)
        self.gridColsEntry.insert(0, str(self.node.star.grid.cols))
        self.gridColsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="(星像選択用分割数)").pack(side=tk.LEFT)
        
        # グリッド当たりの選択星数
        starsFrame = tk.Frame(mainFrame)
        starsFrame.pack(fill=tk.X, pady=2)
        tk.Label(starsFrame, text="  グリッド当たり星数:").pack(side=tk.LEFT)
        self.starsPerGridEntry = tk.Entry(starsFrame, width=5)
        self.starsPerGridEntry.insert(0, str(self.node.star.grid.starsPerGrid))
        self.starsPerGridEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから選ぶ星数)").pack(side=tk.LEFT)
        
        # 少なくとも同定したい星の数
        minMatchedStarsFrame = tk.Frame(mainFrame)
        minMatchedStarsFrame.pack(fill=tk.X, pady=2)
        tk.Label(minMatchedStarsFrame, text="  少なくとも同定したい星の数:").pack(side=tk.LEFT)
        self.minMatchedStarsEntry = tk.Entry(minMatchedStarsFrame, width=5)
        self.minMatchedStarsEntry.insert(0, str(self.node.star.minMatchedStars))
        self.minMatchedStarsEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(minMatchedStarsFrame, text="個 (検索の終了を許可する数)").pack(side=tk.LEFT)
        
        # RANSAC試行回数
        ransacFrame = tk.Frame(mainFrame)
        ransacFrame.pack(fill=tk.X, pady=2)
        tk.Label(ransacFrame, text="  RANSAC試行回数:").pack(side=tk.LEFT)
        self.ransacEntry = tk.Entry(ransacFrame, width=5)
        self.ransacEntry.insert(0, str(self.node.star.ransac.iterations))
        self.ransacEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(ransacFrame, text="回 (外れ値耐性用繰り返し回数)").pack(side=tk.LEFT)
        
        # RANSAC乱数シード
        seedFrame = tk.Frame(mainFrame)
        seedFrame.pack(fill=tk.X, pady=2)
        tk.Label(seedFrame, text="  RANSAC乱数シード:").pack(side=tk.LEFT)
        self.ransacSeedEntry = tk.Entry(seedFrame, width=5)
        self.ransacSeedEntry.insert(0, str(self.node.star.ransac.seed))
        self.ransacSeedEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(seedFrame, text="(1以上、結果が悪い場合は変更)").pack(side=tk.LEFT)

        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            self.node.fovDeg                   = max(0.01, float(self.fovDegEntry.get()))
            self.node.useHeaderFovDeg          = self.useHeaderFovDegVar.get()
            self.node.catalog.matchLimit       = max(0.001, min(99.0, float(self.catalogMatchLimitEntry.get())))
            self.node.catalog.magLimit         = max(1, min(20, float(self.magLimitEntry.get())))
            self.node.star.grid.rows           = max(1, int(self.gridRowsEntry.get()))
            self.node.star.grid.cols           = max(1, int(self.gridColsEntry.get()))
            self.node.star.grid.starsPerGrid   = max(1, int(self.starsPerGridEntry.get()))
            self.node.star.minMatchedStars     = max(4, min(100, int(self.minMatchedStarsEntry.get())))
            self.node.star.ransac.iterations   = max(10, min(10000, int(self.ransacEntry.get())))
            self.node.star.ransac.seed         = max(1, int(self.ransacSeedEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
