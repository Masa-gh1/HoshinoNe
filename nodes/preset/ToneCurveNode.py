'''
ToneCurveNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

from base.FlowNode_CONST import *
from nodes import ConfigurableNode
from nodes import NNBlockOperationNode

class ToneCurveNode(NNBlockOperationNode,ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'tone_curve'
    # ノード名
    name      = 'トーンカーブ'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

        # デフォルト設定 - 半開区間 [0.0, 1.0) で正規化範囲
        self.displayMin = 0.0
        self.displayEnd = 1.0
        self.outputMin = 0.0
        self.outputEnd = 1.0
        self.controlPoints = [(0.0, 0.0), (1.0, 1.0)]  # (入力, 出力)
        self.boundaryCondition = 'natural'  # 境界条件
        
        # ライブラリチェック
        import importlib.util
        if not importlib.util.find_spec("scipy"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ scipy がインストールされていません。\npip install scipy でインストールしてください。")
            return
        
        if not importlib.util.find_spec("matplotlib"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ matplotlib がインストールされていません。\npip install matplotlib でインストールしてください。")
            return
    
    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\n{len(self.controlPoints)-2}点\n出力[{self.outputMin:.2f}, {self.outputEnd:.2f})"
        return displayText
    
    def store(self, nodeData):
        nodeData["displayMin"] = self.displayMin
        nodeData["displayEnd"] = self.displayEnd
        nodeData["outputMin"] = self.outputMin
        nodeData["outputEnd"] = self.outputEnd
        nodeData["controlPoints"] = self.controlPoints
        nodeData["boundaryCondition"] = self.boundaryCondition
    
    def restore(self, nodeData):
        if "displayMin" in nodeData:
            self.displayMin = nodeData["displayMin"]
        if "displayEnd" in nodeData:
            self.displayEnd = nodeData["displayEnd"]
        if "outputMin" in nodeData:
            self.outputMin = nodeData["outputMin"]
        if "outputEnd" in nodeData:
            self.outputEnd = nodeData["outputEnd"]
        if "controlPoints" in nodeData:
            self.controlPoints = nodeData["controlPoints"]
        if "boundaryCondition" in nodeData:
            self.boundaryCondition = nodeData["boundaryCondition"]
    
    def createSettingWindow(self):
        return ToneCurveDialog( self.view.editor.root, self)
        
    def processBlock(self, block):
        import numpy as np
        from scipy.interpolate import interp1d, CubicSpline
        from base import DataBlock

        planeIndex = block.planeIndex
        x, y = block.x, block.y
        
        # DataBlockから実際のデータを取得
        data = block.data
        
        # NaN値を事前に検出・分離
        nan_mask = np.isnan(data)
        if np.all(nan_mask):
            # 全てNaNの場合はそのまま返す
            return DataBlock(data, planeIndex, x, y)
        
        # トーンカーブ関数を作成
        sortedPoints = sorted(self.controlPoints, key=lambda p: p[0])
        xValues = [p[0] for p in sortedPoints]
        yValues = [p[1] for p in sortedPoints]

        # 制御点数に応じて補間方法を選択
        if len(xValues) <= 2:
            # 2点なので線形補完
            curveFunction = interp1d( xValues, yValues, kind='linear', bounds_error=False, fill_value='extrapolate')
        else:
            # 3点以上なのでスプライン補完
            curveFunction = CubicSpline( xValues, yValues, bc_type=self.boundaryCondition, extrapolate=True)
        
        # 結果データを初期化（NaN値を保持）
        result = data.copy()
        
        # 有効値（NaN以外）のみ処理
        valid_mask = ~nan_mask
        valid_data = result[valid_mask]
        
        # 始点・終点の外側をクランプ
        startPoint = sortedPoints[0]
        endPoint = sortedPoints[-1]
        
        # 範囲外の処理
        mask_below = valid_data < startPoint[0]
        mask_above = valid_data > endPoint[0]
        mask_inside = ~(mask_below | mask_above)
        
        # 結果データを初期化
        adjustedData = np.zeros_like(valid_data)
        
        # 範囲内のデータにトーンカーブを適用
        if np.any(mask_inside):
            adjustedData[mask_inside] = curveFunction(valid_data[mask_inside])
        
        # 範囲外のデータを始点・終点の値に設定
        if np.any(mask_below):
            adjustedData[mask_below] = startPoint[1]
        if np.any(mask_above):
            adjustedData[mask_above] = endPoint[1]
        
        # [0.0, 1.0) から出力範囲 [outputMin, outputEnd) に変換
        processedData = adjustedData * (self.outputEnd - self.outputMin) + self.outputMin
        
        # 出力範囲内にクリップ
        processedData = np.clip(processedData, self.outputMin, self.outputEnd)
        
        # 有効値のみ結果に反映
        result[valid_mask] = processedData
        
        # 新しいDataBlockを作成して返す
        return DataBlock(result, planeIndex, x, y)
    
    def applySettings(self, inputMin, inputEnd, outputMin, outputEnd, controlPoints, boundaryCondition):
        self.displayMin = inputMin
        self.displayEnd = inputEnd
        self.outputMin = outputMin
        self.outputEnd = outputEnd
        self.controlPoints = controlPoints
        self.boundaryCondition = boundaryCondition
        self.view.onNodeConfigChanged(self)
    
    def setupDisplayLevels(self, outputFlowData, inputFlowData):
        """出力のdisplay_levelsを設定"""
        outputFlowData.headers['display_levels'] = {
            'min': self.outputMin,
            'exclusive_upper': self.outputEnd
        }
    
    def getConfigHash(self):
        config = f"{self.outputMin}_{self.outputEnd}_{self.controlPoints}_{self.boundaryCondition}"
        return hashlib.md5(config.encode()).hexdigest()

class ToneCurveDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name}設定")
        self.geometry("600x500")
        self.protocol("WM_DELETE_WINDOW", self.onClose)
        
        self.selectedPoint = None
        self.dragging = False
        self.dragStarted = False
        self.pressedPoint = None
        
        # プレビュー用 元の設定を保存
        self.originalSettings = {
            'displayMin': self.node.displayMin,
            'displayEnd': self.node.displayEnd,
            'outputMin': self.node.outputMin,
            'outputEnd': self.node.outputEnd,
            'controlPoints': self.node.controlPoints.copy(),
            'boundaryCondition': self.node.boundaryCondition,
        }
        
        # UI側でcontrolPointsの一時保存を管理
        self.tempControlPoints = self.node.controlPoints.copy()
        
        # ライブラリチェック
        import importlib.util
        if not importlib.util.find_spec("scipy"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ scipy がインストールされていません。\npip install scipy でインストールしてください。")
            return
        
        if not importlib.util.find_spec("matplotlib"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ matplotlib がインストールされていません。\npip install matplotlib でインストールしてください。")
            return
        
        self.createWidgets()
        self.updatePlot()
        
    def createWidgets(self):
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        # 表示範囲行
        displayFrame = tk.Frame(basicFrame)
        displayFrame.pack(fill=tk.X, pady=2)
        tk.Label(displayFrame, text="表示範囲:").pack(side=tk.LEFT, padx=(0,5))
        self.displayMinEntry = tk.Entry(displayFrame, width=10)
        self.displayMinEntry.insert(0, str(self.node.displayMin))
        self.displayMinEntry.pack(side=tk.LEFT, padx=(0,2))
        self.displayMinEntry.bind('<Return>', self.onRangeChange)
        tk.Label(displayFrame, text="～").pack(side=tk.LEFT, padx=2)
        self.displayEndEntry = tk.Entry(displayFrame, width=10)
        self.displayEndEntry.insert(0, str(self.node.displayEnd))
        self.displayEndEntry.pack(side=tk.LEFT, padx=(2,5))
        self.displayEndEntry.bind('<Return>', self.onRangeChange)
        tk.Button(displayFrame, text="入力元フィット", command=self.fitDisplayToInput).pack(side=tk.LEFT, padx=5)
        tk.Button(displayFrame, text="0.1-99.9%範囲", command=self.fitDisplayToPercentile).pack(side=tk.LEFT, padx=5)
        tk.Button(displayFrame, text="制御点フィット", command=self.fitDisplayToControlPoint).pack(side=tk.LEFT, padx=5)
        
        # 出力範囲行
        outputFrame = tk.Frame(basicFrame)
        outputFrame.pack(fill=tk.X, pady=2)
        tk.Label(outputFrame, text="出力範囲:").pack(side=tk.LEFT, padx=(0,5))
        self.outputMinEntry = tk.Entry(outputFrame, width=10)
        self.outputMinEntry.insert(0, str(self.node.outputMin))
        self.outputMinEntry.pack(side=tk.LEFT, padx=(0,2))
        self.outputMinEntry.bind('<Return>', self.onRangeChange)
        tk.Label(outputFrame, text="～").pack(side=tk.LEFT, padx=2)
        self.outputEndEntry = tk.Entry(outputFrame, width=10)
        self.outputEndEntry.insert(0, str(self.node.outputEnd))
        self.outputEndEntry.pack(side=tk.LEFT, padx=(2,5))
        self.outputEndEntry.bind('<Return>', self.onRangeChange)
        
        # トーンカーブ行
        curveFrame = tk.Frame(basicFrame)
        curveFrame.pack(fill=tk.X, pady=2)
        tk.Label(curveFrame, text="トーンカーブ:").pack(side=tk.LEFT, padx=(0,5))
        self.boundaryCombobox = ttk.Combobox(curveFrame, values=['natural', 'clamped', 'not-a-knot'], state="readonly", width=12)
        self.boundaryCombobox.set(self.node.boundaryCondition)
        self.boundaryCombobox.pack(side=tk.LEFT, padx=(0,5))
        self.boundaryCombobox.bind('<<ComboboxSelected>>', self.onBoundaryChange)
        tk.Button(curveFrame, text="表示範囲フィット", command=self.fitControlPointToDisplay).pack(side=tk.LEFT, padx=5)
        
        # ヒストグラムY軸行
        histYFrame = tk.Frame(basicFrame)
        histYFrame.pack(fill=tk.X, pady=2)
        tk.Label(histYFrame, text="ヒストグラムY軸:").pack(side=tk.LEFT, padx=(0,5))
        self.yScaleVar = tk.StringVar(value="log")
        tk.Radiobutton(histYFrame, text="Log", variable=self.yScaleVar, value="log", command=self.updatePlot).pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(histYFrame, text="Linear", variable=self.yScaleVar, value="linear", command=self.updatePlot).pack(side=tk.LEFT, padx=2)
        
        # グラフフレーム
        graphFrame = tk.Frame(self, height=250)
        graphFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        graphFrame.pack_propagate(False)
        
        self.figure = Figure(figsize=(6, 3))
        self.axes = self.figure.add_subplot(111)
        self.histAxes = self.axes.twinx()  # ヒストグラム用の別軸
        self.histAxes.set_zorder(0)  # ヒストグラムを背景に
        self.axes.set_zorder(1)  # メイン軸を前景に
        self.axes.set_facecolor('none')  # メイン軸の背景を透明に
        self.canvas = FigureCanvasTkAgg(self.figure, graphFrame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # イベントバインド
        self.canvas.mpl_connect('button_press_event', self.onPress)
        self.canvas.mpl_connect('button_release_event', self.onRelease)
        self.canvas.mpl_connect('motion_notify_event', self.onMotion)
        self.canvas.mpl_connect('scroll_event', self.onScroll)
        
        # 操作説明
        helpFrame = tk.Frame(self)
        helpFrame.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(helpFrame, text="操作: 左クリック=追加/削除, ドラッグ=移動, ホイール=ズーム",
                font=("Arial", 9), foreground="gray").pack(side=tk.LEFT)
        
        # ボタンフレーム
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        
        self.previewVariable = tk.BooleanVar(value=False)
        self.previewCheckbox = tk.Checkbutton(buttonFrame, text="プレビュー",
                                            variable=self.previewVariable,
                                            command=self.onPreviewToggle)
        self.previewCheckbox.pack(side=tk.LEFT, padx=5)
        
        tk.Button(buttonFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
    def updatePlot(self):
        self.axes.clear()
        
        # ヒストグラム表示（入力データがある場合のみ）
        if self.node.inputNodes and self.node.inputNodes[0].flowDatas:
            self.plotHistogram(self.node.inputNodes[0].flowDatas[0])
        
        # トーンカーブ表示
        self.plotToneCurve()
        
        # 制御点表示
        self.plotControlPoints()
        
        # 軸の範囲をUI入力値で設定
        try:
            displayMin = float(self.displayMinEntry.get())
            displayEnd = float(self.displayEndEntry.get())
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            
            self.axes.set_xlim(displayMin, displayEnd)
            self.axes.set_ylim(outputMin, outputEnd)
        except ValueError:
            # デフォルト値
            self.axes.set_xlim(0, 1)
            self.axes.set_ylim(0, 1)
        
        # トーンカーブ軸は常にlinear
        self.axes.set_xscale('linear')
        self.axes.set_yscale('linear')
        
        self.axes.set_xlabel('Input')
        self.axes.set_ylabel('Output')
        self.axes.grid(True, alpha=0.3)
        
        self.canvas.draw()
    
    def plotHistogram(self, flowData):
        from utils import numpy_helpers as nh

        # ヒストグラム軸をクリア
        self.histAxes.clear()
        
        # 軸スケール設定を取得
        yScale = self.yScaleVar.get()
        
        # flowData.getHistogramを使用してヒストグラムデータを取得
        histogramData = flowData.getHistogram()
        
        if histogramData and 'planes' in histogramData:
            # プレーン用の色を定義
            colors = ['red', 'green', 'blue', 'cyan', 'magenta', 'yellow']
            
            # Y軸スケールを設定
            if yScale == "log":
                self.histAxes.set_yscale('log')
            else:
                self.histAxes.set_yscale('linear')
            
            # UI入力値を取得
            try:
                displayMin = float(self.displayMinEntry.get())
                displayEnd = float(self.displayEndEntry.get())
            except ValueError:
                displayMin = self.node.displayMin
                displayEnd = self.node.displayEnd
            
            # 全プレーンのヒストグラムを重ねて表示
            for planeIndex, planeHist in enumerate(histogramData['planes']):
                binCounts = planeHist['bin_counts']
                binEdges = planeHist['bin_edges']
                
                # ビン中心を計算
                binCenters = (binEdges[:-1] + binEdges[1:]) / 2

                # 入力範囲内のビンのみをフィルタリング
                mask = (binCenters >= displayMin) & (binCenters <= displayEnd)
                filteredCenters = binCenters[mask]
                filteredCounts = nh.array(binCounts)[mask]

                if filteredCounts.any():
                    # Y軸がログスケールの場合は1を加算
                    if yScale == "log":
                        filteredCounts = nh.array(filteredCounts) + 1
                    
                    # プレーン別の色で表示
                    color = colors[planeIndex % len(colors)]
                    self.histAxes.plot(filteredCenters, filteredCounts, alpha=0.4, color=color, linewidth=1)

            self.histAxes.set_xlim(displayMin, displayEnd)
            
            # ログスケール時は下限のみ1に固定
            if yScale == "log":
                current_ylim = self.histAxes.get_ylim()
                self.histAxes.set_ylim(1, current_ylim[1])
            
            self.histAxes.tick_params(axis='y', labelleft=False)  # Y軸ラベルを非表示
    
    def plotToneCurve(self):
        import numpy as np
        from scipy.interpolate import interp1d, CubicSpline

        if 2 <= len(self.tempControlPoints):
            # UI入力値を取得
            displayMin = float(self.displayMinEntry.get())
            displayEnd = float(self.displayEndEntry.get())
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            boundaryCondition = self.boundaryCombobox.get()
            
            # 制御点をX座標でソート
            sortedPoints = sorted(self.tempControlPoints, key=lambda p: p[0])
            xValues = [p[0] for p in sortedPoints]
            yValues = [p[1] for p in sortedPoints]
            
            # 正規化された制御点で補間
            xNormalized = [(x - displayMin) / (displayEnd - displayMin) for x in xValues]
            
            if len(xNormalized) >= 2:
                # 制御点数に応じて補間方法を選択
                if len(xNormalized) < 3:
                    curveFunction = interp1d(xNormalized, yValues, kind='linear', bounds_error=False, fill_value='extrapolate')
                else:
                    # 選択された境界条件でスプライン
                    curveFunction = CubicSpline(xNormalized, yValues, bc_type=boundaryCondition, extrapolate=True)
                
                # 実際の値でカーブを描画
                xSmooth = np.linspace(displayMin, displayEnd, 256)
                xSmoothNormalized = (xSmooth - displayMin) / (displayEnd - displayMin)
                
                # 始点・終点の外側をクランプ
                startPoint = sortedPoints[0]
                endPoint = sortedPoints[-1]
                
                # 範囲外の処理
                mask_below = xSmooth < startPoint[0]
                mask_above = xSmooth > endPoint[0]
                mask_inside = ~(mask_below | mask_above)
                
                # 結果データを初期化
                ySmooth = np.zeros_like(xSmooth)
                
                # 範囲内のデータにトーンカーブを適用
                if np.any(mask_inside):
                    ySmooth[mask_inside] = curveFunction(xSmoothNormalized[mask_inside])
                
                # 範囲外のデータを始点・終点の値に設定
                if np.any(mask_below):
                    ySmooth[mask_below] = startPoint[1]
                if np.any(mask_above):
                    ySmooth[mask_above] = endPoint[1]
                
                # 出力を実際の値に変換
                ySmooth = ySmooth * (outputEnd - outputMin) + outputMin
                
                self.axes.plot(xSmooth, ySmooth, '-', linewidth=2, color='dimgray')
    
    def plotControlPoints(self):
        outputMin = float(self.outputMinEntry.get())
        outputEnd = float(self.outputEndEntry.get())
        
        for i, (x, y) in enumerate(self.tempControlPoints):
            # 実際の値で制御点を表示
            yActual = y * (outputEnd - outputMin) + outputMin
            
            color = 'red' if i in [0, len(self.tempControlPoints)-1] else 'dimgray'
            self.axes.plot(x, yActual, 'o', color=color, markersize=8)
    
    def findNearestPoint(self, x, y):
        """最も近い制御点を検索"""
        minimumDistance = float('inf')
        nearestPoint = None
        
        displayMin = float(self.displayMinEntry.get())
        displayEnd = float(self.displayEndEntry.get())
        outputMin = float(self.outputMinEntry.get())
        outputEnd = float(self.outputEndEntry.get())
        
        # 判定範囲を実際の値に合わせて調整
        thresholdX = (displayEnd - displayMin) * 0.03
        thresholdY = (outputEnd - outputMin) * 0.03
        
        for i, (pointX, pointY) in enumerate(self.tempControlPoints):
            pointYActual = pointY * (outputEnd - outputMin) + outputMin
            
            # X軸とY軸の距離を個別にチェック
            distanceX = abs(x - pointX)
            distanceY = abs(y - pointYActual)
            
            # 両方の軸で闾値以内の場合のみ候補とする
            if distanceX < thresholdX and distanceY < thresholdY:
                distance = (distanceX**2 + distanceY**2)**0.5
                if distance < minimumDistance:
                    minimumDistance = distance
                    nearestPoint = i
        
        return nearestPoint
    
    def onPress(self, event):
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        
        # 最も近い制御点を検索
        nearestIndex = self.findNearestPoint(event.xdata, event.ydata)
        
        # プレス時の状態を記録
        self.pressedPoint = nearestIndex
        self.dragStarted = False
        self.pressX = event.xdata
        self.pressY = event.ydata
        
        if nearestIndex is not None:
            # 制御点をプレス：ドラッグ準備
            self.selectedPoint = nearestIndex
            self.dragging = True
        else:
            # 空いている場所をプレス：即座に制御点を追加
            xActual = float(event.xdata)
            yActual = float(event.ydata)
            yNormalized = (yActual - float(self.outputMinEntry.get())) / (float(self.outputEndEntry.get()) - float(self.outputMinEntry.get()))
            yNormalized = max(0, min(1, yNormalized))
            newPoint = (xActual, yNormalized)
            
            # 挿入位置を決定
            insertPosition = len(self.tempControlPoints)
            for i, (pointX, pointY) in enumerate(self.tempControlPoints):
                if xActual < pointX:
                    insertPosition = i
                    break
            
            self.tempControlPoints.insert(insertPosition, newPoint)
            self.selectedPoint = insertPosition
            self.dragging = True
            self.updatePlot()
            self.triggerPreview()
    
    def onMotion(self, event):
        if not self.dragging or self.selectedPoint is None:
            return
        
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        
        # ドラッグ開始を記録
        self.dragStarted = True
        
        # 制御点を移動
        xActual = float(event.xdata)
        yActual = float(event.ydata)
        # Y値を正規化して保存
        yNormalized = (yActual - float(self.outputMinEntry.get())) / (float(self.outputEndEntry.get()) - float(self.outputMinEntry.get()))
        yNormalized = max(0, min(1, yNormalized))
        
        self.tempControlPoints[self.selectedPoint] = (xActual, yNormalized)
        self.updatePlot()  # ドラッグ中はグラフのみ更新
    
    def onRelease(self, event):
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            self.dragging = False
            self.selectedPoint = None
            self.pressedPoint = None
            self.dragStarted = False
            return
        
        if self.pressedPoint is not None:
            # 制御点をプレスしていた場合
            if self.dragStarted:
                # ドラッグした場合：移動完了
                self.triggerPreview()
            else:
                # ドラッグせずに離した場合：削除（始点・終点以外）
                if self.pressedPoint not in [0, len(self.tempControlPoints)-1]:
                    self.tempControlPoints.pop(self.pressedPoint)
                    self.updatePlot()
                    self.triggerPreview()
        
        self.dragging = False
        self.selectedPoint = None
        self.pressedPoint = None
        self.dragStarted = False
    
    def onScroll(self, event):
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        
        currentMin = float(self.displayMinEntry.get())
        currentEnd = float(self.displayEndEntry.get())
        currentRange = currentEnd - currentMin
        
        # ズーム倍率
        zoomFactor = 0.9 if event.step > 0 else 1.1
        newRange = currentRange * zoomFactor
        
        # マウス位置を中心にズーム
        mouseX = event.xdata
        centerRatio = (mouseX - currentMin) / currentRange
        
        newMin = mouseX - newRange * centerRatio
        newEnd = newMin + newRange
        
        # 最小範囲制限
        if newRange > 1e-10:
            self.displayMinEntry.delete(0, tk.END)
            self.displayMinEntry.insert(0, f"{newMin:.3f}")
            self.displayEndEntry.delete(0, tk.END)
            self.displayEndEntry.insert(0, f"{newEnd:.3f}")
            
            self.updatePlot()

    def onRangeChange(self, event=None):
        # 範囲の変更時
        self.updatePlot()
        self.triggerPreview()
    
    def onBoundaryChange(self, *args):
        # トーンカーブの変更時
        self.updatePlot()
        self.triggerPreview()
    
    def onPreviewToggle(self):
        # プレビューのトグル時
        from utils.ThreadPool import CoalescingExecutor

        if self.previewVariable.get():
            # プレビュー有効：一時保存値を適用
            self.restoreTemporarySettings()
        else:
            # プレビュー無効：確定値を適用して実行
            self.restoreConfirmedSettings()
        
        CoalescingExecutor.submit( self, self.node.preview)
    
    def restoreTemporarySettings(self):
        # 一時保存値をノードに適用
        self.node.displayMin = float(self.displayMinEntry.get())
        self.node.displayEnd = float(self.displayEndEntry.get())
        self.node.outputMin = float(self.outputMinEntry.get())
        self.node.outputEnd = float(self.outputEndEntry.get())
        self.node.controlPoints = self.tempControlPoints
        self.node.boundaryCondition = self.boundaryCombobox.get()
    
    def restoreConfirmedSettings(self):
        # 確定値をノードに適用
        if self.originalSettings:
            self.node.displayMin = self.originalSettings['displayMin']
            self.node.displayEnd = self.originalSettings['displayEnd']
            self.node.outputMin = self.originalSettings['outputMin']
            self.node.outputEnd = self.originalSettings['outputEnd']
            self.node.controlPoints = self.originalSettings['controlPoints']
            self.node.boundaryCondition = self.originalSettings['boundaryCondition']
    
    def triggerPreview(self):
        from utils.ThreadPool import CoalescingExecutor
        
        if self.previewVariable.get():
            # プレビュー有効：一時保存値を適用
            self.restoreTemporarySettings()
            CoalescingExecutor.submit( self, self.node.preview)
    
    def fitDisplayToInput(self):
        # 入力データから最大最小値を取得してUIに設定
        from utils.interval_helper import createHalfOpenEnd

        if self.node.inputNodes and self.node.inputNodes[0].flowDatas:
            
            flowData = self.node.inputNodes[0].flowDatas[0]
            minValue = flowData.getMinValue()
            maxValue = flowData.getMaxValue()
            
            if minValue is not None and maxValue is not None:
                endValue = createHalfOpenEnd(minValue, maxValue)
                
                self.displayMinEntry.delete(0, tk.END)
                self.displayMinEntry.insert(0, f"{minValue:.3f}")
                self.displayEndEntry.delete(0, tk.END)
                self.displayEndEntry.insert(0, f"{endValue:.3f}")
                
                self.updatePlot()
    
    def fitDisplayToPercentile(self):
        # パーセンタイル範囲（1%～99%）にズーム
        if self.node.inputNodes and self.node.inputNodes[0].flowDatas:
            
            flowData = self.node.inputNodes[0].flowDatas[0]
            histogramData = flowData.getHistogram(log_scale=False)
            
            if histogramData and 'planes' in histogramData:
                # 全プレーンのヒストグラムを統合してパーセンタイルを計算
                allBinCenters = []
                allCounts = []
                
                for planeHist in histogramData['planes']:
                    binCounts = planeHist['bin_counts']
                    binEdges = planeHist['bin_edges']
                    
                    # ビン中心を計算
                    binCenters = [(binEdges[i] + binEdges[i+1]) / 2 for i in range(len(binCounts))]
                    
                    for center, count in zip(binCenters, binCounts):
                        if count > 0:
                            allBinCenters.extend([center] * count)
                
                if allBinCenters:
                    # パーセンタイルを計算（0.1%と99.9%）
                    allBinCenters.sort()
                    totalPixels = len(allBinCenters)
                    
                    p001_index = int(totalPixels * 0.001)
                    p999_index = int(totalPixels * 0.999)
                    
                    p001_value = allBinCenters[p001_index]
                    p999_value = allBinCenters[p999_index]
                    
                    # 少し余裕を持たせる
                    margin = (p999_value - p001_value) * 0.1
                    zoomMin = p001_value - margin
                    zoomMax = p999_value + margin
                    
                    self.displayMinEntry.delete(0, tk.END)
                    self.displayMinEntry.insert(0, f"{zoomMin:.3f}")
                    self.displayEndEntry.delete(0, tk.END)
                    self.displayEndEntry.insert(0, f"{zoomMax:.3f}")
                    
                    self.updatePlot()
    
    def fitDisplayToControlPoint(self):
        # 制御点の範囲にズーム
        if self.tempControlPoints:
            # 最小値と最大値を取得
            pointMin = self.tempControlPoints[0][0]
            pointEnd = self.tempControlPoints[-1][0]

            # UIに設定
            self.displayMinEntry.delete(0, tk.END)
            self.displayMinEntry.insert(0, str(pointMin))
            self.displayEndEntry.delete(0, tk.END)
            self.displayEndEntry.insert(0, str(pointEnd))

            self.updatePlot()

    def fitControlPointToDisplay(self):
        displayMin = float(self.displayMinEntry.get())
        displayEnd = float(self.displayEndEntry.get())
        
        if displayMin < displayEnd:
            # 始点・終点を更新
            self.tempControlPoints[0] = (displayMin, 0.0)
            self.tempControlPoints[-1] = (displayEnd, 1.0)
            
            # 中間の制御点を範囲内に調整
            for i in range(1, len(self.tempControlPoints) - 1):
                x, y = self.tempControlPoints[i]
                x = max(displayMin, min(displayEnd, x))
                self.tempControlPoints[i] = (x, y)
            
            self.updatePlot()
            self.triggerPreview()
    
    def onApply(self):
        # 一時保存値を確定値とする
        displayMin = float(self.displayMinEntry.get())
        displayEnd = float(self.displayEndEntry.get())
        outputMin = float(self.outputMinEntry.get())
        outputEnd = float(self.outputEndEntry.get())
        boundaryCondition = self.boundaryCombobox.get()
        
        if displayMin < displayEnd and outputMin < outputEnd:
            # 確定値を更新
            self.node.applySettings(displayMin, displayEnd, outputMin, outputEnd, self.tempControlPoints, boundaryCondition)
            # 確定値を更新
            self.originalSettings = {
                'displayMin': displayMin,
                'displayEnd': displayEnd,
                'outputMin': outputMin,
                'outputEnd': outputEnd,
                'controlPoints': self.tempControlPoints.copy(),
                'boundaryCondition': boundaryCondition,
            }
    
    def onClose(self):
        from utils.ThreadPool import CoalescingExecutor
        
        # プレビュー表示を解除して閉じる
        if self.previewVariable.get():
            self.restoreConfirmedSettings()
            CoalescingExecutor.submit( self, self.node.preview)
        
        self.destroy()