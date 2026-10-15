'''
PointsExtractionNode - 点像抽出ノード

画像から点像(点光源)を抽出しリストを出力するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

import hashlib

import tkinter as tk
from tkinter import messagebox

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

if TYPE_CHECKING:
    import numpy as np
    from base.FlowData import FlowData

class PointsExtractionNode(FlowNode, ConfigurableNode):
    """画像から点像(点光源)を抽出しリストを出力するノード"""
    
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'points_extraction'
    # ノード名
    name      = '点像抽出'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_AUX
    
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # 設定パラメータ
        # 画像パラメータ
        self.targetPlane    = 1                     # 抽出対象プレーン (0:R, 1:G, 2:B ...)
        
        # 点像抽出パラメータ
        self.threshold      = 95.0                  # 抽出閾値 [%]
        self.minDiameter    = 2                     # 最小直径 [px]
        self.maxDiameter    = 16                    # 最大直径 [px]
        self.maxAspectRatio = 2.0                   # 最大アスペクト比
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return

    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nThr:{self.threshold}% Max:{self.maxDiameter}px"
        return displayText

    def store(self, nodeData):
        """ノード設定を辞書に保存"""
        nodeData["targetPlane"]    = self.targetPlane
        nodeData["threshold"]      = self.threshold
        nodeData["minDiameter"]    = self.minDiameter
        nodeData["maxDiameter"]    = self.maxDiameter
        nodeData["maxAspectRatio"] = self.maxAspectRatio

    def restore(self, nodeData):
        """辞書からノード設定を復元"""
        if "targetPlane" in nodeData:
            self.targetPlane = nodeData["targetPlane"]
        if "threshold" in nodeData:
            self.threshold = nodeData["threshold"]
        if "minDiameter" in nodeData:
            self.minDiameter = nodeData["minDiameter"]
        if "maxDiameter" in nodeData:
            self.maxDiameter = nodeData["maxDiameter"]
        if "maxAspectRatio" in nodeData:
            self.maxAspectRatio = nodeData["maxAspectRatio"]

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
        """点像抽出処理のメイン実行"""
        from utils import numpy_helpers as nh
        
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

        # 各画像から点像を抽出し、カタログ照合
        outputFlowDatas = []
        totalImages     = len(inputStream)
        
        for i, flowData in enumerate(inputStream):
            self.reportProgress(context, f"画像 {i + 1}/{totalImages} 処理中", i, totalImages)
            
            # 指定プレーンを取得
            width, height = flowData.getDimensions()
            planeIndex = min(self.targetPlane, flowData.getPlaneCount() - 1)
            image = nh.nans((height, width))
            for block in flowData.iterateBlocks(planeIndex):
                if block:
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    image[y:y+h, x:x+w] = block.data
            
            # 点像を抽出
            points = self.detectPoints(image)

            # 出力 Table FlowData を作成
            outTable = self.createFlowData(flowData, points)
            outputFlowDatas.append(outTable)

        self.flowDatas = outputFlowDatas
        self.reportProgress(context, "完了")
    
    def detectPoints(self, image:np.ndarray) -> list[tuple[float, float, float, float, float, float]]:
        """
        画像から点像を抽出
        
        Args:
            image: 抽出用グレースケール画像 (uint8)
            
        Returns:
            (cx, cy, brightness, centerBrightness, area, aspectRatio) のリスト
        """
        import numpy as np
        import cv2

        # 閾値処理
        threshold = np.nanpercentile(image, self.threshold)
        binary = np.where(image <= threshold, 0, 255).astype(np.uint8)

        # 連結成分で点像を抽出
        try:
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except (cv2.error, SystemError):
            # OpenCV 4.5.5以降のバグ対応
            from utils.Debug import Debug
            Debug.log(type(self).__name__,"Retry cv2.findContours")
            try:
                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            except (cv2.error, SystemError):
                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = contours

        # 面積フィルタ
        minArea = np.pi * (self.minDiameter / 2.0) ** 2
        maxArea = np.pi * (self.maxDiameter / 2.0) ** 2

        result = []
        for point in points:
            # 面積フィルタ
            area = cv2.contourArea(point)
            if area < minArea or maxArea < area:
                continue
            
            # アスペクト比フィルタ（回転考慮）
            (center), (width, height), angle = cv2.minAreaRect(point) # 最小外接矩形（回転考慮）
            if width <= 0 or height <= 0:
                continue
            
            aspectRatio = max(width, height) / min(width, height)
            if self.maxAspectRatio < aspectRatio:
                continue
                
            # 位置を取得
            M = cv2.moments(point)
            if M['m00'] <= 0:
                continue
            
            cx = float(M['m10'] / M['m00']) # 点像の重心
            cy = float(M['m01'] / M['m00']) # 点像の重心
            
            # 重心の明るさを取得(サブピクセル考慮)
            ix, iy = int(cx), int(cy)

            # 周辺の輝度分布を考慮したサブピクセル輝度の推定（バイリニア補間）
            # 座標x, yが画像範囲内にあるか確認
            if image.shape[1] - 1 <= ix and image.shape[0] - 1 <= iy:
                # 範囲外の場合は最寄りの画素を使用
                centerBrightness = image[iy, ix]
            else:
                # 周辺4画素の輝度を取得
                q11 = image[iy, ix]
                q12 = image[iy, ix + 1]
                q21 = image[iy + 1, ix]
                q22 = image[iy + 1, ix + 1]

                # バイリニア補間による輝度計算
                dx = cx - ix
                dy = cy - iy
                centerBrightness = ( q11 * (1 - dx) * (1 - dy)
                                   + q12 *      dx  * (1 - dy)
                                   + q21 * (1 - dx) *      dy
                                   + q22 *      dx  *      dy
                                   )
            
            # 明るさを取得
            # 点像の明度を取得(広がりの合計)
            # 点像は無限遠の点とみなし分散している明るさを合計する
            # 輪郭からマスクを作成して、点像を取得
            # 輪郭の少し外まで採る(直径を1.4倍)
            n = 1.41421356237
            x, y, w, h = cv2.boundingRect(point)

            # 点像の外郭を n 倍
            ew = int(np.ceil(w * (n - 1) / 2))
            eh = int(np.ceil(h * (n - 1) / 2))
            x -= ew
            y -= eh
            w += w + 2 * ew - (x if x < 0 else 0)
            h += h + 2 * eh - (y if y < 0 else 0)
            x = max(x, 0)
            y = max(y, 0)
            w = min(w, image.shape[1] - x)
            h = min(h, image.shape[0] - y)

            # 最小マスクを作成
            offsetPoint = point - [x, y]
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [offsetPoint], -1, 255, thickness=cv2.FILLED) # 輪郭を取得
            r = np.sqrt(np.sum(mask > 0)/np.pi)
            k = int(np.ceil(r * (n - 1))) * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)) # 輪郭を拡張
            mask = cv2.dilate(mask, kernel, iterations=1)
            
            # 元の画像からマスク部分を切り出し
            pointAreaValues = image[y:y+h, x:x+w][mask > 0]
            if pointAreaValues.size <= 0:
                continue
            
            # 分散している明るさを合計
            brightness = float(np.sum(pointAreaValues))
            
            result.append((cx, cy, brightness, centerBrightness, area, aspectRatio))

        return result

    def createFlowData(self, inputData:FlowData, points:list[list]) -> FlowData:
        """点像リストから Table 型 FlowData を作成"""
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        from base import FlowData
        
        # 原点距離でソート
        points.sort(key=lambda p: p[0]**2 + p[1]**2)
        
        columns = ['x', 'y', 'brightness', 'center_brightness', 'area', 'aspect_raito']
        lines   = [f"{y}" for y in range(len(points))]

        tableRows = []
        for point in points:
            row = [
                point[0],
                point[1],
                point[2],
                point[3],
                point[4],
                point[5],
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
            'planes'  : ['point_extraction'],
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
        return PointsExtractionSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config =(f"{self.minorType}_"
                 f"{self._outputCat}_"
                 f"{self.targetPlane}_"
                 f"{self.threshold}_"
                 f"{self.minDiameter}_"
                 f"{self.maxDiameter}_"
                 f"{self.maxAspectRatio}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class PointsExtractionSettingsDialog(tk.Toplevel):
    """PointsExtractionNode 用設定ダイアログ"""
    
    def __init__(self, parent, node:PointsExtractionNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("450x300")
        
        self._createWidgets()
    
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 画像パラメータ
        tk.Label(mainFrame, text="■ 画像パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 位置合わせ用プレーン
        planeFrame = tk.Frame(mainFrame)
        planeFrame.pack(fill=tk.X, pady=2)
        tk.Label(planeFrame, text="抽出対象プレーン:").pack(side=tk.LEFT)
        self.planeEntry = tk.Entry(planeFrame, width=5)
        self.planeEntry.insert(0, str(self.node.targetPlane))
        self.planeEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(planeFrame, text="(0:R, 1:G, 2:B, ... )").pack(side=tk.LEFT)
        
        # カタログ照合パラメータ
        tk.Label(mainFrame, text="■ カタログ照合パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 点像抽出パラメータ
        tk.Label(mainFrame, text="■ 点像抽出パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(8, 2))
        
        # 点像抽出閾値
        thresholdFrame = tk.Frame(mainFrame)
        thresholdFrame.pack(fill=tk.X, pady=2)
        tk.Label(thresholdFrame, text="  点像抽出閾値:").pack(side=tk.LEFT)
        self.thresholdEntry = tk.Entry(thresholdFrame, width=5)
        self.thresholdEntry.insert(0, str(self.node.threshold))
        self.thresholdEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(thresholdFrame, text="% (上位%の明るい点像を選択)").pack(side=tk.LEFT)
        
        # 点像直径閾値
        sizeFrame = tk.Frame(mainFrame)
        sizeFrame.pack(fill=tk.X, pady=2)
        tk.Label(sizeFrame, text="  点像直径閾値:").pack(side=tk.LEFT)
        self.minDiameterEntry = tk.Entry(sizeFrame, width=5)
        self.minDiameterEntry.insert(0, str(self.node.minDiameter))
        self.minDiameterEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(sizeFrame, text="~").pack(side=tk.LEFT)
        self.maxDiameterEntry = tk.Entry(sizeFrame, width=5)
        self.maxDiameterEntry.insert(0, str(self.node.maxDiameter))
        self.maxDiameterEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(sizeFrame, text="px (抽出対象の点像直径)").pack(side=tk.LEFT)
        
        # 最大アスペクト比
        aspectRatioFrame = tk.Frame(mainFrame)
        aspectRatioFrame.pack(fill=tk.X, pady=2)
        tk.Label(aspectRatioFrame, text="  最大アスペクト比:").pack(side=tk.LEFT)
        self.aspectRatioEntry = tk.Entry(aspectRatioFrame, width=5)
        self.aspectRatioEntry.insert(0, str(self.node.maxAspectRatio))
        self.aspectRatioEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(aspectRatioFrame, text="(細長いノイズを除外)").pack(side=tk.LEFT)
        
        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            self.node.targetPlane       = max(0, int(self.planeEntry.get()))
            self.node.threshold         = max(0.0, min(100.0, float(self.thresholdEntry.get())))
            self.node.minDiameter       = max(1, int(self.minDiameterEntry.get()))
            self.node.maxDiameter       = max(self.node.minDiameter, int(self.maxDiameterEntry.get()))
            self.node.maxAspectRatio    = max(1.0, float(self.aspectRatioEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
