'''
ToneCurveNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import hashlib

from base.NNBlockOperationNode import NNBlockOperationNode
from base.FlowData import FlowData
from utils.interval_helper import createHalfOpenEnd
from base.ConfigurableNode import ConfigurableNode

# scipyのインポートチェック
try:
    from scipy.interpolate import interp1d, CubicSpline
    scipyAvailable = True
except ImportError:
    scipyAvailable = False

# matplotlibのインポートチェック
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    matplotlibAvailable = True
except ImportError:
    matplotlibAvailable = False

class ToneCurveNode(NNBlockOperationNode,ConfigurableNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "tone_curve", "トーンカーブ")

        # デフォルト設定 - 半開区間 [0.0, 1.0) で正規化範囲
        self.inputMin = 0.0
        self.inputEnd = 1.0
        self.outputMin = 0.0
        self.outputEnd = 1.0
        self.controlPoints = [(0.0, 0.0), (1.0, 1.0)]  # (入力, 出力)
        self.boundaryCondition = 'natural'  # 境界条件
        
        # ライブラリチェック
        if not scipyAvailable:
            messagebox.showerror(f"{self.text} エラー", "scipyライブラリがインストールされていません。\npip install scipy でインストールしてください。")
            return
        
        if not matplotlibAvailable:
            messagebox.showerror(f"{self.text} エラー", "matplotlibライブラリがインストールされていません。\npip install matplotlib でインストールしてください。")
            return
        
        self.lastConfigHash = None
        self.updateNodeText()
    
    def getColor(self):
        return self._color_func
    
    def updateNodeText(self):
        displayText = f"{self.text}\n{len(self.controlPoints)-2}点\n出力[{self.outputMin:.2f}, {self.outputEnd:.2f})"
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        nodeData["inputMin"] = self.inputMin
        nodeData["inputEnd"] = self.inputEnd
        nodeData["outputMin"] = self.outputMin
        nodeData["outputEnd"] = self.outputEnd
        nodeData["controlPoints"] = self.controlPoints
        nodeData["boundaryCondition"] = self.boundaryCondition
    
    def restore(self, nodeData):
        if "inputMin" in nodeData:
            self.inputMin = nodeData["inputMin"]
        if "inputEnd" in nodeData:
            self.inputEnd = nodeData["inputEnd"]
        if "outputMin" in nodeData:
            self.outputMin = nodeData["outputMin"]
        if "outputEnd" in nodeData:
            self.outputEnd = nodeData["outputEnd"]
        if "controlPoints" in nodeData:
            self.controlPoints = nodeData["controlPoints"]
        if "boundaryCondition" in nodeData:
            self.boundaryCondition = nodeData["boundaryCondition"]
        self.updateNodeText()
    
    def onEdit(self):
        return ToneCurveDialog( self.editor.root, self)
        
    def processBlock(self, block):
        if block is None:
            return None
        
        # DataBlockから実際のデータを取得
        data = np.array(block.data, dtype=np.float64)
        
        # NaN値を事前に検出・分離
        nan_mask = np.isnan(data)
        if np.all(nan_mask):
            # 全てNaNの場合はそのまま返す
            from base.DataBlock import DataBlock
            return DataBlock(block.planeIndex, block.x, block.y, data.tolist())
        
        # トーンカーブ関数を作成
        sortedPoints = sorted(self.controlPoints, key=lambda p: p[0])
        xValues = [p[0] for p in sortedPoints]
        yValues = [p[1] for p in sortedPoints]
        
        # 入力範囲を正規化範囲にマッピング
        normalizedX = [(x - self.inputMin) / (self.inputEnd - self.inputMin) for x in xValues]
        
        # 制御点数に応じて補間方法を選択
        if len(normalizedX) < 3:
            curveFunction = interp1d(normalizedX, yValues, kind='linear', 
                                bounds_error=False, fill_value='extrapolate')
        else:
            # 選択された境界条件でスプライン
            curveFunction = CubicSpline(normalizedX, yValues, bc_type=self.boundaryCondition, extrapolate=True)
        
        # 結果データを初期化（NaN値を保持）
        resultData = data.copy()
        
        # 有効値（NaN以外）のみ処理
        valid_mask = ~nan_mask
        if np.any(valid_mask):
            valid_data = data[valid_mask]
            
            # 入力範囲 [inputMin, inputEnd) を [0.0, 1.0) に正規化
            normalizedData = (valid_data - self.inputMin) / (self.inputEnd - self.inputMin)
            
            # 始点・終点の外側をクランプ
            startPoint = sortedPoints[0]
            endPoint = sortedPoints[-1]
            
            # 範囲外の処理
            mask_below = valid_data < startPoint[0]
            mask_above = valid_data > endPoint[0]
            mask_inside = ~(mask_below | mask_above)
            
            # 結果データを初期化
            adjustedData = np.zeros_like(normalizedData)
            
            # 範囲内のデータにトーンカーブを適用
            if np.any(mask_inside):
                adjustedData[mask_inside] = curveFunction(normalizedData[mask_inside])
            
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
            resultData[valid_mask] = processedData
        
        # 新しいDataBlockを作成して返す
        from base.DataBlock import DataBlock
        return DataBlock(block.planeIndex, block.x, block.y, resultData.tolist())
    
    def applySettings(self, inputMin, inputEnd, outputMin, outputEnd, controlPoints, boundaryCondition):
        self.inputMin = inputMin
        self.inputEnd = inputEnd
        self.outputMin = outputMin
        self.outputEnd = outputEnd
        self.controlPoints = controlPoints
        self.boundaryCondition = boundaryCondition
        self.updateNodeText()
        
        newHash = self.getConfigHash()
        if newHash != self.lastConfigHash:
            self.lastConfigHash = newHash
            self.editor.onNodeConfigChanged(self)
    
    def setupDisplayLevels(self, outputFlowData, inputFlowData):
        """出力のdisplay_levelsを設定"""
        outputFlowData.headers['display_levels'] = {
            'min': self.outputMin,
            'exclusive_upper': self.outputEnd
        }
    
    def getConfigHash(self):
        config = f"{self.inputMin}_{self.inputEnd}_{self.outputMin}_{self.outputEnd}_{self.controlPoints}_{self.boundaryCondition}"
        return hashlib.md5(config.encode()).hexdigest()

class ToneCurveDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.text}設定")
        self.geometry("600x500")
        self.protocol("WM_DELETE_WINDOW", self.onClose)
        
        # ライブラリチェック
        if not scipyAvailable:
            messagebox.showerror(f"{node.text} エラー", "scipyライブラリがインストールされていません。\npip install scipy でインストールしてください。")
            self.destroy()
            return
        
        if not matplotlibAvailable:
            messagebox.showerror(f"{node.text} エラー", "matplotlibライブラリがインストールされていません。\npip install matplotlib でインストールしてください。")
            self.destroy()
            return
        
        self.selectedPoint = None
        self.dragging = False
        self.dragStarted = False
        self.pressedPoint = None
        
        # プレビュー用 元の設定を保存
        self.originalSettings = {
            'inputMin': self.node.inputMin,
            'inputEnd': self.node.inputEnd,
            'outputMin': self.node.outputMin,
            'outputEnd': self.node.outputEnd,
            'controlPoints': self.node.controlPoints.copy(),
            'boundaryCondition': self.node.boundaryCondition,
        }
        
        # UI側でcontrolPointsの一時保存を管理
        self.tempControlPoints = self.node.controlPoints.copy()
        
        self.createWidgets()
        self.updatePlot()
        
    def createWidgets(self):
        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        # 入力範囲行
        inputFrame = tk.Frame(basicFrame)
        inputFrame.pack(fill=tk.X, pady=2)
        tk.Label(inputFrame, text="入力範囲:").pack(side=tk.LEFT, padx=(0,5))
        self.minEntry = tk.Entry(inputFrame, width=10)
        self.minEntry.insert(0, str(self.node.inputMin))
        self.minEntry.pack(side=tk.LEFT, padx=(0,2))
        self.minEntry.bind('<Return>', self.onRangeChange)
        tk.Label(inputFrame, text="～").pack(side=tk.LEFT, padx=2)
        self.endEntry = tk.Entry(inputFrame, width=10)
        self.endEntry.insert(0, str(self.node.inputEnd))
        self.endEntry.pack(side=tk.LEFT, padx=(2,5))
        self.endEntry.bind('<Return>', self.onRangeChange)
        tk.Button(inputFrame, text="入力元フィット", command=self.fitInputRange).pack(side=tk.LEFT, padx=5)
        
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
        tk.Button(curveFrame, text="制御点フィット", command=self.fitControlPoint).pack(side=tk.LEFT, padx=5)
        tk.Button(curveFrame, text="0.1-99.9%範囲", command=self.zoomToHistogram).pack(side=tk.LEFT, padx=5)
        
        # ヒストグラムY軸行
        histYFrame = tk.Frame(basicFrame)
        histYFrame.pack(fill=tk.X, pady=2)
        tk.Label(histYFrame, text="ヒストグラムY軸:").pack(side=tk.LEFT, padx=(0,5))
        self.yScaleMode = "log"  # デフォルトはlog
        self.yScaleVar = tk.StringVar(value="log")
        self.yScaleLog = tk.Radiobutton(histYFrame, text="Log", variable=self.yScaleVar, value="log", command=lambda: self.setYScale("log"))
        self.yScaleLinear = tk.Radiobutton(histYFrame, text="Linear", variable=self.yScaleVar, value="linear", command=lambda: self.setYScale("linear"))
        self.yScaleLog.pack(side=tk.LEFT, padx=2)
        self.yScaleLinear.pack(side=tk.LEFT, padx=2)
        
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
        
    def setYScale(self, mode):
        self.yScaleMode = mode
        self.updatePlot()
    
    def updatePlot(self):
        self.axes.clear()
        
        # 入力データの有無をチェック
        hasInputData = (hasattr(self.node, 'inputNodes') and self.node.inputNodes and 
                       hasattr(self.node.inputNodes[0], 'flowDatas') and self.node.inputNodes[0].flowDatas)
        
        # ヒストグラム表示（入力データがある場合のみ）
        if hasInputData:
            self.plotHistogram(self.node.inputNodes[0].flowDatas[0])
        
        # トーンカーブ表示（常に表示）
        self.plotToneCurve()
        
        # 制御点表示（常に表示）
        self.plotControlPoints()
        
        # 軸の範囲をUI入力値で設定
        try:
            inputMin = float(self.minEntry.get())
            inputEnd = float(self.endEntry.get())
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            
            self.axes.set_xlim(inputMin, inputEnd)
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
        # ヒストグラム軸をクリア
        self.histAxes.clear()
        
        # 軸スケール設定を取得
        yScale = self.yScaleMode
        
        # flowData.getHistogramを使用してヒストグラムデータを取得
        histogramData = flowData.getHistogram(log_scale=False)
        
        if histogramData and 'planes' in histogramData:
            # プレーン用の色を定義
            colors = ['red', 'green', 'blue', 'cyan', 'magenta', 'yellow']
            
            # Y軸スケールを設定
            if yScale == "log":
                self.histAxes.set_yscale('log')
            else:
                self.histAxes.set_yscale('linear')
            
            # 全プレーンのヒストグラムを重ねて表示
            for planeIdx, planeHist in enumerate(histogramData['planes']):
                binCounts = planeHist['counts']
                binEdges = planeHist['bin_edges']
                
                # ビン中心を計算
                binCenters = [(binEdges[i] + binEdges[i+1]) / 2 for i in range(len(binCounts))]
                
                # UI入力値を取得
                try:
                    inputMin = float(self.minEntry.get())
                    inputEnd = float(self.endEntry.get())
                except ValueError:
                    inputMin = self.node.inputMin
                    inputEnd = self.node.inputEnd
                
                # 入力範囲内のビンのみをフィルタリング
                filteredCenters = []
                filteredCounts = []
                for i, center in enumerate(binCenters):
                    if inputMin <= center <= inputEnd:
                        filteredCenters.append(center)
                        filteredCounts.append(binCounts[i])
                
                if filteredCounts:
                    # Y軸がログスケールの場合は1を加算
                    if yScale == "log":
                        filteredCounts = np.array(filteredCounts) + 1
                    
                    # プレーン別の色で表示
                    color = colors[planeIdx % len(colors)]
                    self.histAxes.step(filteredCenters, filteredCounts, where='mid', 
                                     alpha=0.4, color=color, linewidth=1)
            
            self.histAxes.set_xlim(inputMin, inputEnd)
            
            # ログスケール時は下限のみ1に固定
            if yScale == "log":
                current_ylim = self.histAxes.get_ylim()
                self.histAxes.set_ylim(1, current_ylim[1])
            
            self.histAxes.tick_params(axis='y', labelleft=False)  # Y軸ラベルを非表示
    
    def plotToneCurve(self):
        if len(self.tempControlPoints) >= 2:
            try:
                # UI入力値を取得
                inputMin = float(self.minEntry.get())
                inputEnd = float(self.endEntry.get())
                outputMin = float(self.outputMinEntry.get())
                outputEnd = float(self.outputEndEntry.get())
                boundaryCondition = self.boundaryCombobox.get()
                
                # 制御点をX座標でソート
                sortedPoints = sorted(self.tempControlPoints, key=lambda p: p[0])
                xValues = [p[0] for p in sortedPoints]
                yValues = [p[1] for p in sortedPoints]
                
                # 正規化された制御点で補間
                xNormalized = [(x - inputMin) / (inputEnd - inputMin) for x in xValues]
                
                if len(xNormalized) >= 2:
                    # 制御点数に応じて補間方法を選択
                    if len(xNormalized) < 3:
                        curveFunction = interp1d(xNormalized, yValues, kind='linear', 
                                            bounds_error=False, fill_value='extrapolate')
                    else:
                        # 選択された境界条件でスプライン
                        curveFunction = CubicSpline(xNormalized, yValues, bc_type=boundaryCondition, extrapolate=True)
                    
                    # 実際の値でカーブを描画
                    xSmooth = np.linspace(inputMin, inputEnd, 256)
                    xSmoothNormalized = (xSmooth - inputMin) / (inputEnd - inputMin)
                    
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
            except ValueError:
                pass
    
    def plotControlPoints(self):
        try:
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            
            for i, (x, y) in enumerate(self.tempControlPoints):
                # 実際の値で制御点を表示
                yActual = y * (outputEnd - outputMin) + outputMin
                
                color = 'red' if i in [0, len(self.tempControlPoints)-1] else 'dimgray'
                self.axes.plot(x, yActual, 'o', color=color, markersize=8)
        except ValueError:
            pass
    
    def findNearestPoint(self, x, y):
        """最も近い制御点を検索"""
        minimumDistance = float('inf')
        nearestPoint = None
        
        try:
            inputMin = float(self.minEntry.get())
            inputEnd = float(self.endEntry.get())
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            
            # 判定範囲を実際の値に合わせて調整
            thresholdX = (inputEnd - inputMin) * 0.03
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
        except ValueError:
            pass
        
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
            yNormalized = (yActual - self.node.outputMin) / (self.node.outputEnd - self.node.outputMin)
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
        yNormalized = (yActual - self.node.outputMin) / (self.node.outputEnd - self.node.outputMin)
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
        
        try:
            currentMin = float(self.minEntry.get())
            currentEnd = float(self.endEntry.get())
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
                self.minEntry.delete(0, tk.END)
                self.minEntry.insert(0, f"{newMin:.8f}")
                self.endEntry.delete(0, tk.END)
                self.endEntry.insert(0, f"{newEnd:.8f}")
                
                self.updatePlot()
        except ValueError:
            pass
    

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
        if self.previewVariable.get():
            # プレビュー有効：一時保存値を適用
            self.restoreTemporarySettings()
        else:
            # プレビュー無効：確定値を適用して実行
            self.restoreConfirmedSettings()
        
        threading.Thread(target=self.node.processPreviewOnly, daemon=True).start()
    
    def restoreTemporarySettings(self):
        # 一時保存値をノードに適用
        try:
            self.node.inputMin = float(self.minEntry.get())
            self.node.inputEnd = float(self.endEntry.get())
            self.node.outputMin = float(self.outputMinEntry.get())
            self.node.outputEnd = float(self.outputEndEntry.get())
            self.node.controlPoints = self.tempControlPoints
            self.node.boundaryCondition = self.boundaryCombobox.get()
        except ValueError:
            pass
    
    def restoreConfirmedSettings(self):
        # 確定値をノードに適用
        if self.originalSettings:
            self.node.inputMin = self.originalSettings['inputMin']
            self.node.inputEnd = self.originalSettings['inputEnd'] 
            self.node.outputMin = self.originalSettings['outputMin']
            self.node.outputEnd = self.originalSettings['outputEnd'] 
            self.node.controlPoints = self.originalSettings['controlPoints'] 
            self.node.boundaryCondition = self.originalSettings['boundaryCondition']
    
    def triggerPreview(self):
        if self.previewVariable.get():
            # プレビュー有効：一時保存値を適用
            self.restoreTemporarySettings()
            threading.Thread(target=self.node.processPreviewOnly, daemon=True).start()
    
    def fitInputRange(self):
        # 入力データから最大最小値を取得してUIに設定
        if (hasattr(self.node, 'inputNodes') and self.node.inputNodes and 
            hasattr(self.node.inputNodes[0], 'flowDatas') and self.node.inputNodes[0].flowDatas):
            
            flowData = self.node.inputNodes[0].flowDatas[0]
            minValue = flowData.getMinValue()
            maxValue = flowData.getMaxValue()
            
            if minValue is not None and maxValue is not None:
                inputEnd = createHalfOpenEnd(minValue, maxValue)
                
                self.minEntry.delete(0, tk.END)
                self.minEntry.insert(0, str(minValue))
                self.endEntry.delete(0, tk.END)
                self.endEntry.insert(0, str(inputEnd))
                
                self.updatePlot()
    
    def zoomToHistogram(self):
        # ヒストグラムのパーセンタイル範囲（1%～99%）にズーム
        if (hasattr(self.node, 'inputNodes') and self.node.inputNodes and 
            hasattr(self.node.inputNodes[0], 'flowDatas') and self.node.inputNodes[0].flowDatas):
            
            flowData = self.node.inputNodes[0].flowDatas[0]
            histogramData = flowData.getHistogram(log_scale=False)
            
            if histogramData and 'planes' in histogramData:
                # 全プレーンのヒストグラムを統合してパーセンタイルを計算
                allBinCenters = []
                allCounts = []
                
                for planeHist in histogramData['planes']:
                    binCounts = planeHist['counts']
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
                    
                    self.minEntry.delete(0, tk.END)
                    self.minEntry.insert(0, f"{zoomMin:.6f}")
                    self.endEntry.delete(0, tk.END)
                    self.endEntry.insert(0, f"{zoomMax:.6f}")
                    
                    self.updatePlot()
    
    def fitControlPoint(self):
        try:
            inputMin = float(self.minEntry.get())
            inputEnd = float(self.endEntry.get())
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            
            if inputMin < inputEnd and outputMin < outputEnd:
                # 始点・終点を更新
                self.tempControlPoints[0] = (inputMin, 0.0)
                self.tempControlPoints[-1] = (inputEnd, 1.0)
                
                # 中間の制御点を範囲内に調整
                for i in range(1, len(self.tempControlPoints) - 1):
                    x, y = self.tempControlPoints[i]
                    x = max(inputMin, min(inputEnd, x))
                    self.tempControlPoints[i] = (x, y)
                
                self.updatePlot()
                self.triggerPreview()
        except ValueError:
            pass
    
    def onApply(self):
        # 一時保存値を確定値とする
        try:
            inputMin = float(self.minEntry.get())
            inputEnd = float(self.endEntry.get())
            outputMin = float(self.outputMinEntry.get())
            outputEnd = float(self.outputEndEntry.get())
            boundaryCondition = self.boundaryCombobox.get()
            
            if inputMin < inputEnd and outputMin < outputEnd:
                # 確定値を更新
                self.node.applySettings(inputMin, inputEnd, outputMin, outputEnd, self.tempControlPoints, boundaryCondition)
                # 確定値を更新
                self.originalSettings = {
                    'inputMin': inputMin,
                    'inputEnd': inputEnd,
                    'outputMin': outputMin,
                    'outputEnd': outputEnd,
                    'controlPoints': self.tempControlPoints.copy(),
                    'boundaryCondition': boundaryCondition,
                }
        except ValueError:
            pass
    
    def onClose(self):
        # プレビュー表示を解除して閉じる
        if self.previewVariable.get():
            self.restoreConfirmedSettings()
            threading.Thread(target=self.node.processPreviewOnly, daemon=True).start()
        
        self.destroy()