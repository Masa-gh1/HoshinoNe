'''
StarExtractionNode - 星抽出ノード

画像から天体（星点）を検出し、星カタログ（HIP2等）と照合して確定した星のリストを生成するノード

Copyright (c) 2026 Masakazu Inoue
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

class StarExtractionNode(FlowNode, ConfigurableNode):
    """画像から星点を抽出し、カタログデータと照合して星リストを出力するノード"""
    
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'star_extraction'
    # ノード名
    name      = '星抽出'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # 設定パラメータ (ShiftDetectionNodeの星検出設定を完全継承)
        self.usePreviousOffset   = False                      # 前の画像の方向を考慮する
        self.alignmentPlane      = 1                          # 位置合わせ用プレーン (0:R, 1:G, 2:B ...)
        self.saturationThreshold = 95                         # 飽和閾値 [%]
        
        # 星点検出パラメータ
        self.star                     = SimpleNamespace()
        self.star.threshold           = 95                    # 星検出閾値 [%]
        self.star.useSaturationMask   = False                 # 飽和マスクを使用する
        self.star.minDiameter         = 2                     # 星最小直径 [px]
        self.star.maxDiameter         = 16                    # 星最大直径 [px]
        self.star.maxAspectRatio      = 2.0                   # 星の最大アスペクト比
        self.star.grid                = SimpleNamespace()
        self.star.grid.rows           = 3                     # グリッド行数
        self.star.grid.cols           = 3                     # グリッド列数
        self.star.grid.starsPerGrid   = 8                     # グリッド当たりの選択星数
        self.star.ransac              = SimpleNamespace()
        self.star.ransac.sampleRadius = 100                   # RANSAC対応点サンプル半径 [px]
        self.star.ransac.iterations   = 100                   # RANSAC試行回数
        self.star.ransac.seed         = 2725                  # RANSAC乱数シード
        
        # 画像パラメータ
        self.fovDeg            = 3.5                          # 画角 [deg]
        self.useHeader         = False                        # 画像ヘッダから推定する
        
        # カタログ照合パラメータ
        self.catalog            = SimpleNamespace()
        self.catalog.matchLimit = 5                            # カタログ照合許容比 [%]
        self.catalog.magLimit   = 8.0                          # カタログ等級上限 [mag]

        self.explore            = SimpleNamespace()
        self.explore.ra         = 255.996                      # 探索赤経 [deg]
        self.explore.dec        = -11.381                      # 探索赤緯 [deg]
        self.explore.fovDeg     = 3.5                          # 探索画角 [deg]
        self.useExplore         = False                        # 探索範囲を使用するか
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nThr:{self.star.threshold}% Match:{self.catalog.matchLimit} %"
        return displayText

    def store(self, nodeData):
        """ノード設定を辞書に保存"""
        nodeData["usePreviousOffset"]   = self.usePreviousOffset
        nodeData["alignmentPlane"]      = self.alignmentPlane
        nodeData["saturationThreshold"] = self.saturationThreshold
        nodeData["starThreshold"]       = self.star.threshold
        nodeData["useSaturationMask"]   = self.star.useSaturationMask
        nodeData["starMinDiameter"]     = self.star.minDiameter
        nodeData["starMaxDiameter"]     = self.star.maxDiameter
        nodeData["maxAspectRatio"]      = self.star.maxAspectRatio
        nodeData["gridRows"]            = self.star.grid.rows
        nodeData["gridCols"]            = self.star.grid.cols
        nodeData["starsPerGrid"]        = self.star.grid.starsPerGrid
        nodeData["starSampleRadius"]    = self.star.ransac.sampleRadius
        nodeData["ransacIterations"]    = self.star.ransac.iterations
        nodeData["ransacSeed"]          = self.star.ransac.seed
        nodeData["fovDeg"]              = self.fovDeg
        nodeData["useHeader"]           = self.useHeader
        nodeData["catalog.matchLimit"]  = self.catalog.matchLimit
        nodeData["catalog.magLimit"]    = self.catalog.magLimit
        nodeData["explore.ra"]          = self.explore.ra
        nodeData["explore.dec"]         = self.explore.dec
        nodeData["explore.fovDeg"]      = self.explore.fovDeg
        nodeData["useExplore"]          = self.useExplore

    def restore(self, nodeData):
        """辞書からノード設定を復元"""
        if "usePreviousOffset" in nodeData:
            self.usePreviousOffset = nodeData["usePreviousOffset"]
        if "alignmentPlane" in nodeData:
            self.alignmentPlane = nodeData["alignmentPlane"]
        if "saturationThreshold" in nodeData:
            self.saturationThreshold = nodeData["saturationThreshold"]
        if "starThreshold" in nodeData:
            self.star.threshold = nodeData["starThreshold"]
        if "useSaturationMask" in nodeData:
            self.star.useSaturationMask = nodeData["useSaturationMask"]
        if "starMinDiameter" in nodeData:
            self.star.minDiameter = nodeData["starMinDiameter"]
        if "starMaxDiameter" in nodeData:
            self.star.maxDiameter = nodeData["starMaxDiameter"]
        if "maxAspectRatio" in nodeData:
            self.star.maxAspectRatio = nodeData["maxAspectRatio"]
        if "gridRows" in nodeData:
            self.star.grid.rows = nodeData["gridRows"]
        if "gridCols" in nodeData:
            self.star.grid.cols = nodeData["gridCols"]
        if "starsPerGrid" in nodeData:
            self.star.grid.starsPerGrid = nodeData["starsPerGrid"]
        if "starSampleRadius" in nodeData:
            self.star.ransac.sampleRadius = nodeData["starSampleRadius"]
        if "ransacIterations" in nodeData:
            self.star.ransac.iterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.star.ransac.seed = nodeData["ransacSeed"]
        if "fovDeg" in nodeData:
            self.fovDeg = nodeData["fovDeg"]
        if "useHeader" in nodeData:
            self.useHeader = nodeData["useHeader"]
        if "catalog.matchLimit" in nodeData:
            self.catalog.matchLimit = nodeData["catalog.matchLimit"]
        if "catalog.magLimit" in nodeData:
            self.catalog.magLimit = nodeData["catalog.magLimit"]
        if "explore.ra" in nodeData:
            self.explore.ra = nodeData["explore.ra"]
        if "explore.dec" in nodeData:
            self.explore.dec = nodeData["explore.dec"]
        if "explore.fovDeg" in nodeData:
            self.explore.fovDeg = nodeData["explore.fovDeg"]
        if "useExplore" in nodeData:
            self.useExplore = nodeData["useExplore"]

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
            
            # 画像プレーンを numpy 配列として取得
            planeIndex = min(self.alignmentPlane, flowData.getPlaneCount() - 1)
            imageArray = self._flowDataToImage(flowData, planeIndex=planeIndex, normalizeForDetection=True)
            
            # 星点を検出
            detectedStars = self._detectStars(imageArray)

            # カタログ照合
            matchedStars = self._matchCatalog(detectedStars, catalog, imageArray.shape, flowData.headers)

            # 出力 Table FlowData を作成
            outTable = self._createTableOutput(matchedStars, flowData.headers)
            outputFlowDatas.append(outTable)

        self.flowDatas = outputFlowDatas
        self.reportProgress(context, "完了")

    def _getCatalog(self) -> np.ndarray:
        """カタログデータを取得（入力ストリームまたはファイルから）"""
        from utils.catalog_helper import Catalog
        if self._catalogStream and self._catalogStream[0]:
            tableFlowData = self._catalogStream[0]
            width, height = tableFlowData.getDimensions()

            # Table FlowData から配列化
            table = nh.nans((height, width))
            for block in flowData.iterateBlocks(planeIndex):
                if block:
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    table[y:y+h, x:x+w] = block.data
            return Catalog(table)
            
        # ファイルから読み込み
        return Catalog()

    def _detectStars(self, image:np.ndarray):
        """
        画像から星を検出
        
        Args:
            image: 検出用グレースケール画像 (uint8)
            
        Returns:
            list[tuple[float, float, float, float]]: (cx, cy, brightness, aspectRatio) のリスト
        """
        import numpy as np
        import cv2

        # ガウシアンブラーでノイズ除去
        blurred = cv2.GaussianBlur(image, (3, 3), 0)

        # メディアンフィルタでバックグラウンドを推定
        background = cv2.medianBlur(blurred, 51)

        # バックグラウンドを減算
        subtracted = cv2.subtract(blurred, background)

        if self.star.useSaturationMask:
            # 飽和領域マスク
            saturationMask = self._createSaturationMask(subtracted)
            maskedSubtracted = np.where(saturationMask, subtracted, 0)
            subtracted = maskedSubtracted
            
        # 閾値処理
        threshold = np.nanpercentile(subtracted[subtracted > 0], self.star.threshold)
        _, binary = cv2.threshold(subtracted, threshold, 255, cv2.THRESH_BINARY)

        # 連結成分で星点を検出
        try:
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except (cv2.error, SystemError):
            # OpenCV 4.5.5以降のバグ対応
            from utils.Debug import Debug
            Debug.log(type(self).__name__,"Retry cv2.findContours")
            try:
                contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            except (cv2.error, SystemError):
                contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        stars = contours

        # 面積フィルタ
        minArea = np.pi * (self.star.minDiameter / 2.0) ** 2
        maxArea = np.pi * (self.star.maxDiameter / 2.0) ** 2
        areaFiltered = [c for c in stars if minArea <= cv2.contourArea(c) <= maxArea]
        stars = areaFiltered

        # アスペクト比フィルタ
        aspectFiltered = []
        aspectRatios   = []
        for star in stars:
            # 最小外接矩形（回転考慮）
            (center), (width, height), angle = cv2.minAreaRect(star)
            
            # アスペクト比計算
            if 0 < width and 0 < height:
                aspectRatio = max(width, height) / min(width, height)
                if aspectRatio <= self.star.maxAspectRatio:
                    aspectFiltered.append(star)
                    aspectRatios.append(aspectRatio)
        stars = aspectFiltered
        
        # 星の位置と明るさを取得
        
        
        
        positions    = []
        brightnesses = []
        for star in stars:
            # 星の重心と輝度を計算
            M = cv2.moments(star)
            if M['m00'] <= 0:
                positions.append(None)
                brightnesses.append(None)
            else:
                # 星の重心
                cx = float(M['m10'] / M['m00'])
                cy = float(M['m01'] / M['m00'])
                positions.append((cx, cy))
                
                # 星の明度を取得(広がりの合計)
                # 星は無限遠の点なので分散している明るさを合計する
                # 輪郭からマスクを作成して、星像を取得
                # 輪郭の少し外まで採る(直径を1.4倍)
                n = 1.41421356237
                x, y, w, h = cv2.boundingRect(star)

                # 星の外郭を n 倍
                _x = x - int((w * (n - 1)) / 2 + 1)
                _y = y - int((h * (n - 1)) / 2 + 1)
                _w = int(w * n + 2)
                _h = int(h * n + 2)
                w = _w - (_x if _x < 0 else 0)
                h = _h - (_y if _y < 0 else 0)
                x, y = max(_x, 0), max(_y, 0)
                w = min(w, subtracted.shape[1] - x)
                h = min(h, subtracted.shape[0] - y)

                # 最小マスクを作成
                offsetStar = star - [x, y]
                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.drawContours(mask, [offsetStar], -1, 255, thickness=cv2.FILLED) # 輪郭を取得
                r = np.sqrt(np.sum(mask > 0)/np.pi)
                k = int(np.ceil(r * (n - 1))) * 2 + 1
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)) # 輪郭を拡張
                mask = cv2.dilate(mask, kernel, iterations=1)
                
                # 元の画像からマスク部分を切り出し
                starAreaValues = subtracted[y:y+h, x:x+w][mask > 0]
                
                # 分散している明るさを合計
                if starAreaValues.size > 0:
                    brightness = float(np.sum(starAreaValues))
                    brightnesses.append(brightness)
                else:
                    brightnesses.append(None)

        ret = []
        for pos, brightness, aspectRatio in zip(positions, brightnesses, aspectRatios):
            if pos:
                cx, cy = pos
                ret.append((cx, cy, brightness, aspectRatio))

        return ret

    def _createSaturationMask(self, image:np.ndarray) -> np.ndarray:
        """飽和領域のマスクを作成"""
        import numpy as np
        import cv2
        
        maxVal = np.max(image)
        saturated = image > (maxVal * self.saturationThreshold / 100.0)
        
        # 飽和領域を膨張させて周辺も除外
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
        mask = cv2.dilate(saturated.astype(np.uint8), kernel, iterations=2)
        
        return mask == 0  # 有効領域のマスク

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
    
    def _matchCatalog(self, detectedStars:list, catalog:Catalog, imageShape:tuple, headers:dict):
        """
        画像座標と天球座標の間で投影（Mapping）を行わず、
        幾何学的な相似の比較のみで全星の同定（インライア判定）を行う。
        これにより、レンズ歪みの影響を最小化する。
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from utils.catalog_helper import Catalog
        
        if len(detectedStars) < 3 or catalog.count() < 3:
            return [], None
        
        h, w = imageShape
        np.random.seed(self.star.ransac.seed)
        
        # 画像側のサンプリング
        selectedStars, _ = self._selectDistributedStars(detectedStars, imageShape)
        starCnt = len(selectedStars)
        if starCnt < 4:
            return [], None
        selectedStars = np.array(selectedStars)
        
        # 探索結果
        bestMatchCount = 0
        bestMatchError = np.inf
        bestMatchedStars = []
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
            # 画像側で 4 点を選択し接する時計回りの三角形 2 つを作成する
            idx = np.random.choice(starCnt, 4, replace=False)
            idx = idx[COMB_TRIANGLE_PAIRS]
            star = selectedStars[idx] # 3点2組の組み合わせ
            s0x = star[:, :, 0, 0]
            s0y = star[:, :, 0, 1]
            s1x = star[:, :, 1, 0]
            s1y = star[:, :, 1, 1]
            s2x = star[:, :, 2, 0]
            s2y = star[:, :, 2, 1]
            valid = np.all(((s1x - s0x) * (s2y - s0y) - (s1y - s0y) * (s2x - s0x)) < 0, axis=1) # 時計回り判定
            sel = np.random.choice(np.where(valid)[0]) # valid==True の中から1つ選択
            pidx = idx[sel, 0]
            qidx = idx[sel, 1]
            
            # 三角形 P を作成
            p = selectedStars[pidx]
            p0, p1, p2 = p
            dp01 = self._calcAngDistance(p0[0], p0[1], p1[0], p1[1], w, h, self.fovDeg)
            dp12 = self._calcAngDistance(p1[0], p1[1], p2[0], p2[1], w, h, self.fovDeg)
            dp20 = self._calcAngDistance(p2[0], p2[1], p0[0], p0[1], w, h, self.fovDeg)
            dp = np.stack([dp01, dp12, dp20])
            if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)
            
            # 三角形 Q を作成
            q = selectedStars[qidx]
            q0, q1, q2 = q
            dq01 = self._calcAngDistance(q0[0], q0[1], q1[0], q1[1], w, h, self.fovDeg)
            dq12 = self._calcAngDistance(q1[0], q1[1], q2[0], q2[1], w, h, self.fovDeg)
            dq20 = self._calcAngDistance(q2[0], q2[1], q0[0], q0[1], w, h, self.fovDeg)
            dq = np.stack([dq01, dq12, dq20])
            if np.any(dq < 1e-7) or np.min(dq) / np.max(dq) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)

            dp2q2 = self._calcAngDistance(p2[0], p2[1], q2[0], q2[1], w, h, self.fovDeg)
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
            cid0 = c[:, 0, 0]
            cid1 = c[:, 1, 0]
            gid0 = g[:, 0, 0]
            gid1 = g[:, 1, 0]
            cid01 = (cid0.astype(np.int64) << 32) | cid1.astype(np.int64)
            gid01 = (gid0.astype(np.int64) << 32) | gid1.astype(np.int64)
            _, cidx, gidx = np.intersect1d(cid01, gid01, return_indices=True)
            
            if 0 < len(cidx) and 0 < len(gidx):
                idx = np.random.randint(len(cidx))
                c = c[cidx[idx]]
                g = g[gidx[idx]]
                
                # 画像 4 点とカタログ 4 点が相似だった
                currentInliers = 4
                currentMatched = [
                    { 'hip'        : float(cat[0]),
                      'ra'         : float(cat[1]),
                      'dec'        : float(cat[2]),
                      'mag'        : float(cat[3]),
                      'x'          : float(sta[0]),
                      'y'          : float(sta[1]),
                      'brightness' : float(sta[2]),
                    } for cat,sta in ((c[0],p[0]),(c[1],p[1]),(c[2],p[2]),(g[2],q[2]))
                ]
                
                currentCatalogIds = [
                    c[0,0],
                    c[1,0],
                    c[2,0],
                    g[2,0],
                ]
                
                # 確定済み以外の星配列を作成
                otherStars = selectedStars[np.logical_not(np.isin(np.arange(starCnt), pidx) | np.isin(np.arange(starCnt), qidx))]
                
                # 一致した星に対し、画像内の全星について位置関係を検証
                for j in range(len(otherStars)):
                    if currentInliers + len(otherStars) - j < bestMatchCount:
                        # このあと全て inlier でも bestMatchCount に届かないので早期終了 
                        break
                    
                    # 選択した p0 に近い2つを currentMatched の中から取り出す。
                    p0 = otherStars[j]
                    nearIndices = sorted(range(len(currentMatched)), key=lambda x: np.hypot(p0[0]-currentMatched[x]['x'], p0[1]-currentMatched[x]['y']))
                    near1 = currentMatched[nearIndices[0]]
                    near2 = currentMatched[nearIndices[1]]
                    p1 = (              near1['x' ], near1['y'  ], near1['brightness'], -1)
                    p2 = (              near2['x' ], near2['y'  ], near2['brightness'], -1)
                    c1 = (near1['hip'], near1['ra'], near1['dec'], near1['mag']           )
                    c2 = (near2['hip'], near2['ra'], near2['dec'], near2['mag']           )
                    
                    if 0 < (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]):
                        p1,p2 = p2,p1 # 時計回りに修正
                        c1,c2 = c2,c1 # 時計回りに修正
                    
                    dp01 = self._calcAngDistance(p0[0], p0[1], p1[0], p1[1], w, h, self.fovDeg)
                    dp12 = self._calcAngDistance(p1[0], p1[1], p2[0], p2[1], w, h, self.fovDeg)
                    dp20 = self._calcAngDistance(p2[0], p2[1], p0[0], p0[1], w, h, self.fovDeg)
                    dp = np.stack([dp01, dp12, dp20])
                    
                    # 検証に不適切な三角形をスキップする
                    if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ
                    
                    # カタログから検索
                    c = catalog.searchTriangle(dp01, dp12, dp20, self.catalog.matchLimit/100.0, self.catalog.magLimit, (None, c1[0], c2[0]))
                    catalogTotal += len(c)
                    c = c[np.all(c[:,0,0,np.newaxis] != nh.array([currentCatalogIds]), axis=1)] # 既知の点を除く
                    if 0 == len(c):
                        continue # 相似の三角形が見つからないのでスキップ
                    elif 1 == len(c):
                        # 1つしか候補がない
                        c0 = c[0,0]
                    else:
                        c0 = c[np.random.choice(len(c0)),0]
                    
                    currentInliers += 1
                    currentMatched.append(
                        {'hip'       : float(c0[0]),
                         'ra'        : float(c0[1]),
                         'dec'       : float(c0[2]),
                         'mag'       : float(c0[3]),
                         'x'         : float(p0[0]),
                         'y'         : float(p0[1]),
                         'brightness': float(p0[2]),
                        }
                    )
                    
                    #重複チェック
                    for j in range(len(currentMatched)):
                        for k in range(j+1,len(currentMatched)):
                            assert currentMatched[j]['hip'] != currentMatched[k]['hip'], "重複が発生しています。"
                    
                    currentCatalogIds.append(c0[0])
                
                # インライア数が閾値を超えた場合、モデル情報を更新
                if 3 <= currentInliers and bestMatchCount <= currentInliers:
                    currentMatched.sort(key=lambda x: x['mag']) # カタログ等級順にソート
                    # 誤差算出
                    # 画像側とカタログ側の全ペア間角距離マトリクス (N x N)を作成
                    p = nh.array([[star['x' ], star['y'  ]] for star in currentMatched])
                    c = nh.array([[star['ra'], star['dec']] for star in currentMatched])
                    dp = self._calcAngDistance(  p[:, np.newaxis, 0], p[:, np.newaxis, 1], p[np.newaxis, :, 0], p[np.newaxis, :, 1], w, h, self.fovDeg)
                    dc = catalog.angularDistance(c[:, np.newaxis, 0], c[:, np.newaxis, 1], c[np.newaxis, :, 0], c[np.newaxis, :, 1])
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
                        bestMatchedStars = currentMatched
                
                if(   5 <= bestMatchCount
                  and bestMatchError < self.catalog.matchLimit/100.0
                  and np.log(1-0.9999) / np.log(1-(bestMatchCount/starCnt)**4) < i # 初期一致数(最小インライア数):4
                  ):
                    # 99.99% の確率で外れ値を除外するのに十分な試行回数に到達
                    break
        i += 1
        
        if 3 <= bestMatchCount:
            import cv2
            src_pts = np.array([[star['x'], star['y']] for star in bestMatchedStars], dtype=np.float32)
            dst_pts = np.array([[star['ra'], star['dec']] for star in bestMatchedStars], dtype=np.float32)
            M, inliers_mask = cv2.estimateAffine2D(src_pts, dst_pts)
            if M is not None:
                img_center_px = np.array([w / 2.0, h / 2.0, 1.0])
                center_coords = M @ img_center_px
                est_ra, est_dec = center_coords[0], center_coords[1]
            else:
                est_ra, est_dec = np.mean(dst_pts[:, 0]), np.mean(dst_pts[:, 1])
            
            s = bestMatchedStars
            
            dist_cat = [
                Catalog.angularDistance(s[0]['ra'], s[0]['dec'], s[1]['ra'], s[1]['dec']),
                Catalog.angularDistance(s[1]['ra'], s[1]['dec'], s[2]['ra'], s[2]['dec']),
                Catalog.angularDistance(s[2]['ra'], s[2]['dec'], s[0]['ra'], s[0]['dec']),
            ]
            avg_dist_cat = np.mean(dist_cat)
            
            dist_img_px = [
                np.hypot(s[0]['x']-s[1]['x'], s[0]['y']-s[1]['y']),
                np.hypot(s[1]['x']-s[2]['x'], s[1]['y']-s[2]['y']),
                np.hypot(s[2]['x']-s[0]['x'], s[2]['y']-s[0]['y']),
            ]
            avg_dist_img_px = np.mean(dist_img_px)
            
            pixel_to_deg_est = avg_dist_cat / avg_dist_img_px
            diag_px = np.hypot(w, h)
            est_fov = diag_px * pixel_to_deg_est
            
            from utils.Debug import Debug
            n = int(np.log10(starCnt))+1
            debug  = f"match:{bestMatchCount:0{n}d}/{starCnt:0{n}d}"
            debug += f" catalog:{catalogTotal//i}"
            debug += f" estimated"
            debug += f" ra:{ est_ra :-07.3f}"
            debug += f" dec:{est_dec:+07.3f}"
            debug += f" fov:{est_fov:-07.3f}"
            debug += f" error:{bestMatchError:0.3f}"
            debug += f" ransac_iteration: {i}"
            Debug.log(type(self).__name__, f"{debug}")
            return bestMatchedStars
        else:
            from utils.Debug import Debug
            Debug.log(type(self).__name__, f"bestMatchCount: 0 match")
            return [], None
    
    def _calcAngDistance(self, x1: np.ndarray|float, y1: np.ndarray|float, x2: np.ndarray|float, y2: np.ndarray|float, w:int, h:int, fovDeg:float) -> np.ndarray|float:
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
                               lambda s0, s1: Catalog.angularDistance(s0[:, :, 1], s0[:, :, 2], s1[:, :, 1], s1[:, :, 2]),
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
    
    def _createTableOutput(self, matchedStars: list, parentHeaders: dict) -> FlowData:
        """星リストから Table 型 FlowData を作成"""
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        from base import FlowData
        
        # 等級でソート
        matchedStars.sort(key=lambda x: x['mag'])
        
        columns = ['ra', 'dec', 'mag', 'x', 'y', 'brightness']
        lines   = [f"HIP{int(star['hip'])}" for star in matchedStars]

        tableRows = []
        for star in matchedStars:
            row = [
                star['ra'],
                star['dec'],
                star['mag'],
                star['x'],
                star['y'],
                star['brightness'],
            ]
            tableRows.append(row)

        if 0 < len(tableRows):
            tableArray = nh.array(tableRows, dtype=nh.BDTYPE)
        else:
            tableArray = nh.zeros((0, len(columns)), dtype=nh.BDTYPE)

        # ヘッダー情報の構築
        headers = {
            'category': self.getOutputCategory(),
            'type'    : 'table',
            'mode'    : '2D',
            'columns' : columns,
            'lines'   : lines,
            'planes'  : ['star_extraction'],
        }

        # 元画像のメタデータを継承
        for key in ['source_file', 'datetime', 'exif', 'width', 'height']:
            if key in parentHeaders:
                headers[key] = parentHeaders[key]

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
        return StarExtractionSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config =(f"{self.minorType}_"
                 f"{self._outputCat}_"
                 f"{self.usePreviousOffset}_"
                 f"{self.alignmentPlane}_"
                 f"{self.saturationThreshold}_"
                 f"{self.star.threshold}_"
                 f"{self.star.useSaturationMask}_"
                 f"{self.star.minDiameter}_"
                 f"{self.star.maxDiameter}_"
                 f"{self.star.maxAspectRatio}_"
                 f"{self.star.grid.rows}_"
                 f"{self.star.grid.cols}_"
                 f"{self.star.grid.starsPerGrid}_"
                 f"{self.star.ransac.sampleRadius}_"
                 f"{self.star.ransac.iterations}_"
                 f"{self.star.ransac.seed}_"
                 f"{self.fovDeg}_"
                 f"{self.useHeader}_"
                 f"{self.catalog.matchLimit}_"
                 f"{self.catalog.magLimit}_"
                 f"{self.explore.ra}_"
                 f"{self.explore.dec}_"
                 f"{self.explore.fovDeg}_"
                 f"{self.useExplore}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class StarExtractionSettingsDialog(tk.Toplevel):
    """StarExtractionNode 用設定ダイアログ"""

    def __init__(self, parent, node:StarExtractionNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("450x700")
        
        self._createWidgets()
    
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self, padx=10, pady=10)
        mainFrame.pack(fill=tk.BOTH, expand=True)

        # 前回方向考慮
        prevFrame = tk.Frame(mainFrame)
        prevFrame.pack(fill=tk.X, pady=2)
        self.usePrevOffsetVar = tk.BooleanVar(value=self.node.usePreviousOffset)
        tk.Checkbutton(prevFrame, text="前の画像の方向を考慮する", variable=self.usePrevOffsetVar).pack(side=tk.LEFT)

        # 位置合わせ用プレーン
        planeFrame = tk.Frame(mainFrame)
        planeFrame.pack(fill=tk.X, pady=2)
        tk.Label(planeFrame, text="位置合わせプレーン:").pack(side=tk.LEFT)
        self.planeEntry = tk.Entry(planeFrame, width=5)
        self.planeEntry.insert(0, str(self.node.alignmentPlane))
        self.planeEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(planeFrame, text="(0:R, 1:G, 2:B ... 検出用)").pack(side=tk.LEFT)

        # 星点検出設定セクション
        tk.Label(mainFrame, text="■ 星点検出パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(8, 2))

        # 星検出閾値
        thrFrame = tk.Frame(mainFrame)
        thrFrame.pack(fill=tk.X, pady=2)
        tk.Label(thrFrame, text="  星検出閾値:").pack(side=tk.LEFT)
        self.thresholdEntry = tk.Entry(thrFrame, width=5)
        self.thresholdEntry.insert(0, str(self.node.star.threshold))
        self.thresholdEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(thrFrame, text="% (上位%の明るい星を選択)").pack(side=tk.LEFT)

        # 飽和マスク
        maskFrame = tk.Frame(mainFrame)
        maskFrame.pack(fill=tk.X, pady=2)
        self.useSatMaskVar = tk.BooleanVar(value=self.node.star.useSaturationMask)
        tk.Checkbutton(maskFrame, text="飽和マスクを使用する", variable=self.useSatMaskVar).pack(side=tk.LEFT)

        # 星直径範囲
        diaFrame = tk.Frame(mainFrame)
        diaFrame.pack(fill=tk.X, pady=2)
        tk.Label(diaFrame, text="  星直径範囲:").pack(side=tk.LEFT)
        self.minDiaEntry = tk.Entry(diaFrame, width=5)
        self.minDiaEntry.insert(0, str(self.node.star.minDiameter))
        self.minDiaEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(diaFrame, text="~").pack(side=tk.LEFT)
        self.maxDiaEntry = tk.Entry(diaFrame, width=5)
        self.maxDiaEntry.insert(0, str(self.node.star.maxDiameter))
        self.maxDiaEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(diaFrame, text="px (検出対象直径)").pack(side=tk.LEFT)

        # 最大アスペクト比
        arFrame = tk.Frame(mainFrame)
        arFrame.pack(fill=tk.X, pady=2)
        tk.Label(arFrame, text="  最大アスペクト比:").pack(side=tk.LEFT)
        self.aspectRatioEntry = tk.Entry(arFrame, width=5)
        self.aspectRatioEntry.insert(0, str(self.node.star.maxAspectRatio))
        self.aspectRatioEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(arFrame, text="(細長いノイズを除外)").pack(side=tk.LEFT)

        # グリッド
        gridFrame = tk.Frame(mainFrame)
        gridFrame.pack(fill=tk.X, pady=2)
        tk.Label(gridFrame, text="  グリッド分割:").pack(side=tk.LEFT)
        self.gridRowsEntry = tk.Entry(gridFrame, width=4)
        self.gridRowsEntry.insert(0, str(self.node.star.grid.rows))
        self.gridRowsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="x").pack(side=tk.LEFT)
        self.gridColsEntry = tk.Entry(gridFrame, width=4)
        self.gridColsEntry.insert(0, str(self.node.star.grid.cols))
        self.gridColsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text=" 各マス星数:").pack(side=tk.LEFT, padx=(5, 0))
        self.starsPerGridEntry = tk.Entry(gridFrame, width=4)
        self.starsPerGridEntry.insert(0, str(self.node.star.grid.starsPerGrid))
        self.starsPerGridEntry.pack(side=tk.LEFT, padx=2)

        # 星サンプル半径
        starDistFrame = tk.Frame(mainFrame)
        starDistFrame.pack(fill=tk.X, pady=2)
        tk.Label(starDistFrame, text="    星サンプル半径:").pack(side=tk.LEFT)
        self.starDistEntry = tk.Entry(starDistFrame, width=5)
        self.starDistEntry.insert(0, str(self.node.star.ransac.sampleRadius))
        self.starDistEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starDistFrame, text="px (統計処理用サンプル収集範囲)").pack(side=tk.LEFT)
        
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
        
        # 画像パラメータセクション
        tk.Label(mainFrame, text="■ 画像パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 画角
        fovDegFrame = tk.Frame(mainFrame)
        fovDegFrame.pack(fill=tk.X, pady=2)
        tk.Label(fovDegFrame, text="  画角:").pack(side=tk.LEFT)
        self.fovDegEntry = tk.Entry(fovDegFrame, width=6)
        self.fovDegEntry.insert(0, str(self.node.fovDeg))
        self.fovDegEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(fovDegFrame, text="deg").pack(side=tk.LEFT)

        # ヘッダー情報から推定
        useHdrFrame = tk.Frame(mainFrame)
        useHdrFrame.pack(fill=tk.X, pady=2)
        self.useHeaderVar = tk.BooleanVar(value=self.node.useHeader)
        tk.Checkbutton(useHdrFrame, text="ヘッダー情報から画角を推定", variable=self.useHeaderVar).pack(side=tk.LEFT)
        
        # カタログ照合セクション
        tk.Label(mainFrame, text="■ カタログ照合パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))

        # 許容半径
        radFrame = tk.Frame(mainFrame)
        radFrame.pack(fill=tk.X, pady=2)
        tk.Label(radFrame, text="  照合許容半径:").pack(side=tk.LEFT)
        self.catalogMatchLimitEntry = tk.Entry(radFrame, width=6)
        self.catalogMatchLimitEntry.insert(0, str(self.node.catalog.matchLimit))
        self.catalogMatchLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(radFrame, text="% (カタログ対応付けのズレ許容比)").pack(side=tk.LEFT)

        # 等級上限
        magFrame = tk.Frame(mainFrame)
        magFrame.pack(fill=tk.X, pady=2)
        tk.Label(magFrame, text="  カタログ等級上限:").pack(side=tk.LEFT)
        self.magLimitEntry = tk.Entry(magFrame, width=6)
        self.magLimitEntry.insert(0, str(self.node.catalog.magLimit))
        self.magLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(magFrame, text="mag (これより暗い星を除外)").pack(side=tk.LEFT)

        # 探索座標
        coordFrame = tk.Frame(mainFrame)
        coordFrame.pack(fill=tk.X, pady=2)
        tk.Label(coordFrame, text=" 探索赤経(RA):").pack(side=tk.LEFT)
        self.raEntry = tk.Entry(coordFrame, width=8)
        self.raEntry.insert(0, str(self.node.explore.ra))
        self.raEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(coordFrame, text=" 赤緯(DEC):").pack(side=tk.LEFT)
        self.decEntry = tk.Entry(coordFrame, width=8)
        self.decEntry.insert(0, str(self.node.explore.dec))
        self.decEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(coordFrame, text="deg (初期探索値)").pack(side=tk.LEFT)
        
        # 探索画角
        fovFrame = tk.Frame(mainFrame)
        fovFrame.pack(fill=tk.X, pady=2)
        tk.Label(fovFrame, text="  探索画角:").pack(side=tk.LEFT)
        self.fovEntry = tk.Entry(fovFrame, width=6)
        self.fovEntry.insert(0, str(self.node.explore.fovDeg))
        self.fovEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(fovFrame, text="deg (初期探索値)").pack(side=tk.LEFT)

        # 探索範囲を使用
        useExploreFrame = tk.Frame(mainFrame)
        useExploreFrame.pack(fill=tk.X, pady=2)
        self.useExploreVar = tk.BooleanVar(value=self.node.useExplore)
        tk.Checkbutton(useExploreFrame, text="探索座標を使用する", variable=self.useExploreVar).pack(side=tk.LEFT)
        tk.Label(useExploreFrame, text="初期探索値を使用する").pack(side=tk.LEFT)
        
        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.onClose)

    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            self.node.usePreviousOffset        = self.usePrevOffsetVar.get()
            self.node.alignmentPlane           = max(0, int(self.planeEntry.get()))
            self.node.star.threshold           = max(1, min(99, int(self.thresholdEntry.get())))
            self.node.star.useSaturationMask   = self.useSatMaskVar.get()
            self.node.star.minDiameter         = max(1, int(self.minDiaEntry.get()))
            self.node.star.maxDiameter         = max(self.node.star.minDiameter, int(self.maxDiaEntry.get()))
            self.node.star.maxAspectRatio      = max(1.0, float(self.aspectRatioEntry.get()))
            self.node.star.grid.rows           = max(1, int(self.gridRowsEntry.get()))
            self.node.star.grid.cols           = max(1, int(self.gridColsEntry.get()))
            self.node.star.grid.starsPerGrid   = max(1, int(self.starsPerGridEntry.get()))
            self.node.star.ransac.sampleRadius = max(10, int(self.starDistEntry.get()))
            self.node.star.ransac.iterations   = max(10, min(100000, int(self.ransacEntry.get())))
            self.node.star.ransac.seed         = max(1, int(self.ransacSeedEntry.get()))
            self.node.fovDeg                   = max(0.01, float(self.fovDegEntry.get()))
            self.node.useHeader                = self.useHeaderVar.get()
            self.node.catalog.matchLimit       = max(0.001, min(99.0, float(self.catalogMatchLimitEntry.get())))
            self.node.catalog.magLimit         = max(1, min(20, float(self.magLimitEntry.get())))
            self.node.explore.ra               = max(0.0, min(360, float(self.raEntry.get())))
            self.node.explore.dec              = max(-90.0, min(90.0, float(self.decEntry.get())))
            self.node.explore.fovDeg           = max(0.0, float(self.fovEntry.get()))
            self.node.useExplore               = self.useExploreVar.get()
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
