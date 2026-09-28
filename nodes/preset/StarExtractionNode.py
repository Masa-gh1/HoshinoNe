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

from config import CATALOG_PATH
from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

if TYPE_CHECKING:
    import numpy as np
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

        # カタログ照合パラメータ
        self.catalogPath       = CATALOG_PATH                 # カタログファイルパス
        self.catalogMatchLimit = 5                            # カタログ照合許容比 [%]
        self.catalogMagLimit   = 8.0                          # カタログ等級上限 [mag]
        self.estimatedRa       = 255.996                      # 推定中心赤経 [deg]
        self.estimatedDec      = -11.381                      # 推定中心赤緯 [deg]
        self.estimatedFovDeg   = 3.5                          # 推定画角 [deg]
        self.useEstimated      = False                        # 推定中心座標を使用するか

        # 内部状態
        self._previousTransform = None                        # 前画像で推定された変換情報

        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nThr:{self.star.threshold}% Match:{self.catalogMatchLimit} %"
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
        nodeData["catalogMatchLimit"]   = self.catalogMatchLimit
        nodeData["catalogMagLimit"]     = self.catalogMagLimit
        nodeData["estimatedRa"]         = self.estimatedRa
        nodeData["estimatedDec"]        = self.estimatedDec
        nodeData["estimatedFovDeg"]     = self.estimatedFovDeg
        nodeData["useApproxCoords"]     = self.useEstimated

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
        if "catalogMatchLimit" in nodeData:
            self.catalogMatchLimit = nodeData["catalogMatchLimit"]
        if "catalogMagLimit" in nodeData:
            self.catalogMagLimit = nodeData["catalogMagLimit"]
        if "estimatedRa" in nodeData:
            self.estimatedRa = nodeData["estimatedRa"]
        if "estimatedDec" in nodeData:
            self.estimatedDec = nodeData["estimatedDec"]
        if "estimatedFovDeg" in nodeData:
            self.estimatedFovDeg = nodeData["estimatedFovDeg"]
        if "useApproxCoords" in nodeData:
            self.useEstimated = nodeData["useApproxCoords"]

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

        # カタログデータの準備
        catalogData = self._getCatalogData()

        # 各画像から星を抽出し、カタログ照合
        outputFlowDatas = []
        totalImages     = len(inputStream)
        
        # 前回の変換情報をリセット
        self._previousTransform = None
        
        for i, flowData in enumerate(inputStream):
            self.reportProgress(context, f"画像 {i + 1}/{totalImages} 処理中", i, totalImages)
            
            # 画像プレーンを numpy 配列として取得
            planeIndex = min(self.alignmentPlane, flowData.getPlaneCount() - 1)
            imageArray = self._flowDataToImage(flowData, planeIndex=planeIndex, normalizeForDetection=True)

            ###################
            # テストパラメタ
            #self.star.minDiameter = 6
            #self.star.maxDiameter = 12
            ###################
            
            # 星点を検出
            detectedStars = self._detectStars(imageArray)

            # カタログ照合
            matchedStars, currentTransform = self._matchCatalog(
                detectedStars,
                catalogData,
                imageArray.shape,
                flowData.headers,
                self._previousTransform if self.usePreviousOffset else None
            )

            if self.usePreviousOffset and None != currentTransform:
                self._previousTransform = currentTransform

            # 出力 Table FlowData を作成
            outTable = self._createTableOutput(matchedStars, flowData.headers)
            outputFlowDatas.append(outTable)

        self.flowDatas = outputFlowDatas
        self.reportProgress(context, "完了")

    def _getCatalogData(self) -> np.ndarray:
        """カタログデータを取得（入力ストリームまたはファイルから）"""
        from utils.catalog_helper import CatalogHelper
        if self._catalogStream and self._catalogStream[0]:
            tableFlowData = self._catalogStream[0]
            # Table FlowData から配列化
            blocks = list(tableFlowData.iterateBlocks())
            if 0 < len(blocks) and blocks[0].data is not None:
                return blocks[0].data

        # ファイルから読み込み
        return CatalogHelper.loadCatalog(self.catalogPath)

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
            # 重心を計算
            M = cv2.moments(star)
            if M['m00'] <= 0:
                positions.append(None)
                brightnesses.append(None)
            else:
                cx = float(M['m10'] / M['m00'])
                cy = float(M['m01'] / M['m00'])
                positions.append((cx, cy))
                
                # 星の明度を取得
                # 輪郭にからマスクを作成して、星像を取得
                mask = np.zeros(subtracted.shape, dtype=np.uint8)
                cv2.drawContours(mask, [star], -1, 255, thickness=cv2.FILLED)
                
                # 元の画像をマスク
                starAreaValues = subtracted[mask > 0]
                
                # 星は無限遠の点なので分散している明るさを合計する
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

    def _createSaturationMask(self, image: np.ndarray) -> np.ndarray:
        """飽和領域のマスクを作成"""
        import numpy as np
        import cv2
        maxVal = np.max(image) if 0 < image.size else 255
        saturated = image > (maxVal * float(self.saturationThreshold) / 100.0)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
        mask = cv2.dilate(saturated.astype(np.uint8), kernel, iterations=2)
        return mask == 0

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

        # 各グリッドから最大n個の明るい星を選択
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
    
    def _matchCatalog(self, detectedStars: list, catalogData: np.ndarray, imageShape: tuple, headers: dict, prevTransform: dict | None = None):
        """
        【真の純粋実装：座標変換を数学的に完全に排除】
        
        投影（Mapping）を一切行わず、幾何学的な「相似比」の比較のみで
        全星の同定（インライア判定）を行う。
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from utils.catalog_helper import CatalogHelper
        
        if len(detectedStars) < 3 or len(catalogData) < 3:
            return [], None
        
        h, w = imageShape
        np.random.seed(self.star.ransac.seed)
        
        # 画像側のサンプリング
        selectedStars, _ = self._selectDistributedStars(detectedStars, imageShape)
        if len(selectedStars) < 3:
            return [], None

        # 探索範囲の決定
        if prevTransform and "crval1" in prevTransform and "crval2" in prevTransform and "fovDeg" in prevTransform:
            crval1, crval2 = prevTransform["crval1"], prevTransform["crval2"]
            searchRadius = prevTransform["fovDeg"] / 2.0
        elif self.useEstimated:
            crval1, crval2 = self.estimatedRa, self.estimatedDec
            searchRadius = self.estimatedFovDeg / 2.0
        else:
            crval1, crval2 = 0.0, 0.0
            searchRadius = 180
        
        # 探索範囲はユーザーの推定画角をガイドとするが、
        # 実際の同定（判定）は、この範囲内で見つかった星の中から「形と相対位置」が一致するかで行う。
        catalog = CatalogHelper.queryStars(catalogData, crval1, crval2, searchRadius, magLimit=self.catalogMagLimit)
        if len(catalog) < 3:
            return [], None
        
        # 一括処理用に列ごとに分割
        catalogRa  = catalog[:, 1]
        catalogDec = catalog[:, 2]
        catalogMag = catalog[:, 3]
        
        degPerPixel = self.estimatedFovDeg / np.hypot(w, h)
        bestMatchCount = 0
        bestMatchError = np.inf
        bestMatchedStars = []
        
        starNum = len(selectedStars)
        from utils.Debug import Debug
        Debug.log(type(self).__name__, f"stars:{starNum} catalog:{len(catalog)}")

        for _ in range(self.star.ransac.iterations): # RANSAC試行回数
            # 画像側で3点を選択し、形状比率を計算
            indices = np.random.choice(starNum, 3, replace=False)
            p0,p1,p2 = [selectedStars[i] for i in indices]
            if 0 < (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]):
                p1,p2 = p2,p1 # 時計回りに修正
            dp01 = np.hypot(p0[0]-p1[0], p0[1]-p1[1]) * degPerPixel # ⊿p0,p1
            dp12 = np.hypot(p1[0]-p2[0], p1[1]-p2[1]) * degPerPixel # ⊿p1,p2
            dp20 = np.hypot(p2[0]-p0[0], p2[1]-p0[1]) * degPerPixel # ⊿p2,p0
            dp = nh.array([dp01,dp12,dp20])
            if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ
            
            # 画像側での距離比
            pBaseRatio = nh.array([dp01/dp12,dp12/dp20,dp20/dp01])
            
            # カタログ側で3点を選択し、形状比率を計算
            indices = np.random.choice(len(catalog), 3, replace=False)
            c0,c1,c2 = [catalog[i] for i in indices]
            if 0 < (c1[0] - c0[0]) * (c2[1] - c0[1]) - (c1[1] - c0[1]) * (c2[0] - c0[0]):
                c1,c2 = c2,c1 # 時計回りに修正
            dc01 = CatalogHelper.angularDistance(c0[1], c0[2], c1[1], c1[2]) # ⊿c0,c1
            dc12 = CatalogHelper.angularDistance(c1[1], c1[2], c2[1], c2[2]) # ⊿c1,c2
            dc20 = CatalogHelper.angularDistance(c2[1], c2[2], c0[1], c0[2]) # ⊿c2,c0
            dc = nh.array([dc01,dc12,dc20])
            if np.any(dc < 1e-7) or np.min(dc) / np.max(dc) < 0.2: continue # 極端に短い辺が在るのでスキップ
            
            # カタログ側での距離比
            cBaseRatio = nh.array([dc01/dc12, dc12/dc20, dc20/dc01])

            if np.allclose(cBaseRatio, pBaseRatio, rtol=self.catalogMatchLimit/100.0):
                # 画像3点とカタログ3点が相似だった
                currentInliers = 3
                # ratio_cat_base と ratio_img_base のズレの総和の記録
                currentMatched = [
                    { 'hip'        : float(c[0]),
                      'ra'         : float(c[1]),
                      'dec'        : float(c[2]),
                      'mag'        : float(c[3]),
                      'x'          : float(p[0]),
                      'y'          : float(p[1]),
                      'brightness' : float(p[2]),
                    } for c,p in ((c0,p0),(c1,p1),(c2,p2))
                ]
                
                # 確定した星を除く index を作成
                candidateCatalogIndices = [i for i in range(len(catalog)) if i not in indices]
                
                # 画像内の全星について、確定した星との三角形(P0, P1, P2)に対する距離比を検証
                for i in range(len(selectedStars)):
                    # currentMatched の中から p0 に近い2つ取り出す。
                    p0 = selectedStars[i]
                    nearIndices = sorted(range(len(currentMatched)), key=lambda x: np.hypot(p0[0]-currentMatched[x]['x'], p0[1]-currentMatched[x]['y']))
                    p1 = currentMatched[nearIndices[0]]
                    p2 = currentMatched[nearIndices[1]]
                    p1 = (p1['x'], p1['y'], p1['brightness'])
                    p2 = (p2['x'], p2['y'], p2['brightness'])
                    
                    c1 = currentMatched[nearIndices[0]]
                    c2 = currentMatched[nearIndices[1]]
                    c1 = (c1['hip'], c1['ra'], c1['dec'], c1['mag'])
                    c2 = (c2['hip'], c2['ra'], c2['dec'], c2['mag'])
                    
                    if 0 < (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]):
                        p1,p2 = p2,p1 # 時計回りに修正
                        c1,c2 = c2,c1 # 時計回りに修正
                    
                    # 画像側での距離
                    dp01 = np.hypot(p0[0]-p1[0], p0[1]-p1[1]) * degPerPixel # ⊿p0,p1
                    dp12 = np.hypot(p1[0]-p2[0], p1[1]-p2[1]) * degPerPixel # ⊿p1,p2
                    dp20 = np.hypot(p2[0]-p0[0], p2[1]-p0[1]) * degPerPixel # ⊿p2,p0
                    if dp01 < 1e-7 or dp12 < 1e-7 or dp20 < 1e-7: continue
                    
                    sortD = np.sort([dp01,dp12,dp20])
                    if sortD[0] / sortD[2] < 0.2:
                        # 極端に短い辺が在るのでスキップ
                        continue
                    
                    # 画像側での距離比
                    pBaseRatio = nh.array([dp01/dp12,dp12/dp20,dp20/dp01])
                    
                    # カタログ側での距離
                    dcn1 = CatalogHelper.angularDistance(c1[1], c1[2], catalogRa, catalogDec)
                    dc12 = CatalogHelper.angularDistance(c1[1], c1[2], c2[1],     c2[2])
                    dc2n = CatalogHelper.angularDistance(c2[1], c2[2], catalogRa, catalogDec)

                    # カタログ側での距離比
                    cRatio = np.stack([dcn1/dc12, dc12/dc2n, dc2n/dcn1], axis=1)
                    
                    isClose = np.isclose(cRatio, pBaseRatio, rtol=self.catalogMatchLimit/100.0)
                    isCloseAll = np.all(isClose, axis=1)
                    matchIndices = np.where(isCloseAll)[0]
                    matchIndices = [i for i in matchIndices if i not in indices]
                    
                    if 0 < len(matchIndices):
                        if 1== len(matchIndices):
                            # 1つしか候補がない
                            matchIndex = matchIndices[0]
                        else:
                            # 辺比を計算
                            dp01 = np.hypot(p0[0]-p1[0], p0[1]-p1[1]) * degPerPixel # ⊿p0,p1
                            dp12 = np.hypot(p1[0]-p2[0], p1[1]-p2[1]) * degPerPixel # ⊿p1,p2
                            dp20 = np.hypot(p2[0]-p0[0], p2[1]-p0[1]) * degPerPixel # ⊿p2,p0
                            dp01r = dp01 / dp12
                            dp12r = dp12 / dp20
                            dp20r = dp20 / dp01

                            # 等級差(輝度比)を比較 ポグソンの式:m1 - m2 = -2.5 log10 (l1 -l2)
                            # 画像側3つの星の等級差(輝度比)を計算
                            p01Mag = -2.5 * np.log10(p0[2] / p1[2])
                            p12Mag = -2.5 * np.log10(p1[2] / p2[2])
                            p20Mag = -2.5 * np.log10(p2[2] / p0[2])
                            
                            # カタログ側マッチ配列
                            cn = catalog[matchIndices]
                            
                            # 辺比を計算
                            dcn1 =                 CatalogHelper.angularDistance(cn[:,1], cn[:,2], c1[  1], c1[  2])
                            dc12 = np.broadcast_to(CatalogHelper.angularDistance(c1[  1], c1[  2], c2[  1], c2[  2]), dcn1.shape)
                            dc2n =                 CatalogHelper.angularDistance(c2[  1], c2[  2], cn[:,1], cn[:,2])
                            dcn1r = dcn1 / dc12
                            dc12r = dc12 / dc12
                            dc2nr = dc2n / dc12

                            # カタログ側3つの星の等級差を計算
                            cn1Mag =                 cn[:,3] - c1[  3]
                            c12Mag = np.broadcast_to(c1[  3] - c2[  3], cn1Mag.shape)
                            c2nMag =                 c2[  3] - cn[:,3]

                            # 画像側に近い明るさ比のカタログを採用する
                            # 3つの差の最も小さいものを採用
                            pSet = np.array([[dp01r], [dp12r], [dp20r],  [p01Mag], [p12Mag], [p20Mag]])
                            cSet = np.array([ dcn1r ,  dc12r ,  dc2nr ,   cn1Mag ,  c12Mag ,  c2nMag  ])
                            
                            matchError = np.sum((cSet - pSet)**2, axis=0)
                            
                            errorIndex = np.argmin(matchError)
                            matchIndex = matchIndices[errorIndex]
                        
                        currentInliers += 1
                        currentMatched.append({
                            'hip'        : float(catalog[matchIndex, 0]),
                            'ra'         : float(catalog[matchIndex, 1]),
                            'dec'        : float(catalog[matchIndex, 2]),
                            'mag'        : float(catalog[matchIndex, 3]),
                            'x'          : float(selectedStars[i][0]),
                            'y'          : float(selectedStars[i][1]),
                            'brightness' : float(selectedStars[i][2]),
                        })

                # インライア数が閾値を超えた場合、モデル情報を更新
                if 3 <= currentInliers and bestMatchCount <= currentInliers:
                    # 等級を比較する
                    currentMagError = 0.0
                    for i in range(len(currentMatched)):
                        j = (i + 1) % len(currentMatched)
                        k = (i + 2) % len(currentMatched)
                        mat0 = currentMatched[i]
                        mat1 = currentMatched[j]
                        mat2 = currentMatched[k]
                        dc01 = CatalogHelper.angularDistance(mat0['ra'], mat0['dec'], mat1['ra'], mat1['dec'])
                        dc12 = CatalogHelper.angularDistance(mat1['ra'], mat1['dec'], mat2['ra'], mat2['dec'])
                        cd   = dc01 / dc12
                        cMag = mat0['mag'] - mat1['mag']
                        dp01 = np.hypot(mat0['x'] - mat1['x'], mat0['y'] - mat1['y'])
                        dp12 = np.hypot(mat1['x'] - mat2['x'], mat1['y'] - mat2['y'])
                        pd   = dp01 / dp12
                        p0br = max(mat0['brightness'], 1e-6)
                        p1br = max(mat1['brightness'], 1e-6)
                        pMag = -2.5 * np.log10(p0br / p1br)
                        currentMagError += (cd - pd)**2 + (cMag - pMag)**2 # 等級差(輝度比)を比較 ポグソンの式:m1 - m2 = -2.5 log10 (l1 -l2)
                    currentMagError /= len(currentMatched)
                    # インライア数が同じでも、誤差が小さい方が優先
                    if bestMatchCount < currentInliers or currentMagError < bestMatchError:
                        bestMatchCount = currentInliers
                        bestMatchError = currentMagError
                        bestMatchedStars = currentMatched

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
                CatalogHelper.angularDistance(s[0]['ra'], s[0]['dec'], s[1]['ra'], s[1]['dec']),
                CatalogHelper.angularDistance(s[1]['ra'], s[1]['dec'], s[2]['ra'], s[2]['dec']),
                CatalogHelper.angularDistance(s[2]['ra'], s[2]['dec'], s[0]['ra'], s[0]['dec']),
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
            
            bestModelInfo = {
                'crval1': est_ra, 
                'crval2': est_dec, 
                'fovDeg': est_fov,
            }
            
            from utils.Debug import Debug
            raMin = min([star['ra'] for star in bestMatchedStars])
            raMax = max([star['ra'] for star in bestMatchedStars])
            decMin = min([star['dec'] for star in bestMatchedStars])
            decMax = max([star['dec'] for star in bestMatchedStars])
            debug  = f"bestMatchCount:{bestMatchCount}"
            debug += f" ra:{raMin:0.3f}_{raMax:0.3f}"
            debug += f" dec:{decMin:0.3f}_{decMax:0.3f}"
            debug += f" estimated"
            debug += f" ra:{est_ra:0.3f}"
            debug += f" dec:{est_dec:0.3f}"
            debug += f" fov:{est_fov:0.3f}"
            debug += f" mag erroe:{bestMatchError:0.3f}"
            Debug.log(type(self).__name__, f"{debug}")
            return bestMatchedStars, bestModelInfo
        else:
            from utils.Debug import Debug
            Debug.log(type(self).__name__, f"bestMatchCount: 0 match")
            return [], None
        
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
                 f"{self.catalogPath}_"
                 f"{self.catalogMatchLimit}_"
                 f"{self.catalogMagLimit}_"
                 f"{self.estimatedRa}_"
                 f"{self.estimatedDec}_"
                 f"{self.estimatedFovDeg}_"
                 f"{self.useEstimated}_"
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
        
        # カタログ照合セクション
        tk.Label(mainFrame, text="■ カタログ照合パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))

        # 許容半径
        radFrame = tk.Frame(mainFrame)
        radFrame.pack(fill=tk.X, pady=2)
        tk.Label(radFrame, text="  照合許容半径:").pack(side=tk.LEFT)
        self.catalogMatchLimitEntry = tk.Entry(radFrame, width=6)
        self.catalogMatchLimitEntry.insert(0, str(self.node.catalogMatchLimit))
        self.catalogMatchLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(radFrame, text="% (カタログ対応付けのズレ許容比)").pack(side=tk.LEFT)

        # 等級上限
        magFrame = tk.Frame(mainFrame)
        magFrame.pack(fill=tk.X, pady=2)
        tk.Label(magFrame, text="  カタログ等級上限:").pack(side=tk.LEFT)
        self.magLimitEntry = tk.Entry(magFrame, width=6)
        self.magLimitEntry.insert(0, str(self.node.catalogMagLimit))
        self.magLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(magFrame, text="mag (これより暗い星を除外)").pack(side=tk.LEFT)

        # 推定座標
        coordFrame = tk.Frame(mainFrame)
        coordFrame.pack(fill=tk.X, pady=2)
        tk.Label(coordFrame, text=" 推定赤経(RA):").pack(side=tk.LEFT)
        self.raEntry = tk.Entry(coordFrame, width=8)
        self.raEntry.insert(0, str(self.node.estimatedRa))
        self.raEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(coordFrame, text=" 赤緯(DEC):").pack(side=tk.LEFT)
        self.decEntry = tk.Entry(coordFrame, width=8)
        self.decEntry.insert(0, str(self.node.estimatedDec))
        self.decEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(coordFrame, text="deg (初期推定値)").pack(side=tk.LEFT)
        
        # 推定画角
        fovFrame = tk.Frame(mainFrame)
        fovFrame.pack(fill=tk.X, pady=2)
        tk.Label(fovFrame, text="  推定画角:").pack(side=tk.LEFT)
        self.fovEntry = tk.Entry(fovFrame, width=6)
        self.fovEntry.insert(0, str(self.node.estimatedFovDeg))
        self.fovEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(fovFrame, text="deg (初期推定値)").pack(side=tk.LEFT)

        # 推定の使用
        useEstimatedFrame = tk.Frame(mainFrame)
        useEstimatedFrame.pack(fill=tk.X, pady=2)
        self.useEstimatedVar = tk.BooleanVar(value=self.node.useEstimated)
        tk.Checkbutton(useEstimatedFrame, text="推定座標を使用する", variable=self.useEstimatedVar).pack(side=tk.LEFT)
        tk.Label(useEstimatedFrame, text="初期推定値を使用する").pack(side=tk.LEFT)
        
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
            self.node.catalogMatchLimit        = max(0.001, min(99.0, float(self.catalogMatchLimitEntry.get())))
            self.node.catalogMagLimit          = float(self.magLimitEntry.get())
            self.node.estimatedRa              = float(self.raEntry.get())
            self.node.estimatedDec             = float(self.decEntry.get())
            self.node.estimatedFovDeg          = max(0.01, float(self.fovEntry.get()))
            self.node.useEstimated             = self.useEstimatedVar.get()
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
