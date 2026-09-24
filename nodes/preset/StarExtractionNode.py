'''
StarExtractionNode - 星抽出ノード

画像から天体（星点）を検出し、星カタログ（HIP2等）と照合して確定した星のリストを生成するノード

Copyright (c) 2026 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from types import SimpleNamespace

import hashlib

import tkinter as tk
from tkinter import messagebox
import numpy as np

from config import CATALOG_PATH
from base.FlowNode_CONST import *
from base import FlowNode
from base import FlowData
from base import DataBlock
from nodes import ConfigurableNode
from utils import numpy_helpers as nh
from utils.catalog_helper import CatalogHelper

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
        self.saturationThreshold = 95                         # 飽和閾値 (%)
        
        # 星点検出パラメータ
        self.star                     = SimpleNamespace()
        self.star.threshold           = 95                    # 星検出閾値 (%)
        self.star.useSaturationMask   = False                 # 飽和マスクを使用する
        self.star.minDiameter         = 2                     # 星最小直径 (px)
        self.star.maxDiameter         = 16                    # 星最大直径 (px)
        self.star.maxAspectRatio      = 2.0                   # 星の最大アスペクト比
        self.star.grid                = SimpleNamespace()
        self.star.grid.rows           = 3                     # グリッド行数
        self.star.grid.cols           = 3                     # グリッド列数
        self.star.grid.starsPerGrid   = 8                     # グリッド当たりの選択星数
        self.star.ransac              = SimpleNamespace()
        self.star.ransac.sampleRadius = 100                   # RANSAC対応点サンプル半径 (px)
        self.star.ransac.iterations   = 100                   # RANSAC試行回数
        self.star.ransac.seed         = 2725                  # RANSAC乱数シード

        # カタログ照合パラメータ
        self.catalogPath       = CATALOG_PATH                 # カタログファイルパス
        self.matchRadius       = 0.5                          # カタログ照合許容半径 (deg)
        self.catalogMagLimit   = 8.0                          # カタログ等級上限 (mag)
        self.estimatedFovDeg   = 3.5                          # 推定画角 (deg)
        self.approxRa          = 255.0                        # 推定中心赤経 (deg)
        self.approxDec         = -12.0                        # 推定中心赤緯 (deg)
        self.useApproxCoords   = False                        # 推定中心座標を使用するか

        # 内部状態
        self._previousTransform = None                        # 前画像で推定された変換情報

        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nThr:{self.star.threshold}% Rad:{self.matchRadius} deg"
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
        nodeData["matchRadius"]         = self.matchRadius
        nodeData["catalogMagLimit"]     = self.catalogMagLimit
        nodeData["estimatedFovDeg"]     = self.estimatedFovDeg
        nodeData["approxRa"]            = self.approxRa
        nodeData["approxDec"]           = self.approxDec
        nodeData["useApproxCoords"]     = self.useApproxCoords

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
        if "matchRadius" in nodeData:
            self.matchRadius = nodeData["matchRadius"]
        if "catalogMagLimit" in nodeData:
            self.catalogMagLimit = nodeData["catalogMagLimit"]
        if "estimatedFovDeg" in nodeData:
            self.estimatedFovDeg = nodeData["estimatedFovDeg"]
        if "approxRa" in nodeData:
            self.approxRa = nodeData["approxRa"]
        if "approxDec" in nodeData:
            self.approxDec = nodeData["approxDec"]
        if "useApproxCoords" in nodeData:
            self.useApproxCoords = nodeData["useApproxCoords"]

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
        if self._catalogStream and self._catalogStream[0]:
            tableFlowData = self._catalogStream[0]
            # Table FlowData から配列化
            blocks = list(tableFlowData.iterateBlocks())
            if 0 < len(blocks) and blocks[0].data is not None:
                return blocks[0].data

        # ファイルから読み込み
        return CatalogHelper.loadCatalog(self.catalogPath)

    def _detectStars(self, image: np.ndarray):
        """
        画像から星点を検出する (ShiftDetectionNode のアルゴリズムを継承)
        
        Args:
            image: 検出用グレースケール画像 (uint8)
            
        Returns:
            list[tuple[float, float, float, float]]: (cx, cy, brightness, aspectRatio) のリスト
        """
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
            positive = maskedSubtracted[maskedSubtracted > 0]
            if 0 < len(positive):
                maxPositive = np.max(positive)
                threshold   = np.nanpercentile(positive, self.star.threshold)
                if threshold >= maxPositive and 1 < maxPositive:
                    threshold = maxPositive - 1
                _, binary   = cv2.threshold(maskedSubtracted, threshold, 255, cv2.THRESH_BINARY)
            else:
                binary = np.zeros_like(maskedSubtracted)
        else:
            # 閾値処理
            positive = subtracted[subtracted > 0]
            if 0 < len(positive):
                maxPositive = np.max(positive)
                threshold   = np.nanpercentile(positive, self.star.threshold)
                if threshold >= maxPositive and 1 < maxPositive:
                    threshold = maxPositive - 1
                _, binary   = cv2.threshold(subtracted, threshold, 255, cv2.THRESH_BINARY)
            else:
                binary = np.zeros_like(subtracted)

        # 連結成分で星点を検出
        try:
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except (cv2.error, SystemError):
            try:
                contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            except (cv2.error, SystemError):
                contours = []

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
            (center), (width, height), angle = cv2.minAreaRect(star)
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
            M = cv2.moments(star)
            if M['m00'] <= 0:
                positions.append(None)
                brightnesses.append(None)
            else:
                cx = float(M['m10'] / M['m00'])
                cy = float(M['m01'] / M['m00'])
                positions.append((cx, cy))
                xInt, yInt = int(round(cx)), int(round(cy))
                if 0 <= xInt < subtracted.shape[1] and 0 <= yInt < subtracted.shape[0]:
                    brightness = float(subtracted[yInt, xInt])
                    brightnesses.append(brightness)
                else:
                    brightnesses.append(None)

        ret = []
        for pos, brightness, aspectRatio in zip(positions, brightnesses, aspectRatios):
            if pos and brightness is not None:
                cx, cy = pos
                ret.append((cx, cy, brightness, aspectRatio))

        return ret

    def _createSaturationMask(self, image: np.ndarray) -> np.ndarray:
        """飽和領域のマスクを作成"""
        import cv2
        maxVal = np.max(image) if 0 < image.size else 255
        saturated = image > (maxVal * float(self.saturationThreshold) / 100.0)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
        mask = cv2.dilate(saturated.astype(np.uint8), kernel, iterations=2)
        return mask == 0

    def _selectDistributedStars(self, stars, imageShape):
        """画像全体に分散した星を選択"""
        if len(stars) < 10:
            return stars, []

        h, w = imageShape
        gridRows, gridCols = self.star.grid.rows, self.star.grid.cols
        cellH = h // gridRows
        cellW = w // gridCols

        distributedStars   = []
        gridSelectedCounts = []

        for row in range(gridRows):
            for col in range(gridCols):
                yMin = row * cellH
                yMax = (row + 1) * cellH if row < gridRows - 1 else h
                xMin = col * cellW
                xMax = (col + 1) * cellW if col < gridCols - 1 else w

                cellStars = [
                    (cx, cy, b, ar) for cx, cy, b, ar in stars
                    if xMin <= cx < xMax and yMin <= cy < yMax
                ]
                cellStars.sort(key=lambda x: x[2], reverse=True)
                selected = cellStars[:self.star.grid.starsPerGrid]
                distributedStars.extend(selected)
                gridSelectedCounts.append(len(selected))

        return distributedStars, gridSelectedCounts
    
    def _matchCatalog(self, detectedStars:list, catalogData:np.ndarray, imageShape:tuple, headers:dict, prevTransform:dict|None = None):
        """
        検出星とカタログ星を照合し、星リストと変換情報を返す
        
        Returns:
            tuple[list[dict], dict]: (照合星リスト, 推定変換パラメータ)
        """
        if 0 == len(detectedStars) or 0 == len(catalogData):
            return [], None

        h, w = imageShape
        cx, cy = w / 2.0, h / 2.0
        
        # RANSAC用固定シードを設定
        np.random.seed(self.star.ransac.seed)
        
        # 分散星を選択し明るさ順にソート
        selectedStars, _ = self._selectDistributedStars(detectedStars, imageShape)
        selectedStars.sort(key=lambda s: s[2], reverse=True)

        # 中心候補座標
        if prevTransform and "crval1" in prevTransform and "crval2" in prevTransform:
            crval1 = prevTransform["crval1"]
            crval2 = prevTransform["crval2"]
            if "fovDeg" in prevTransform:
                fovDeg = prevTransform["fovDeg"]
            else:
                fovDeg = self.estimatedFovDeg
        else:
            crval1 = self.approxRa
            crval2 = self.approxDec
            fovDeg = self.estimatedFovDeg
        
        # 探索範囲の決定
        searchRadius = max(0.5, fovDeg * 2.0)
        candidateCatalog = CatalogHelper.queryStars(catalogData, crval1, crval2, searchRadius, magLimit=self.catalogMagLimit)
        print("DEBUG", list(np.min(candidateCatalog,axis=0)))
        print("DEBUG", list(np.max(candidateCatalog,axis=0)))
        matchedStars = []
        bestTransform = None
        
        if 3 <= len(candidateCatalog) and 3 <= len(selectedStars):
            # カタログ星を接平面座標 (xi, eta) [rad] に投影
            catXi, catEta = CatalogHelper.gnomonicProjection(
                candidateCatalog[:, 1], candidateCatalog[:, 2], crval1, crval2
            )
        
            # 前回の変換が利用可能な場合
            if False:
                pass #未実装

            # 初回または前推定がない場合: RANSACによる幾何照合
            # 検出星の中心相対座標
            detU = np.array([s[0] - cx for s in selectedStars])
            detV = np.array([s[1] - cy for s in selectedStars])
            
            # 推定ピクセルスケール [rad/px]
            nominalScale = np.radians(fovDeg / ((w*w+h*h)**0.5)) # 対角
            minScale     = 0.7 * nominalScale
            maxScale     = 1.3 * nominalScale

            nDet = min(12, len(selectedStars))
            nCat = min(30, len(candidateCatalog))
            
            # 最初に使うための「有効な」検出星を抽出
            valid_det_idx = []
            for i in range(nDet):
                is_valid = True
                for j in range(nDet):
                    if i == j: continue
                    if np.hypot(detU[i] - detU[j], detV[i] - detV[j]) < 20.0:
                        is_valid = False
                        break
                if is_valid: valid_det_idx.append(i)
            
            if len(valid_det_idx) < 2:
                valid_det_idx = list(range(min(nDet, len(selectedStars))))

            bestInliers = 0
            bestModel   = None
            
            # RANSACループ
            for _ in range(self.star.ransac.iterations):
                idx1 = np.random.choice(valid_det_idx)
                idx2 = np.random.choice([i for i in valid_det_idx if i != idx1])
                
                pIdx1 = np.random.randint(0, nCat - 1)
                pIdx2 = np.random.randint(0, nCat - 1)
                if pIdx1 == pIdx2: continue
                
                dImg = np.hypot(detU[idx1] - detU[idx2], detV[idx1] - detV[idx2])
                if dImg < 20.0: continue
                angImg = np.arctan2(detV[idx2] - detV[idx1], detU[idx2] - detU[idx1])
                
                dSky = np.hypot(catXi[pIdx1] - catXi[pIdx2], catEta[pIdx1] - catEta[pIdx2])
                pairScale = dSky / dImg
                
                if not (minScale <= pairScale <= maxScale):
                    continue
                
                angSky = np.arctan2(catEta[pIdx2] - catEta[pIdx1], catXi[pIdx2] - catXi[pIdx1])
                rot = -(angSky + angImg)
                cR, sR = np.cos(rot), np.sin(rot)
                
                # オフセット項の計算
                predXi0  = ( detU[idx1] * cR - detV[idx1] * sR) * pairScale
                predEta0 = (-detU[idx1] * sR - detV[idx1] * cR) * pairScale
                dXi  = catXi[pIdx1] - predXi0
                dEta = catEta[pIdx1] - predEta0
                
                # 全ての検出点に対して、オフセットを考慮した予測座標を計算
                predXiAll  = ( (detU[valid_det_idx] * cR - detV[valid_det_idx] * sR) * pairScale + dXi )
                predEtaAll = ( (-detU[valid_det_idx] * sR - detV[valid_det_idx] * cR) * pairScale + dEta )
                
                # インライア判定
                currentInliers = 0
                for k in range(len(valid_det_idx)):
                    dists = np.hypot(catXi - predXiAll[k], catEta - predEtaAll[k])
                    if np.min(dists) / pairScale < 5.0:
                        currentInliers += 1
                
                if currentInliers > bestInliers:
                    bestInliers = currentInliers
                    bestModel   = (pairScale, rot, dXi, dEta)
            
            if bestModel is not None and 3 <= bestInliers:
                bestScale, bestRot, bestDXi, bestDEta = bestModel
                cR, sR = np.cos(bestRot), np.sin(bestRot)
                
                matchedRows = []
                for s in selectedStars:
                    u = s[0] - cx
                    v = s[1] - cy
                    
                    # 最終的な座標変換: 回転・スケール + RANSACで求めたオフセット
                    predXi  = ( u * cR - v * sR) * bestScale + bestDXi
                    predEta = (-u * sR - v * cR) * bestScale + bestDEta
                    
                    dists = np.hypot(catXi - predXi, catEta - predEta)
                    minIdx = np.argmin(dists)
                    minDistPx = dists[minIdx] / bestScale
                    
                    if minDistPx <= 5.0:
                        catRow = candidateCatalog[minIdx]
                        matchedRows.append({
                            'hip'        : float(catRow[0]),
                            'x'          : float(s[0]),
                            'y'          : float(s[1]),
                            'brightness' : float(s[2]),
                            'catalog_ra' : float(catRow[1]),
                            'catalog_dec': float(catRow[2]),
                        })

                if 3 <= len(matchedRows):
                    matchedStars = matchedRows
                    bestTransform = {
                        'crval1'  : crval1,
                        'crval2'  : crval2,
                        'fovDeg'  : fovDeg,
                    }
        
        if len(matchedStars) < 3:
            # 失敗時
            return [], None
        else:
            return matchedStars, bestTransform
    
    def _createTableOutput(self, matchedStars: list, parentHeaders: dict) -> FlowData:
        """星リストから Table 型 FlowData を作成"""
        from config import BLOCK_SIZE

        columns = ['hip', 'x', 'y', 'brightness', 'catalog_ra', 'catalog_dec']
        lines   = [f"star_{i}" for i in range(len(matchedStars))]

        tableRows = []
        for star in matchedStars:
            row = [
                star['hip'],
                star['x'],
                star['y'],
                star['brightness'],
                star['catalog_ra'],
                star['catalog_dec']
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

    def _flowDataToImage(self, flowData: FlowData, planeIndex: int = 0, normalizeForDetection: bool = True) -> np.ndarray:
        """FlowData から星検出用のグレースケール画像を構築"""
        width, height = flowData.getDimensions()
        image = nh.zeros((height, width), dtype=nh.BDTYPE)

        for block in flowData.iterateBlocks():
            if block and block.planeIndex == planeIndex:
                y1, y2 = block.y, block.y + block.getHeight()
                x1, x2 = block.x, block.x + block.getWidth()
                if 3 == len(block.data.shape):
                    image[y1:y2, x1:x2] = block.data[:, :, 0]
                else:
                    image[y1:y2, x1:x2] = block.data

        if normalizeForDetection:
            minVal = np.nanmin(image)
            maxVal = np.nanmax(image)
            if maxVal > minVal:
                margin = (maxVal - minVal) * float(self.saturationThreshold) / 100.0
                satLow = minVal + margin
                satHigh = maxVal - margin
                validMask = (image > satLow) & (image < satHigh)
                validPixels = image[validMask]
                if np.any(validMask):
                    meanVal = np.mean(validPixels)
                    stdVal  = np.std(validPixels)
                else:
                    meanVal = np.mean(image)
                    stdVal  = np.std(image)

                if stdVal > 0:
                    normalized = (image - meanVal) / stdVal
                    clipped    = np.clip((normalized + 3.0) / 6.0 * 255.0, 0.0, 255.0)
                    return clipped.astype(np.uint8)

            return np.zeros((height, width), dtype=np.uint8)

        return image.astype(np.uint8)
    
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
                 f"{self.matchRadius}_"
                 f"{self.catalogMagLimit}_"
                 f"{self.estimatedFovDeg}_"
                 f"{self.approxRa}_"
                 f"{self.approxDec}_"
                 f"{self.useApproxCoords}_"
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
        self.matchRadEntry = tk.Entry(radFrame, width=6)
        self.matchRadEntry.insert(0, str(self.node.matchRadius))
        self.matchRadEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(radFrame, text="deg (カタログ対応付けの最大距離)").pack(side=tk.LEFT)

        # 等級上限
        magFrame = tk.Frame(mainFrame)
        magFrame.pack(fill=tk.X, pady=2)
        tk.Label(magFrame, text="  カタログ等級上限:").pack(side=tk.LEFT)
        self.magLimitEntry = tk.Entry(magFrame, width=6)
        self.magLimitEntry.insert(0, str(self.node.catalogMagLimit))
        self.magLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(magFrame, text="mag (これより暗い星を除外)").pack(side=tk.LEFT)

        # 推定画角
        fovFrame = tk.Frame(mainFrame)
        fovFrame.pack(fill=tk.X, pady=2)
        tk.Label(fovFrame, text="  推定画角:").pack(side=tk.LEFT)
        self.fovEntry = tk.Entry(fovFrame, width=6)
        self.fovEntry.insert(0, str(self.node.estimatedFovDeg))
        self.fovEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(fovFrame, text="deg (長辺画角の目安)").pack(side=tk.LEFT)

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
            self.node.star.ransac.iterations   = max(10, min(1000, int(self.ransacEntry.get())))
            self.node.star.ransac.seed         = max(1, int(self.ransacSeedEntry.get()))
            self.node.matchRadius              = max(0.001, float(self.matchRadEntry.get()))
            self.node.catalogMagLimit          = float(self.magLimitEntry.get())
            self.node.estimatedFovDeg          = max(0.01, float(self.fovEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
