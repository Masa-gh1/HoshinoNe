'''
DistortionAnalysisNode - 歪み解析ノード

星リストの幾何学的配置のズレから、FITS SIP 規約に基づく光学系の歪み多項式係数を算出するノード

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
from utils.catalog_helper import CatalogHelper

class DistortionAnalysisNode(FlowNode, ConfigurableNode):
    """星リストの幾何学配置から FITS SIP (Simple Imaging Polynomial) 歪み係数を特定するノード"""

    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'distortion_analysis'
    # ノード名
    name      = '歪み解析'
    # 入出力タイプ
    ioType    = _IO_TYPE_N1
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

        # 設定パラメータ
        self.sipOrder          = 3      # SIP多項式次数 (2または3)
        self.ransacThresholdPx = 2.0    # RANSAC外れ値閾値 (px)
        self.ransacIterations  = 100    # RANSAC試行回数
        self.ransacSeed        = 2725   # RANSAC乱数シード

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nSIP Order:{self.sipOrder}"
        return displayText

    def store(self, nodeData):
        """設定の保存"""
        nodeData["sipOrder"]          = self.sipOrder
        nodeData["ransacThresholdPx"] = self.ransacThresholdPx
        nodeData["ransacIterations"]  = self.ransacIterations
        nodeData["ransacSeed"]        = self.ransacSeed

    def restore(self, nodeData):
        """設定の復元"""
        if "sipOrder" in nodeData:
            self.sipOrder = nodeData["sipOrder"]
        if "ransacThresholdPx" in nodeData:
            self.ransacThresholdPx = nodeData["ransacThresholdPx"]
        if "ransacIterations" in nodeData:
            self.ransacIterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.ransacSeed = nodeData["ransacSeed"]

    def createSettingWindow(self):
        """設定ダイアログを作成"""
        return DistortionAnalysisSettingsDialog(self.view.editor.root, self)

    def process(self, context=None):
        """歪み解析のメイン処理"""
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
            self.reportProgress(context, f"画像 {i + 1}/{totalTables} の歪み解析中", i, totalTables)

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

            # FITS SIP 係数を計算
            sipParams = self._calculateSip(starData, width, height)
            results.append(sipParams)

        # 歪み係数 Table FlowData の生成
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

    def _calculateSip(self, starData: np.ndarray, width: int, height: int) -> dict:
        """
        星配置から FITS SIP 歪みパラメータを算出する
        
        Args:
            starData: [N, 6] の配列 (hip_id, x, y, brightness, catalog_ra, catalog_dec)
            width: 画像幅 (px)
            height: 画像高さ (px)
            
        Returns:
            dict: SIP 係数辞書
        """
        crpix1 = width / 2.0
        crpix2 = height / 2.0

        defaultRes = {
            'CRPIX1'   : float(crpix1),
            'CRPIX2'   : float(crpix2),
            'A_ORDER'  : float(self.sipOrder),
            'B_ORDER'  : float(self.sipOrder),
            'A_2_0'    : 0.0,
            'A_1_1'    : 0.0,
            'A_0_2'    : 0.0,
            'A_3_0'    : 0.0,
            'A_2_1'    : 0.0,
            'A_1_2'    : 0.0,
            'A_0_3'    : 0.0,
            'B_2_0'    : 0.0,
            'B_1_1'    : 0.0,
            'B_0_2'    : 0.0,
            'B_3_0'    : 0.0,
            'B_2_1'    : 0.0,
            'B_1_2'    : 0.0,
            'B_0_3'    : 0.0,
            'RMS_ERROR': 0.0,
        }

        if 0 == len(starData):
            return defaultRes

        validMask = (
            ~np.isnan(starData[:, 0])
            & ~np.isnan(starData[:, 4])
            & ~np.isnan(starData[:, 5])
        )
        validStars = starData[validMask]

        # 3次の SIP には最低 8 点以上の星が必要
        minRequiredStars = 6 if 2 == self.sipOrder else 10
        if len(validStars) < minRequiredStars:
            return defaultRes

        imgX   = validStars[:, 1]
        imgY   = validStars[:, 2]
        catRa  = validStars[:, 4]
        catDec = validStars[:, 5]

        # 中心基準の相対ピクセル座標
        u = imgX - crpix1
        v = imgY - crpix2

        # 天球接平面投影
        meanRa  = float(np.mean(catRa))
        meanDec = float(np.mean(catDec))
        xi, eta = CatalogHelper.gnomonicProjection(catRa, catDec, meanRa, meanDec)

        # 線形変換行列の推定 (理想的な接平面線形位置へのフィッティング)
        # [xi, eta]^T = M * [u, v]^T + [t_xi, t_eta]^T
        designLinear = np.column_stack([u, v, np.ones_like(u)])
        fitXi, _, _, _  = np.linalg.lstsq(designLinear, xi, rcond=None)
        fitEta, _, _, _ = np.linalg.lstsq(designLinear, eta, rcond=None)

        # 逆線形行列を求めて、カタログ位置に対応する「理想線形ピクセル座標」 (u_ideal, v_ideal) を算出
        mMat = np.array([
            [fitXi[0], fitXi[1]],
            [fitEta[0], fitEta[1]]
        ])
        detM = np.linalg.det(mMat)
        if np.abs(detM) < 1e-15: # 特異行列の場合はデフォルト返却
            return defaultRes

        invM = np.linalg.inv(mMat)
        resXi  = xi - fitXi[2]
        resEta = eta - fitEta[2]

        idealU = invM[0, 0] * resXi + invM[0, 1] * resEta
        idealV = invM[1, 0] * resXi + invM[1, 1] * resEta

        # 歪み量: 観測ピクセルから理想ピクセルへの差分
        deltaU = idealU - u
        deltaV = idealV - v

        # SIP 多項式基底行列の構築
        # 2次項: u^2, u*v, v^2
        # 3次項: u^3, u^2*v, u*v^2, v^3
        basisList = [
            u**2,       # A_2_0
            u * v,      # A_1_1
            v**2,       # A_0_2
        ]
        if 3 <= self.sipOrder:
            basisList.extend([
                u**3,         # A_3_0
                (u**2) * v,   # A_2_1
                u * (v**2),   # A_1_2
                v**3,         # A_0_3
            ])

        basisMatrix = np.column_stack(basisList)

        # 最小二乗法により SIP 係数を推定
        coeffsA, residualsA, _, _ = np.linalg.lstsq(basisMatrix, deltaU, rcond=None)
        coeffsB, residualsB, _, _ = np.linalg.lstsq(basisMatrix, deltaV, rcond=None)

        # 残差 RMS 計算
        predDeltaU = basisMatrix @ coeffsA
        predDeltaV = basisMatrix @ coeffsB
        rmsError = float(np.sqrt(np.mean((deltaU - predDeltaU)**2 + (deltaV - predDeltaV)**2)))

        res = {
            'CRPIX1'   : float(crpix1),
            'CRPIX2'   : float(crpix2),
            'A_ORDER'  : float(self.sipOrder),
            'B_ORDER'  : float(self.sipOrder),
            'A_2_0'    : float(coeffsA[0]),
            'A_1_1'    : float(coeffsA[1]),
            'A_0_2'    : float(coeffsA[2]),
            'A_3_0'    : float(coeffsA[3]) if 3 <= self.sipOrder else 0.0,
            'A_2_1'    : float(coeffsA[4]) if 3 <= self.sipOrder else 0.0,
            'A_1_2'    : float(coeffsA[5]) if 3 <= self.sipOrder else 0.0,
            'A_0_3'    : float(coeffsA[6]) if 3 <= self.sipOrder else 0.0,
            'B_2_0'    : float(coeffsB[0]),
            'B_1_1'    : float(coeffsB[1]),
            'B_0_2'    : float(coeffsB[2]),
            'B_3_0'    : float(coeffsB[3]) if 3 <= self.sipOrder else 0.0,
            'B_2_1'    : float(coeffsB[4]) if 3 <= self.sipOrder else 0.0,
            'B_1_2'    : float(coeffsB[5]) if 3 <= self.sipOrder else 0.0,
            'B_0_3'    : float(coeffsB[6]) if 3 <= self.sipOrder else 0.0,
            'RMS_ERROR': rmsError,
        }

        return res

    def _createTableOutput(self, results: list, lines: list, parentHeaders: dict) -> FlowData:
        """FITS SIP パラメータ Table FlowData の作成"""
        from config import BLOCK_SIZE

        columns = [
            'CRPIX1', 'CRPIX2', 'A_ORDER', 'B_ORDER',
            'A_2_0', 'A_1_1', 'A_0_2', 'A_3_0', 'A_2_1', 'A_1_2', 'A_0_3',
            'B_2_0', 'B_1_1', 'B_0_2', 'B_3_0', 'B_2_1', 'B_1_2', 'B_0_3',
            'RMS_ERROR'
        ]

        tableRows = []
        for res in results:
            row = [res[col] for col in columns]
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
            'planes'  : ['distortion_analysis'],
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


class DistortionAnalysisSettingsDialog(tk.Toplevel):
    """DistortionAnalysisNode 用設定ダイアログ"""

    def __init__(self, parent, node: DistortionAnalysisNode):
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

        tk.Label(mainFrame, text="■ FITS SIP 歪み解析パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))

        # SIP 多項式次数
        orderFrame = tk.Frame(mainFrame)
        orderFrame.pack(fill=tk.X, pady=4)
        tk.Label(orderFrame, text="SIP多項式次数 (ORDER):").pack(side=tk.LEFT)
        self.orderVar = tk.IntVar(value=self.node.sipOrder)
        tk.Radiobutton(orderFrame, text="2次", variable=self.orderVar, value=2).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(orderFrame, text="3次", variable=self.orderVar, value=3).pack(side=tk.LEFT, padx=5)

        # RANSAC 外れ値閾値
        thrFrame = tk.Frame(mainFrame)
        thrFrame.pack(fill=tk.X, pady=4)
        tk.Label(thrFrame, text="インライア許容距離:").pack(side=tk.LEFT)
        self.thrEntry = tk.Entry(thrFrame, width=6)
        self.thrEntry.insert(0, str(self.node.ransacThresholdPx))
        self.thrEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(thrFrame, text="px (外れ値除外用)").pack(side=tk.LEFT)

        # RANSAC 試行回数
        iterFrame = tk.Frame(mainFrame)
        iterFrame.pack(fill=tk.X, pady=4)
        tk.Label(iterFrame, text="RANSAC試行回数:").pack(side=tk.LEFT)
        self.iterEntry = tk.Entry(iterFrame, width=6)
        self.iterEntry.insert(0, str(self.node.ransacIterations))
        self.iterEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(iterFrame, text="回").pack(side=tk.LEFT)

        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=15)

        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.onClose)

    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            self.node.sipOrder          = int(self.orderVar.get())
            self.node.ransacThresholdPx = max(0.1, float(self.thrEntry.get()))
            self.node.ransacIterations  = max(10, min(10000, int(self.iterEntry.get())))

            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")

    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
