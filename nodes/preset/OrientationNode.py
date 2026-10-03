'''
OrientationNode - 向き特定ノード

抽出された星リストから画像の方位（回転角）、中心天球座標、ピクセルスケールを算出するノード

Copyright (c) 2026 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import tkinter as tk
from tkinter import messagebox
import numpy as np

from base.FlowNode_CONST import *
from base import FlowNode
from base import FlowData
from base import DataBlock
from nodes import ConfigurableNode
from utils import numpy_helpers as nh
from utils.catalog_helper import Catalog

class OrientationNode(FlowNode, ConfigurableNode):
    """星リストの天体座標と画像座標から、画像の天球上の姿勢（回転角・中心赤道座標）を特定するノード"""

    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'orientation'
    # ノード名
    name      = '向き特定'
    # 入出力タイプ
    ioType    = _IO_TYPE_N1
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

        # 設定パラメータ
        self.ransacThresholdPx = 3.0    # RANSACインライア許容距離 (px)
        self.ransacIterations  = 100    # RANSAC試行回数
        self.ransacSeed        = 2725   # RANSAC乱数シード

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nIter:{self.ransacIterations}"
        return displayText

    def store(self, nodeData):
        """設定の保存"""
        nodeData["ransacThresholdPx"] = self.ransacThresholdPx
        nodeData["ransacIterations"]  = self.ransacIterations
        nodeData["ransacSeed"]        = self.ransacSeed

    def restore(self, nodeData):
        """設定の復元"""
        if "ransacThresholdPx" in nodeData:
            self.ransacThresholdPx = nodeData["ransacThresholdPx"]
        if "ransacIterations" in nodeData:
            self.ransacIterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.ransacSeed = nodeData["ransacSeed"]

    def createSettingWindow(self):
        """設定ダイアログを作成"""
        return OrientationSettingsDialog(self.view.editor.root, self)

    def process(self, context=None):
        """向き特定のメイン処理"""
        self.reportProgress(context, "開始")

        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)

        if 0 == len(inputStreams) or not inputStreams[0]:
            self.flowDatas = []
            return

        starTables = inputStreams[0]
        results    = []
        lines      = []

        totalTables = len(starTables)
        for i, tableFlowData in enumerate(starTables):
            self.reportProgress(context, f"画像 {i + 1}/{totalTables} の向き特定中", i, totalTables)
            
            # 画像識別子の取得
            sourceFile = tableFlowData.headers.get("source_file", "")
            datetimeStr = tableFlowData.headers.get("datetime", "")
            if sourceFile:
                imageId = sourceFile
            elif datetimeStr:
                imageId = f"datetime_{datetimeStr}"
            else:
                imageId = f"image_{i}"

            lines.append(imageId)

            # Table データから星配列を抽出
            starData = self._loadStarData(tableFlowData)
            width    = tableFlowData.headers.get("width", 1000)
            height   = tableFlowData.headers.get("height", 1000)

            # 姿勢パラメータの計算
            orientation = self._calculateOrientation(starData, width, height)
            results.append(orientation)

        # 姿勢情報 Table FlowData の生成
        outFlowData = self._createTableOutput(results, lines, starTables[0].headers)
        self.flowDatas = [outFlowData]

        self.reportProgress(context, "完了")

    def _loadStarData(self, flowData: FlowData) -> np.ndarray:
        """Table FlowData から [hip_id, x, y, brightness, catalog_ra, catalog_dec] を読み込む"""
        blocks = list(flowData.iterateBlocks())
        if 0 == len(blocks) or blocks[0].data is None:
            return nh.zeros((0, 6), dtype=nh.BDTYPE)

        dataList = [block.data for block in blocks if block and block.data is not None]
        if 0 == len(dataList):
            return nh.zeros((0, 6), dtype=nh.BDTYPE)

        return np.vstack(dataList)

    def _calculateOrientation(self, starData: np.ndarray, width: int, height: int) -> dict:
        """
        抽出された星の座標から回転角、中心赤道座標、ピクセルスケールを計算する
        
        Args:
            starData: [N, 6] の配列 (hip_id, x, y, brightness, catalog_ra, catalog_dec)
            width: 画像幅 (px)
            height: 画像高さ (px)
            
        Returns:
            dict: 算出結果 {'crval1', 'crval2', 'rotation', 'pixel_scale', 'confidence'}
        """
        cx = width / 2.0
        cy = height / 2.0

        # カタログ座標が有効な星 (NaN でないもの) をフィルタリング
        if 0 == len(starData):
            return {'crval1': 0.0, 'crval2': 0.0, 'rotation': 0.0, 'pixel_scale': 0.0, 'confidence': 0.0}

        validMask = (
            ~np.isnan(starData[:, 0])
            & ~np.isnan(starData[:, 4])
            & ~np.isnan(starData[:, 5])
        )
        validStars = starData[validMask]

        if len(validStars) < 3: # 3 点未満では一意に特定不能
            return {'crval1': 0.0, 'crval2': 0.0, 'rotation': 0.0, 'pixel_scale': 0.0, 'confidence': 0.0}

        # 画像座標とカタログ座標
        imgX  = validStars[:, 1]
        imgY  = validStars[:, 2]
        catRa = validStars[:, 4]
        catDec= validStars[:, 5]

        # カタログ星の重心を中心天球座標の初期値とする
        meanRa  = float(np.mean(catRa))
        meanDec = float(np.mean(catDec))

        # 接平面投影 (xi, eta) [rad]
        xi, eta = Catalog.gnomonicProjection(catRa, catDec, meanRa, meanDec)

        # 画像中心基準座標 (u, v)
        u = imgX - cx
        v = imgY - cy

        # RANSAC による類似変換推定 (スケール、回転、中心オフセット)
        rng = np.random.default_rng(self.ransacSeed)
        nStars = len(validStars)
        bestInliers = 0
        bestModel   = None

        for _ in range(self.ransacIterations):
            sampleIdx = rng.choice(nStars, size=2, replace=False)
            uSub = u[sampleIdx]
            vSub = v[sampleIdx]
            xiSub = xi[sampleIdx]
            etaSub = eta[sampleIdx]

            dImg = np.sqrt((uSub[0] - uSub[1])**2 + (vSub[0] - vSub[1])**2)
            dSky = np.sqrt((xiSub[0] - xiSub[1])**2 + (etaSub[0] - etaSub[1])**2)

            if dImg < 1e-5 or dSky < 1e-8:
                continue

            # スケール比 [rad/px]
            scale = dSky / dImg

            # 回転角差
            angImg = np.arctan2(vSub[1] - vSub[0], uSub[1] - uSub[0])
            angSky = np.arctan2(etaSub[1] - etaSub[0], xiSub[1] - xiSub[0])
            rot    = angSky - angImg

            cosR, sinR = np.cos(rot), np.sin(rot)

            # 画像中心の接平面上のオフセット推定
            # xi = (u * cosR - v * sinR) * scale + dXi
            # eta = (u * sinR + v * cosR) * scale + dEta
            dXi  = np.mean(xiSub - ( uSub * cosR - vSub * sinR) * scale)
            dEta = np.mean(etaSub - (uSub * sinR + vSub * cosR) * scale)

            # 全点での残差計算
            predXi  = ( u * cosR - v * sinR) * scale + dXi
            predEta = ( u * sinR + v * cosR) * scale + dEta

            resPx = np.sqrt((xi - predXi)**2 + (eta - predEta)**2) / scale
            inliers = np.sum(resPx <= self.ransacThresholdPx)

            if bestInliers < inliers:
                bestInliers = inliers
                bestModel   = (scale, rot, dXi, dEta)

        if bestModel is None or bestInliers < 3:
            return {'crval1': meanRa, 'crval2': meanDec, 'rotation': 0.0, 'pixel_scale': 0.0, 'confidence': 0.0}

        scale, rot, dXi, dEta = bestModel
        cosR, sinR = np.cos(rot), np.sin(rot)

        # インライア点を用いて最小二乗再推定
        predXi  = ( u * cosR - v * sinR) * scale + dXi
        predEta = ( u * sinR + v * cosR) * scale + dEta
        inlierMask = (np.sqrt((xi - predXi)**2 + (eta - predEta)**2) / scale) <= self.ransacThresholdPx  # noqa: F841

        # 画像中心 (u=0, v=0) の天球座標 (crval1, crval2)
        centerXiRad  = float(dXi)
        centerEtaRad = float(dEta)
        centerRaDeg, centerDecDeg = Catalog.gnomonicDeprojection(
            centerXiRad, centerEtaRad, meanRa, meanDec
        )

        rotationDeg = float(np.degrees(rot)) % 360.0
        scaleDegPerPx = float(np.degrees(scale))
        confidence = float(min(1.0, bestInliers / 20.0))

        return {
            'crval1'     : centerRaDeg,
            'crval2'     : centerDecDeg,
            'rotation'   : rotationDeg,
            'pixel_scale': scaleDegPerPx,
            'confidence' : confidence,
        }

    def _createTableOutput(self, results: list, lines: list, parentHeaders: dict) -> FlowData:
        """姿勢情報 Table FlowData の作成"""
        from config import BLOCK_SIZE

        columns = ['crval1', 'crval2', 'rotation', 'pixel_scale', 'confidence']
        tableRows = []

        for res in results:
            row = [
                res['crval1'],
                res['crval2'],
                res['rotation'],
                res['pixel_scale'],
                res['confidence']
            ]
            tableRows.append(row)

        if 0 < len(tableRows):
            tableArray = nh.array(tableRows, dtype=nh.BDTYPE)
        else:
            tableArray = nh.zeros((0, len(columns)), dtype=nh.BDTYPE)

        headers = {
            'category': self.getOutputCategory(),
            'type'    : 'table',
            'mode'    : '2D',
            'columns' : columns,
            'lines'   : lines,
            'planes'  : ['orientation'],
        }

        # メタデータを継承
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


class OrientationSettingsDialog(tk.Toplevel):
    """OrientationNode 用設定ダイアログ"""

    def __init__(self, parent, node: OrientationNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("420x260")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()

        self._createWidgets()

    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self, padx=15, pady=15)
        mainFrame.pack(fill=tk.BOTH, expand=True)

        tk.Label(mainFrame, text="■ 姿勢推定パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))

        # RANSAC インライア許容距離
        thrFrame = tk.Frame(mainFrame)
        thrFrame.pack(fill=tk.X, pady=4)
        tk.Label(thrFrame, text="インライア許容距離:").pack(side=tk.LEFT)
        self.thrEntry = tk.Entry(thrFrame, width=6)
        self.thrEntry.insert(0, str(self.node.ransacThresholdPx))
        self.thrEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(thrFrame, text="px (外れ値判定閾値)").pack(side=tk.LEFT)

        # RANSAC 試行回数
        iterFrame = tk.Frame(mainFrame)
        iterFrame.pack(fill=tk.X, pady=4)
        tk.Label(iterFrame, text="RANSAC試行回数:").pack(side=tk.LEFT)
        self.iterEntry = tk.Entry(iterFrame, width=6)
        self.iterEntry.insert(0, str(self.node.ransacIterations))
        self.iterEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(iterFrame, text="回").pack(side=tk.LEFT)

        # RANSAC 乱数シード
        seedFrame = tk.Frame(mainFrame)
        seedFrame.pack(fill=tk.X, pady=4)
        tk.Label(seedFrame, text="RANSAC乱数シード:").pack(side=tk.LEFT)
        self.seedEntry = tk.Entry(seedFrame, width=6)
        self.seedEntry.insert(0, str(self.node.ransacSeed))
        self.seedEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(seedFrame, text="(1以上の整数)").pack(side=tk.LEFT)

        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=15)

        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.onClose)

    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            self.node.ransacThresholdPx = max(0.1, float(self.thrEntry.get()))
            self.node.ransacIterations  = max(10, min(10000, int(self.iterEntry.get())))
            self.node.ransacSeed        = max(1, int(self.seedEntry.get()))

            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")

    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
