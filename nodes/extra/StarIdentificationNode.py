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
        
        # 設定パラメータ
        # 画像パラメータ
        self.fovDeg                 = 3.5                   # 画角 [deg]
        self.useHeaderFovDeg        = False                 # 画像ヘッダから推定する
        
        # カタログ照合パラメータ
        self.catalog                = SimpleNamespace()
        self.catalog.matchLimit     = 1.0                   # カタログ照合許容比 [%]
        self.catalog.magLimit       = 8.0                   # カタログ等級上限 [mag]
        
        # 星像選択パラメータ
        self.star                   = SimpleNamespace()
        self.star.grid              = SimpleNamespace()
        self.star.grid.rows         = 1                     # グリッド行数
        self.star.grid.cols         = 1                     # グリッド列数
        self.star.grid.starsPerGrid = 8                     # グリッド当たりの選択星数
        self.star.ransac            = SimpleNamespace()
        self.star.ransac.iterations = 100                   # RANSAC試行回数
        self.star.ransac.seed       = 2725                  # RANSAC乱数シード
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nMatch:{self.catalog.matchLimit} %"
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
        if "ransacIterations" in nodeData:
            self.star.ransac.iterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.star.ransac.seed = nodeData["ransacSeed"]

    def preprocessStreams(self, inputStreams):
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
            flowData = self.createFlowData(flowData, matchedStars)
            outputFlowDatas.append(flowData)

        self.flowDatas = outputFlowDatas
        self.reportProgress(context, "完了")

    def _getCatalog(self) -> Catalog:
        """カタログデータを取得（入力ストリームまたはファイルから）"""
        from utils import numpy_helpers as nh
        from utils.catalog_helper import Catalog
        if self._catalogStream and self._catalogStream[0]:
            flowData = self._catalogStream[0]
            width, height = flowData.getDimensions()

            # Table FlowData から配列化
            table = nh.nans((height, width))
            for block in flowData.iterateBlocks():
                if block:
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    table[y:y+h, x:x+w] = block.data
            return Catalog(table)
            
        # ファイルから読み込み
        return Catalog()

    def _selectDistributedStars(self, stars, imageShape):
        """画像全体に分散した星を選択"""
        if 0 == len(stars):
            return stars, []

        h, w = imageShape
        gridRows, gridCols = self.star.grid.rows, self.star.grid.cols
        
        # 各グリッド領域のサイズ
        cellH = h // gridRows
        cellW = w // gridCols
        
        distributedStars   = []
        gridSelectedCounts = []

        # 各グリッドから最大 n 個の明るい星を選択
        for row in range(gridRows):
            for col in range(gridCols):
                yMin = row * cellH
                yEnd = (row + 1) * cellH if row < gridRows - 1 else h
                xMin = col * cellW
                xEnd = (col + 1) * cellW if col < gridCols - 1 else w

                # このグリッド内の星を抽出
                gridStars = [(x, y, br, ar) for x, y, br, ar in stars if xMin <= x < xEnd and yMin <= y < yEnd]
                
                # 明度順でソートして上位指定数を選択
                gridStars.sort(key=lambda x: x[2], reverse=True)
                selected = gridStars[:self.star.grid.starsPerGrid]
                distributedStars.extend(selected)
                gridSelectedCounts.append(len(selected))
        
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
        for name in ["x", "y", "brightness", "aspect_raito"]:
            idx = columns.index(name)
            stars.append(data[:,idx])
        stars = np.stack(stars, axis=1)
        
        # 元画像の大きさが分からないので大体のサイズを設定
        # 星均等に写っていると想定し、周囲の余白は同じであるとする。
        width, height = np.min(stars[:, 0:2], axis=0) + np.max(stars[:, 0:2], axis=0)
        
        # 画像側のサンプリング
        stars, _ = self._selectDistributedStars(stars, (height, width))
        starCnt = len(stars)
        if starCnt < 4:
            return []
        stars = nh.array(stars)
        
        # 星の座標をレンズ中心からの単位 vector に変換
        starsX = stars[:, 0] - (width / 2) # 中心を原点に
        starsY = stars[:, 1] - (height / 2) # 中心を原点に
        f = (width * width + height * height) ** 0.5 / (2.0 * np.tan(np.radians(self.fovDeg) / 2.0)) # 焦点距離を計算
        f = np.broadcast_to(f, starsX.shape)
        starsV = np.stack([starsX, starsY, f]).T
        starsV = starsV / np.linalg.norm(starsV, axis=1, keepdims=True) # 
        
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
            dp01 = self._calcAngDistance(p0[U:W+1], p1[U:W+1])
            dp12 = self._calcAngDistance(p1[U:W+1], p2[U:W+1])
            dp20 = self._calcAngDistance(p2[U:W+1], p0[U:W+1])
            dp = np.stack([dp01, dp12, dp20])
            if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)
            
            # 三角形 Q を作成
            q = stars[qidx]
            q0, q1, q2 = q
            dq01 = self._calcAngDistance(q0[U:W+1], q1[U:W+1])
            dq12 = self._calcAngDistance(q1[U:W+1], q2[U:W+1])
            dq20 = self._calcAngDistance(q2[U:W+1], q0[U:W+1])
            dq = np.stack([dq01, dq12, dq20])
            if np.any(dq < 1e-7) or np.min(dq) / np.max(dq) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)

            dp2q2 = self._calcAngDistance(p2[U:W+1], q2[U:W+1])
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
                    
                    dp01 = self._calcAngDistance(p0[U:W+1], n1[U:W+1])
                    dp12 = self._calcAngDistance(n1[U:W+1], n2[U:W+1])
                    dp20 = self._calcAngDistance(n2[U:W+1], p0[U:W+1])
                    dp = np.stack([dp01, dp12, dp20])
                    
                    # 検証に不適切な三角形をスキップする
                    if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ
                    
                    # カタログから検索
                    c = catalog.searchTriangle(dp01, dp12, dp20, self.catalog.matchLimit/100.0, self.catalog.magLimit, (None, n1[ID], n2[ID]))
                    catalogTotal += len(c)
                    c = c[np.all(c[:,0,0,np.newaxis] != nh.array([currentCatalogIds]), axis=1)] # 既知の点を除く
                    if 1 < len(c):
                        c0 = c[random.choice(len(c)),0] # 複数候補があるのでランダムに選択
                    elif 1 == len(c):
                        c0 = c[0,0] # 1つしか候補がない
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
                    p = nh.array([star for star in currentMatched])
                    c = nh.array([star for star in currentMatched])
                    dp = self._calcAngDistance(  p[:, np.newaxis, U:W+1   ], p[np.newaxis, :, U:W+1   ])
                    dc = catalog.angularDistance(c[:, np.newaxis, RA:DEC+1], c[np.newaxis, :, RA:DEC+1])
                    # カタログ側で 2σ 以上離れた角距離を排除
                    x1, x2 = np.triu_indices(currentInliers, k=1) # 表の右上だけ選択
                    dch = dc[x1, x2]
                    dch = np.sort(dch)[:currentInliers] # 簡単な図形で考えた場合、外周は短い辺となるので、短い側を採用して統計を採る
                    mean = np.mean(dch)
                    std = np.std(dch)
                    valid = (0 < dc) & (dc < mean + 2.0 * std) # カタログ側で 2σ より短い接続を残す
                    # 全点で隣接する2辺の角距離で比を計算する
                    dpRatio = []
                    dcRatio = []
                    for j in range(currentInliers):
                        xIdx = np.where(valid[j])[0]
                        if 2 <= len(xIdx):
                            x1, x2 = np.triu_indices(len(xIdx), k=1) # 表の右上だけ選択
                            x1idx = xIdx[x1]
                            x2idx = xIdx[x2]
                            dpRatio.extend(dp[j, x1idx] / dp[j, x2idx]) # 画像側2辺の比
                            dcRatio.extend(dc[j, x1idx] / dc[j, x2idx]) # カタログ側2辺の比
                    if 0 == len(dpRatio) or 0 == len(dcRatio):
                        currentError = np.inf
                    else:
                        dpRatio = nh.array(dpRatio)
                        dcRatio = nh.array(dcRatio)
                        # RMS を計算し error 値とする
                        diff = (dpRatio - dcRatio) / dpRatio # 分母に画像側を持ってきているのはカタログ検索(catalog.searchTriangle)の仕様に合わせる為
                        currentError = np.sqrt(np.mean(diff**2))
                    
                    # インライア数が同じでも、誤差が小さい方が優先
                    if bestMatchCount < currentInliers or currentError < bestMatchError:
                        bestMatchCount = currentInliers
                        bestMatchError = currentError
                        bestMatchStars = currentMatched
                
                if(   5 <= bestMatchCount
                  and bestMatchError < self.catalog.matchLimit/100.0
                  and np.log(1-0.9999) / np.log(1-(bestMatchCount/starCnt)**4) < i # 初期一致数(最小インライア数):4
                  ):
                    # 99.99% の確率で外れ値を除外するのに十分な試行回数に到達
                    break
        i += 1
        
        if 3 <= bestMatchCount:
            # RANSAC 結果から向きと画角を推定する(デバッグ用)
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
            
            from utils.Debug import Debug
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
    
    def _calcAngDistance(self, vector0:np.ndarray, vector1:np.ndarray) -> np.ndarray:
        """2点への単位 vector の角距離を求める
        Args:
            vector0: 1つ目の単位 vector [[x,y,z],...]
            vector1: 2つ目の単位 vector [[x,y,z],...]
        Returns:
            2点間の角距離 (度)
        """
        import numpy as np
        from utils.catalog_helper import Catalog
        cosTheta = np.vecdot(vector0, vector1, axis=-1)     # ベクトルの内積 x1*x2 + y1*y2 + z1*z2
        cosTheta = np.clip(cosTheta, -1.0, 1.0) # 浮動小数点誤差により -1.0 未満や 1.0 を超えることがあるのでクリップ
        return np.degrees(np.arccos(cosTheta))

    def __calcAngDistance(self, x1:np.ndarray|float, y1:np.ndarray|float, x2:np.ndarray|float, y2:np.ndarray|float, w:int, h:int, fovDeg:float) -> np.ndarray|float:
        """画像上の2点から角距離を求める（中心投影レンズを前提）
        
        Args:
            x1: 点1のx
            y1: 点1のy
            x2: 点2のx
            y2: 点2のy
            w: 画像幅
            h: 画像高さ
            fovDeg: 対角画角 (度)
        Returns:
            2点間の角距離 (度)
        """
        import numpy as np
        cx, cy = w / 2.0, h / 2.0                           # 画像の中心座標
        diagonalPx = np.sqrt(w**2 + h**2)                   # 画像の対角線サイズ [px]
        fovRd = np.radians(fovDeg)
        fPx = diagonalPx / (2.0 * np.tan(fovRd / 2.0))      # 焦点距離 f [px] レンズから投影面までの距離
        v1_x, v1_y = x1 - cx, y1 - cy                       # 中央からのベクトル1
        v2_x, v2_y = x2 - cx, y2 - cy                       # 中央からのベクトル2
        dot_product = v1_x * v2_x + v1_y * v2_y + fPx * fPx # ベクトルの内積 x1*x2 + y1*y2 + z1*z2
        norm_v1 = np.sqrt(v1_x**2 + v1_y**2 + fPx**2)       # レンズから投影点までの距離
        norm_v2 = np.sqrt(v2_x**2 + v2_y**2 + fPx**2)       # レンズから投影点までの距離
        cosTheta = dot_product / (norm_v1 * norm_v2)        # レンズから見た2点のコサイン値
        cosTheta = np.clip(cosTheta, -1.0, 1.0)             # 浮動小数点誤差による 1.0 超え/ -1.0 未満をクリップ
        rad = np.arccos(cosTheta)                           # レンズから見た2点の角度
        return np.degrees(rad)

    def _calcStarRatio(self, star:np.ndarray|list, w:int, h:int, fovDeg:float) -> np.ndarray:
        """星の配置からレートを計算する
        star に列方向に組になる星を入れ、行方向は任意で無くてもよい。
        例: 3点の組み合わせが3組ある場合
           [[p00, p01, p02],     [[ratio001, ratio012, ratio020]
            [p10, p11, p12],  ->  [ratio101, ratio112, ratio120]
            [p20, p21, p22]]      [ratio201, ratio212, ratio220]]
        例: 3点の組み合わせが1組しかない場合、以下でもよい
            [p00, p01, p02]   ->  [ratio001, ratio012, ratio020]
        
        Args:
            star: 星の座標と明るさ [[[x, y, brightness],...],...]
            w: 画像幅
            h: 画像高さ
            fovDeg: 対角画角 (度)
        Returns:
            ratio配列 [[ratio01, ratio12, ratio2x, ratioxy,...],...]
        Raises:
            ValueError: 星が3点未満の場合
        """
        import numpy as np
        # n点間の距離(位置差)を計算 (n-1番目は0との差)
        # n点間の輝度差を計算 (n-1番目は0との差)
        return self._calcRatio(star,
                               lambda s0, s1: (self._calcAngDistance(s0[:, :, 0], s0[:, :, 1], s1[:, :, 0], s1[:, :, 1], w, h, fovDeg)),
                               lambda s0, s1: (s0[:, :, 2] - s1[:, :, 2])
                              )
    
    def _calcCatalogRatio(self, star:np.ndarray|list) -> np.ndarray:
        """星の配置からレートを計算する
        star に列方向に組になる星を入れ、行方向は任意で無くてもよい。
        例: 3点の組み合わせが3組ある場合
           [[p00, p01, p02],     [[ratio001, ratio012, ratio020]
            [p10, p11, p12],  ->  [ratio101, ratio112, ratio120]
            [p20, p21, p22]]      [ratio201, ratio212, ratio220]]
        例: 3点の組み合わせが1組しかない場合、以下でもよい
            [p00, p01, p02]   ->  [ratio001, ratio012, ratio020]
        
        Args:
            star: 星の座標と明るさ [[[id, ra, deg, mag],...],...]
        Returns:
            ratio配列 [[ratio01, ratio12, ratio2x, ratioxy,...],...]
        Raises:
            ValueError: 星が3点未満の場合
        """
        from utils.catalog_helper import Catalog
        # n点間の角距離(位置差)を計算 (n-1番目は0との差)
        # n点間の輝度差を計算 (n-1番目は0との差) ポグソンの式:m1 - m2 = -2.5 log10 (l1 - l2) 実装は m2 を0等級を基準(1)とした
        return self._calcRatio(star,
                               lambda s0, s1: Catalog.angularDistance(s0[:, :, RA:DEC+1], s1[:, :, RA:DEC+1]),
                               lambda s0, s1: (10.0**(s0[:, :, 3] / -2.5) - (10.0**(s1[:, :, 3] / -2.5)))
                              )
    
    def _calcRatio(self, star:np.ndarray|list, func0, func1) -> np.ndarray:
        """星の配置からレートを計算する
        計算式をテンプレートパターンで外部から得る
        Args:
            star: 星の情報
            func0: 距離計算関数
            func1: 等級計算関数
        Returns:
            ratio配列 [[ratio01, ratio12, ratio2x, ratioxy,...],...]
        Raises:
            ValueError: 星が3点未満の場合
        """
        import numpy as np
        
        star = np.asanyarray(star)
        if 2 == star.ndim:
            _star = star[np.newaxis, ...]
        else:
            _star = star
        
        if _star.shape[1] < 3:
            raise ValueError("入力には少なくとも3点の星が必要です。")
        
        # n点間の差を計算 (n-1番目は0との差)
        # (原点の影響を消す)
        _starN = np.roll(_star, shift=-1, axis=1)
        diff0 = func0(_star, _starN)
        diff1 = func1(_star, _starN)
        
        # n点間の比を計算 (n-1番目は0との比)
        # (単位の影響を消す)
        ratio0 = diff0 / np.roll(diff0, shift=-1, axis=1)
        ratio1 = diff1 / np.roll(diff1, shift=-1, axis=1)
        
        # 算出した比を結合
        ratio = ratio0 # np.concatenate([ratio0, ratio1], axis=1)
        
        if 2 == star.ndim:
            return ratio[0]
        else:
            return ratio
    
    def createFlowData(self, inputData:FlowData, matchedStars:list) -> FlowData:
        """星リストから Table 型 FlowData を作成"""
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        from base import FlowData
        
        # 等級でソート
        matchedStars.sort(key=lambda x: x[MAG])
        
        columns = ['ra', 'dec', 'mag', 'x', 'y', 'brightness']
        lines   = [f"HIP{int(star[ID])}" for star in matchedStars]

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
            'planes'  : ['star_extraction'],
        })
        
        flowData = FlowData(headers)
        rows, cols = tableArray.shape
        flowData.setDimensions(cols, rows)

        for y in range(0, rows, BLOCK_SIZE):
            blockHeight = min(BLOCK_SIZE, rows - y)
            blockData   = tableArray[y:y + blockHeight, :]
            flowData.setBlock(DataBlock(blockData, 0, 0, y))

        return flowData
    
    def _flowDataToImage(self, flowData:FlowData, planeIndex:int|None = None, normalizeForDetection:bool = False) -> np.ndarray:
        """FlowDataから画像配列を構築"""
        import numpy as np
        from utils import numpy_helpers as nh

        width, height = flowData.getDimensions()
        
        if planeIndex is None:
            # 全プレーンを使用（従来の動作）
            image   = nh.zeros((height, width))
            invalid = np.ones((height, width), dtype=bool)
            for block in flowData.iterateBlocks():
                if block:
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    image[y:y+h, x:x+w] += block.data
                    invalid[y:y+h, x:x+w] &= np.isnan(block.data)
            image[invalid] = nh.nan
        else:
            # 特定プレーンのみを使用
            image = nh.nans((height, width))
            for block in flowData.iterateBlocks(planeIndex):
                if block:
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    image[y:y+h, x:x+w] = block.data
        
        # 星検出用の正規化処理（統計的手法）
        if normalizeForDetection:
            mean_val = np.nanmean(image)
            std_val  = np.nanstd(image)
            if std_val > 0:
                image = (image - mean_val) / std_val
                image = np.clip((image + 3) / 6 * 255, 0, 255)
                np.nan_to_num(image, nan=127, copy=False)
                image = image.astype(np.uint8)
            else:
                image = np.zeros((height, width), dtype=np.uint8)
        
        return image
    
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
                 f"{self.star.ransac.iterations}_"
                 f"{self.star.ransac.seed}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class StarIdentificationSettingsDialog(tk.Toplevel):
    """StarIdentificationNode 用設定ダイアログ"""
    
    def __init__(self, parent, node:StarExtractionNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("450x350")
        
        self._createWidgets()
    
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 画像パラメータ
        tk.Label(mainFrame, text="■ 画像パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
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
        
        # カタログ照合パラメータ
        tk.Label(mainFrame, text="■ カタログ照合パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
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
        
        # 星像選択パラメータ
        tk.Label(mainFrame, text="■ 星像選択パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(8, 2))
        
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
        self.starsPerGridEntry = tk.Entry(starsFrame, width=10)
        self.starsPerGridEntry.insert(0, str(self.node.star.grid.starsPerGrid))
        self.starsPerGridEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから選ぶ星数)").pack(side=tk.LEFT)
        
        # RANSAC試行回数
        ransacFrame = tk.Frame(mainFrame)
        ransacFrame.pack(fill=tk.X, pady=2)
        tk.Label(ransacFrame, text="    RANSAC試行回数:").pack(side=tk.LEFT)
        self.ransacEntry = tk.Entry(ransacFrame, width=5)
        self.ransacEntry.insert(0, str(self.node.star.ransac.iterations))
        self.ransacEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(ransacFrame, text="回 (外れ値耐性用繰り返し回数)").pack(side=tk.LEFT)
        
        # RANSAC乱数シード
        seedFrame = tk.Frame(mainFrame)
        seedFrame.pack(fill=tk.X, pady=2)
        tk.Label(seedFrame, text="    RANSAC乱数シード:").pack(side=tk.LEFT)
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
            self.node.star.ransac.iterations   = max(10, min(10000, int(self.ransacEntry.get())))
            self.node.star.ransac.seed         = max(1, int(self.ransacSeedEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
