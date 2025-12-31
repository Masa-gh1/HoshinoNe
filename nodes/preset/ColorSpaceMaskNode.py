'''
ColorSpaceMaskNode - 色空間マスクノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, ConfigurableNode

class ColorSpaceMaskNode(LazyNNOperationNode, ConfigurableNode):
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'colorspace_mask'
    name = '色空間マスク'

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        from utils import numpy_helpers as nh
        
        self.colorSpace = "RGB"
        # 回転行列で管理（ジンバルロック回避）
        self.rotationMatrix = nh.eye(3)
        self.selectionPoints3d = []
        self.selectedPointIndex = None
    
    def getText(self):
        pointCount = len(self.selectionPoints3d)
        return f"{self.name}\n{self.colorSpace}空間\n{pointCount}点選択"
    
    def store(self, nodeData):
        nodeData["color_space"] = self.colorSpace
        nodeData["rotation_matrix"] = self.rotationMatrix.tolist()
        nodeData["selection_points_3d"] = self.selectionPoints3d
        nodeData["selected_point_index"] = self.selectedPointIndex
    
    def restore(self, nodeData):
        from utils import numpy_helpers as nh
        
        self.colorSpace = nodeData.get("color_space", "RGB")
        matrixData = nodeData.get("rotation_matrix", nh.eye(3).tolist())
        self.rotationMatrix = nh.array(matrixData)
        self.selectionPoints3d = nodeData.get("selection_points_3d", [])
        self.selectedPointIndex = nodeData.get("selected_point_index", None)
    
    def createSettingWindow(self):
        return ColorSpaceMaskDialog(self.view.editor.root, self)
    
    def applySettings(self, colorSpace, rotationMatrix, selectionPoints3d, selectedPointIndex):
        self.colorSpace = colorSpace
        self.rotationMatrix = rotationMatrix
        self.selectionPoints3d = selectionPoints3d
        self.selectedPointIndex = selectedPointIndex
        self.view.onNodeConfigChanged(self)
    
    def createLazyFlowData(self, inputData):
        return ColorSpaceMaskLazyFlowData(inputData, self.colorSpace, self.selectionPoints3d)
    
    def getConfigHash(self):
        import numpy as np
        
        matrixStr = np.array2string(self.rotationMatrix, precision=6)
        config = f"{self.colorSpace}_{matrixStr}_{self.selectionPoints3d}"
        return hashlib.sha256(config.encode()).hexdigest()

class ColorSpaceMaskLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y, colorSpace, selectionPoints3d):
        from base import DataBlock
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        
        if 0 != planeIndex:
            return None
        
        # マスク点がない場合は全て通す (1.0)
        if not selectionPoints3d:
            maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
            return DataBlock(maskData, planeIndex, x, y)
        
        # RGB プレーンを同時取得
        rBlock = flowData.getBlock(0, x, y)  # R
        gBlock = flowData.getBlock(1, x, y)  # G
        bBlock = flowData.getBlock(2, x, y)  # B
        
        if rBlock is None or gBlock is None or bBlock is None:
            # いずれかのプレーンがない場合は全て通す
            maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
            return DataBlock(maskData, planeIndex, x, y)
        
        # マスク生成
        height, width = rBlock.data.shape[:2]
        mask          = nh.ones((height, width))  # 初期値は 1.0 (全て通す)
        
        for yPos in range(height):
            for xPos in range(width):
                # RGB 値を取得
                R       = rBlock.data[yPos, xPos]
                G       = gBlock.data[yPos, xPos] 
                B       = bBlock.data[yPos, xPos]
                pixelRGB = nh.array([R, G, B])
                
                # 色空間変換
                if "RGB" == colorSpace:
                    pixelColor = pixelRGB
                else:  # Lab
                    pixelColor = self.rgbToLab(pixelRGB)
                
                # 各マスク点との距離を計算してマスク値を決定 (減算)
                maskReduction = self.calculateMaskReduction(pixelColor, selectionPoints3d)
                mask[yPos, xPos] = max(0.0, mask[yPos, xPos] - maskReduction)
        
        return DataBlock(mask, planeIndex, x, y)
    
    def rgbToLab(self, rgb):
        """RGB → Lab シンプル変換 (LabConverterNode と同じ)"""
        from utils import numpy_helpers as nh
        import numpy as np
        # 正規化 [0,1]
        rgb = np.clip(rgb, 0, 1)
        
        R, G, B = rgb[0], rgb[1], rgb[2]
        
        # Lab 変換 (正規化なし)
        L = (R + G + B) / 3.0
        a = R - L
        b = B - L
        
        return nh.array([L, a, b])
    
    def calculateMaskReduction(self, pixelColor, selectionPoints3d):
        """ピクセル色に対するマスク減算値を計算 (加算のみ)"""
        from utils import numpy_helpers as nh
        import numpy as np
        totalReduction = 0.0
        
        for x, y, z, radius, feather in selectionPoints3d:
            maskCenter = nh.array([x, y, z])
            
            # 3D 距離を計算
            distance = np.linalg.norm(pixelColor - maskCenter)
            
            # ガウシアンフォールオフでマスク値を計算
            if distance <= radius * feather:
                # ガウシアン関数: exp(-(distance/sigma)^2)
                sigma     = radius / 3.0  # 半径の 1/3 をシグマとする
                maskValue = np.exp(-(distance / sigma) ** 2)
                
                # 加算のみ (負の数として加算 = 減算)
                totalReduction += maskValue
        
        return totalReduction
    
    def getLazyHeaderkeys(self):
        return ['category', 'type', 'mode', 'planes', 'display_levels']
    
    def headerOperation(self, lazyFlowData, key, *args, **kwargs):
        return {
            'category': 'auxiliary',
            'type': 'image',
            'mode': 'L',
            'planes': ['Mask'],
            'display_levels': {'min': 0.0, 'exclusive_upper': 1.0}
        }

class ColorSpaceMaskDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name}設定")
        self.geometry("500x600")
        
        # 元の設定を保存
        self.originalSettings = {
            'colorSpace'        : self.node.colorSpace,
            'rotationMatrix'    : self.node.rotationMatrix.copy(),
            'selectionPoints3d' : self.node.selectionPoints3d.copy(),
            'selectedPointIndex': self.node.selectedPointIndex,
        }
        
        # 一時的な設定
        self.tempColorSpace         = self.node.colorSpace
        self.tempRotationMatrix     = self.node.rotationMatrix.copy()
        self.tempSelectionPoints3d  = self.node.selectionPoints3d.copy()
        self.tempSelectedPointIndex = self.node.selectedPointIndex
        
        self.createWidgets()
        self.updateMaskList()
        self.after(100, self.updateDisplay)
        
        # ウィンドウが閉じられたときのクリーンアップ
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def createWidgets(self):
        # 色空間選択
        frame1 = tk.Frame(self)
        frame1.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(frame1, text="色空間:").pack(side=tk.LEFT)
        self.colorSpaceVar = tk.StringVar(value=self.node.colorSpace)
        combo = ttk.Combobox(frame1, textvariable=self.colorSpaceVar, 
                            values=["RGB", "Lab"], state="readonly", width=10)
        combo.pack(side=tk.LEFT, padx=5)
        combo.bind('<<ComboboxSelected>>', self.onColorSpaceChange)
        
        # キャンバス
        self.canvas = ColorSpaceCanvas(self, width=400, height=400)
        self.canvas.pack(padx=10, pady=10)
        
        # マスク色リスト
        frameList = tk.Frame(self)
        frameList.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(frameList, text="マスク色リスト:").pack(anchor=tk.W)
        
        # Treeview作成
        columns = ("index", "x", "y", "z", "radius", "feather")
        self.maskList = ttk.Treeview(frameList, columns=columns, show="headings", height=6)
        
        # 列設定
        self.maskList.heading("index", text="#")
        self.maskList.heading("x", text="X")
        self.maskList.heading("y", text="Y")
        self.maskList.heading("z", text="Z")
        self.maskList.heading("radius", text="半径")
        self.maskList.heading("feather", text="ぼかし")
        
        self.maskList.column("index", width=30)
        self.maskList.column("x", width=60)
        self.maskList.column("y", width=60)
        self.maskList.column("z", width=60)
        self.maskList.column("radius", width=50)
        self.maskList.column("feather", width=50)
        
        self.maskList.pack(fill=tk.BOTH, expand=True)
        self.maskList.bind("<<TreeviewSelect>>", self.onMaskColorSelect)
        self.maskList.bind("<Double-1>", self.onCellEdit)
        
        # 削除ボタンを廃止
        # frameButtons = tk.Frame(frameList)
        # frameButtons.pack(fill=tk.X, pady=5)
        # 
        # tk.Button(frameButtons, text="削除", command=self.onDelete).pack(side=tk.LEFT, padx=5)
        # tk.Button(frameButtons, text="全削除", command=self.onDeleteAll).pack(side=tk.LEFT, padx=5)
        
        # 情報表示
        frame2 = tk.Frame(self)
        frame2.pack(fill=tk.X, padx=10, pady=5)
        
        self.infoLabel = tk.Label(frame2, text="回転: X=0° Y=0°", fg="gray")
        self.infoLabel.pack()
        
        # ボタン
        frame3 = tk.Frame(self)
        frame3.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(frame3, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(frame3, text="リセット", command=self.onReset).pack(side=tk.LEFT, padx=5)
        tk.Button(frame3, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
    
    def onColorSpaceChange(self, event=None):
        self.tempColorSpace = self.colorSpaceVar.get()
        self.updateMaskList()  # 列ヘッダーを更新
        self.updateDisplay()
    
    def onReset(self):
        from utils import numpy_helpers as nh
        
        self.tempRotationMatrix = nh.eye(3)
        self.tempSelectionPoints3d = []
        self.tempSelectedPointIndex = None
        self.updateDisplay()
        self.updateMaskList()
    
    def updateDisplay(self):
        self.canvas.updateDisplay()
        self.updateInfo()
    
    def updateMaskList(self):
        # リストをクリア
        for item in self.maskList.get_children():
            self.maskList.delete(item)
        
        # 列ヘッダーを色空間に応じて更新
        if "RGB" == self.tempColorSpace:
            self.maskList.heading("x", text="R")
            self.maskList.heading("y", text="G")
            self.maskList.heading("z", text="B")
        else:  # Lab
            self.maskList.heading("x", text="L")
            self.maskList.heading("y", text="a")
            self.maskList.heading("z", text="b")
        
        # 選択点を追加
        for i, (x, y, z, radius, feather) in enumerate(self.tempSelectionPoints3d):
            self.maskList.insert("", "end", iid=str(i), values=(
                i, f"{x:.3f}", f"{y:.3f}", f"{z:.3f}", f"{radius:.3f}", f"{feather:.1f}"
            ))
        
        # 選択状態を復元
        if (self.tempSelectedPointIndex is not None 
        and self.tempSelectedPointIndex < len(self.tempSelectionPoints3d)):
            self.maskList.selection_set(str(self.tempSelectedPointIndex))
    
    def onMaskColorSelect(self, event=None):
        selection = self.maskList.selection()
        if selection:
            selectedIndex = int(selection[0])
            self.tempSelectedPointIndex = selectedIndex
        else:
            self.tempSelectedPointIndex = None
        self.canvas.updateDisplay()
    
    def onDelete(self):
        if (self.node.selected_point_index is not None 
        and self.node.selected_point_index < len(self.node.selection_points_3d)):
            
            del self.node.selection_points_3d[self.node.selected_point_index]
            self.node.selected_point_index = None
            self.updateMaskList()
            self.canvas.updateDisplay()
    
    def onDeleteAll(self):
        self.node.selection_points_3d.clear()
        self.node.selected_point_index = None
        self.updateMaskList()
        self.canvas.updateDisplay()
    
    def updateInfo(self):
        from utils import numpy_helpers as nh
        import numpy as np
        
        # 回転行列からオイラー角を近似的に計算
        matrix = self.tempRotationMatrix
        # Y 軸回転角を計算
        rotationY = np.degrees(np.arctan2(matrix[0, 2], matrix[2, 2]))
        # X 軸回転角を計算
        rotationX = np.degrees(np.arcsin(-matrix[1, 2]))
        
        text = f"回転: X={rotationX:.0f}° Y={rotationY:.0f}°"
        self.infoLabel.config(text=text)
    
    def onApply(self):
        # 一時的な設定を確定
        self.node.applySettings(
            self.tempColorSpace,
            self.tempRotationMatrix,
            self.tempSelectionPoints3d,
            self.tempSelectedPointIndex
        )
        
        # 確定値を更新
        self.originalSettings = {
            'colorSpace'        : self.tempColorSpace,
            'rotationMatrix'    : self.tempRotationMatrix.copy(),
            'selectionPoints3d' : self.tempSelectionPoints3d.copy(),
            'selectedPointIndex': self.tempSelectedPointIndex,
        }
    
    def onClose(self):
        # 元の設定に戻す
        self.node.colorSpace = self.originalSettings['colorSpace']
        self.node.rotationMatrix = self.originalSettings['rotationMatrix']
        self.node.selectionPoints3d = self.originalSettings['selectionPoints3d']
        self.node.selectedPointIndex = self.originalSettings['selectedPointIndex']
        
        self.destroy()
    
    def onCellEdit(self, event):
        """セル編集開始"""
        item = self.maskList.selection()[0] if self.maskList.selection() else None
        if not item:
            return
        
        column = self.maskList.identify_column(event.x)
        
        # 半径とぼかし列のみ編集可能
        if column in ["#5", "#6"]:  # radius, feather
            self.startCellEdit(item, column, event.x, event.y)
    
    def startCellEdit(self, item, column, x, y):
        """セル編集ウィジェットを表示"""
        # 現在の値を取得
        values = self.maskList.item(item, "values")
        if "#5" == column:  # radius
            currentValue = values[4]
            colName = "radius"
        else:  # feather
            currentValue = values[5]
            colName = "feather"
        
        # セルの位置を取得
        bbox = self.maskList.bbox(item, column)
        if not bbox:
            return
        
        # Entry ウィジェットを作成
        self.editVar = tk.StringVar(value=currentValue)
        self.editEntry = tk.Entry(self.maskList, textvariable=self.editVar)
        self.editEntry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        self.editEntry.focus()
        self.editEntry.select_range(0, tk.END)
        
        # 編集情報を保存
        self.editItem = item
        self.editColumn = column
        
        # イベントバインド
        self.editEntry.bind("<Return>", self.finishCellEdit)
        self.editEntry.bind("<Escape>", self.cancelCellEdit)
        self.editEntry.bind("<FocusOut>", self.finishCellEdit)
    
    def finishCellEdit(self, event=None):
        """セル編集終了"""
        if not hasattr(self, 'editEntry'):
            return
        
        try:
            newValue = float(self.editVar.get())
            itemIndex = int(self.editItem)
            
            # 範囲チェック
            if "#5" == self.editColumn:  # radius
                if 0.001 <= newValue <= 1.0:
                    x, y, z, _, feather = self.tempSelectionPoints3d[itemIndex]
                    self.tempSelectionPoints3d[itemIndex] = (x, y, z, newValue, feather)
            else:  # feather
                if 0.1 <= newValue <= 10.0:
                    x, y, z, radius, _ = self.tempSelectionPoints3d[itemIndex]
                    self.tempSelectionPoints3d[itemIndex] = (x, y, z, radius, newValue)
            
            # リストを更新
            self.updateMaskList()
            self.canvas.updateDisplay()
            
        except ValueError:
            pass  # 無効な値は無視
        
        self.cancelCellEdit()
    
    def cancelCellEdit(self, event=None):
        """セル編集キャンセル"""
        if hasattr(self, 'editEntry'):
            self.editEntry.destroy()
            del self.editEntry
            del self.editVar
            del self.editItem
            del self.editColumn

class ColorSpaceCanvas(tk.Canvas):
    def __init__(self, parent, width=400, height=400):
        super().__init__(parent, width=width, height=height, bg="black")
        self.dialog = parent
        self.node = parent.node
        
        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        
        self.dragging = False
        self.dragging_mask = False
        self.clicked_inside_mask = False
        self.last_x = 0
        self.last_y = 0
    
    def on_click(self, event):
        self.last_x = event.x
        self.last_y = event.y
        self.dragging = False
        
        # 選択中のマスク円内をクリックしたかチェック
        self.clicked_inside_mask = self.isInsideSelectedMask(event.x, event.y)
        self.dragging_mask = False
    
    def on_drag(self, event):
        from utils import numpy_helpers as nh
        
        if self.clicked_inside_mask:
            # マスク円内からドラッグ開始
            if not self.dragging_mask:
                dx = abs(event.x - self.last_x)
                dy = abs(event.y - self.last_y)
                if 3 < dx or 3 < dy:
                    self.dragging_mask = True
            
            if self.dragging_mask:
                # マスクの移動
                self.moveMask(event.x, event.y)
                return
        
        if not self.dragging:
            dx = abs(event.x - self.last_x)
            dy = abs(event.y - self.last_y)
            if 3 < dx or 3 < dy:
                self.dragging = True
        
        if self.dragging:
            # 分離された X/Y 軸回転（ジンバルロック回避）
            width  = self.winfo_width()
            height = self.winfo_height()
            
            # マウス移動量を正規化
            dx = (event.x - self.last_x) / width  * 2.0
            dy = (event.y - self.last_y) / height * 2.0
            
            # カメラ座標系の軸を取得
            invRotation = self.dialog.tempRotationMatrix.T
            cameraRight = invRotation @ nh.array([1, 0, 0])  # X 軸
            cameraUp    = invRotation @ nh.array([0, 1, 0])  # Y 軸
            
            # Y 軸回転（左右ドラッグ）
            if 0.001 < abs(dx):
                yRotation = self.createRotationMatrix(cameraUp, dx)
                self.dialog.tempRotationMatrix = self.dialog.tempRotationMatrix @ yRotation
            
            # X 軸回転（上下ドラッグ）
            if 0.001 < abs(dy):
                # 更新されたカメラ座標系を再取得
                invRotation = self.dialog.tempRotationMatrix.T
                cameraRight = invRotation @ nh.array([1, 0, 0])
                xRotation   = self.createRotationMatrix(cameraRight, -dy)
                self.dialog.tempRotationMatrix = self.dialog.tempRotationMatrix @ xRotation
            
            self.dialog.updateInfo()
            self.updateDisplay()  # リアルタイム描画
            self.last_x = event.x
            self.last_y = event.y
    
    def on_release(self, event):
        if self.dragging_mask:
            # マスク移動終了
            self.dragging_mask = False
        elif self.clicked_inside_mask and not self.dragging:
            # マスク円内をクリック（ドラッグしなかった）→削除
            self.deleteMask()
        elif not self.dragging and not self.clicked_inside_mask:
            # 空き領域をクリック→選択点追加
            self.addPoint(event.x, event.y)
        
        # フラグをリセット
        self.dragging = False
        self.clicked_inside_mask = False
    
    def addPoint(self, screenX, screenY):
        from utils import numpy_helpers as nh
        
        # 断面位置を取得
        if (self.dialog.tempSelectedPointIndex is not None 
        and self.dialog.tempSelectedPointIndex < len(self.dialog.tempSelectionPoints3d)):
            # 選択中のマスク色の Z 位置をカメラ目線で計算
            selectedPoint = self.dialog.tempSelectionPoints3d[self.dialog.tempSelectedPointIndex]
            x, y, z, radius, feather = selectedPoint
            
            # 色空間座標を中心原点に変換
            centered = nh.array([x - 0.5, y - 0.5, z - 0.5])
            
            # 回転適用
            rotated = self.applyRotationToPoint(centered)
            
            # カメラ目線での Z 値を断面位置とする
            sliceZ = rotated[2]
        else:
            # 選択なしの場合は中央 (Z=0)
            sliceZ = 0.0
        
        # 画面座標 → [-1.0, 1.0] 座標系
        width  = self.winfo_width()
        height = self.winfo_height()
        
        uScreen = (screenX / width  - 0.5) * 2.0   # [-1.0, 1.0]
        vScreen = (screenY / height - 0.5) * 2.0   # [-1.0, 1.0]
        
        # 断面上の 3D 点 (Z=sliceZ 固定)
        screenPoint = nh.array([uScreen, vScreen, sliceZ])
        
        # 逆回転で色空間座標を取得
        colorPoint  = self.dialog.tempRotationMatrix.T @ screenPoint
        colorCoords = colorPoint + 0.5
        
        # 範囲チェック
        if (0.0 <= colorCoords[0] <= 1.0 
        and 0.0 <= colorCoords[1] <= 1.0 
        and 0.0 <= colorCoords[2] <= 1.0):
            
            x, y, z = colorCoords
            self.dialog.tempSelectionPoints3d.append((x, y, z, 0.1, 1.0))
            # 新しい点を直接リストに追加
            newIndex = len(self.dialog.tempSelectionPoints3d) - 1
            self.dialog.tempSelectedPointIndex = newIndex
            
            # リストに直接追加（全体再構築しない）
            self.dialog.maskList.insert("", "end", iid=str(newIndex), values=(
                newIndex, f"{x:.3f}", f"{y:.3f}", f"{z:.3f}", "0.100", "1.0"
            ))
            
            # 新しいアイテムを選択
            self.dialog.maskList.selection_set(str(newIndex))
    
    def updateDisplay(self):
        self.delete("all")
        
        width  = self.winfo_width()
        height = self.winfo_height()
        
        if width <= 1 or height <= 1:
            width = height = 400
        
        # 色空間の立方体を描画
        self.drawColorspaceSlice(width, height)
        self.drawWireframe(width, height)
        self.drawSelectionPoints(width, height)
    
    def drawColorspaceSlice(self, width, height):
        import numpy as np
        from utils import numpy_helpers as nh
        
        # 断面位置を決定
        if (self.dialog.tempSelectedPointIndex is not None 
        and self.dialog.tempSelectedPointIndex < len(self.dialog.tempSelectionPoints3d)):
            # 選択中のマスク色の Z 位置をカメラ目線で計算
            selectedPoint = self.dialog.tempSelectionPoints3d[self.dialog.tempSelectedPointIndex]
            x, y, z, radius, feather = selectedPoint
            
            # 色空間座標を中心原点に変換
            centered = nh.array([x - 0.5, y - 0.5, z - 0.5])
            
            # 回転適用
            rotated = self.applyRotationToPoint(centered)
            
            # カメラ目線での Z 値を断面位置とする
            sliceZ = rotated[2]
        else:
            # 選択なしの場合は中央 (Z=0)
            sliceZ = 0.0
        
        # Z=sliceZ 断面の色空間を描画
        step = 4  # 描画間隔
        
        for y in range(0, height, step):
            for x in range(0, width, step):
                # 画面座標 → [-1.0, 1.0] 座標系
                uScreen = (x / width  - 0.5) * 2.0   # [-1.0, 1.0]
                vScreen = (y / height - 0.5) * 2.0   # [-1.0, 1.0]
                
                # 断面上の 3D 点 (Z=sliceZ 固定)
                screenPoint = nh.array([uScreen, vScreen, sliceZ])
                
                # 逆回転で色空間座標を取得
                colorPoint = self.dialog.tempRotationMatrix.T @ screenPoint
                
                # 色空間座標 [0,1] に変換
                colorCoords = colorPoint + 0.5
                
                if (0.0 <= colorCoords[0] <= 1.0 
                and 0.0 <= colorCoords[1] <= 1.0 
                and 0.0 <= colorCoords[2] <= 1.0):
                    
                    # RGB 色に変換
                    if "RGB" == self.dialog.tempColorSpace:
                        rgb = colorCoords
                    else:  # Lab
                        rgb = self.labToRgb(colorCoords)
                    
                    # 色を描画
                    rgbInt = np.clip(rgb * 255, 0, 255).astype(int)
                    color  = f"#{rgbInt[0]:02x}{rgbInt[1]:02x}{rgbInt[2]:02x}"
                    
                    self.create_rectangle(x, y, x+step, y+step, 
                                        fill=color, outline="")
    
    def applyRotationToPoint(self, point):
        # 回転行列を直接適用
        return self.dialog.tempRotationMatrix @ point
    
    def createRotationMatrix(self, axis, angle):
        """ロドリゲスの回転公式で回転行列を作成"""
        from utils import numpy_helpers as nh
        import numpy as np
        
        if abs(angle) < 0.001:
            return nh.eye(3)
        
        axis  = axis / np.linalg.norm(axis)
        cosA  = np.cos(angle)
        sinA  = np.sin(angle)
        
        K = nh.array([
            [0,       -axis[2],  axis[1]],
            [axis[2],  0,       -axis[0]],
            [-axis[1], axis[0],  0      ]
        ])
        
        return nh.eye(3) + sinA * K + (1 - cosA) * (K @ K)
    
    def labToRgb(self, lab):
        from utils import numpy_helpers as nh
        
        # 簡易 Lab→RGB 変換
        L, a, b = lab
        
        # Lab 値を調整
        a = (a - 0.5) * 2  # [-1, 1]
        b = (b - 0.5) * 2  # [-1, 1]
        
        # 簡易変換
        R = L + a * 0.5
        G = L - a * 0.25 - b * 0.25
        B = L + b * 0.5
        
        return nh.array([R, G, B])
    
    def drawWireframe(self, width, height):
        """色空間立方体のワイヤーフレームを描画"""
        from utils import numpy_helpers as nh
        
        # 立方体の 8 個の頂点 (色空間座標)
        vertices = nh.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],  # 下面
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]   # 上面
        ])
        
        # 回転した頂点を画面座標に変換
        screenVertices = []
        for vertex in vertices:
            # 中心を原点として回転適用
            centered = vertex - 0.5
            rotated  = self.applyRotationToPoint(centered)
            
            # [-1,1] 座標系から画面座標へ変換
            screenX = (rotated[0] / 2.0 + 0.5) * width
            screenY = (rotated[1] / 2.0 + 0.5) * height
            
            screenVertices.append((screenX, screenY, rotated[2]))
        
        # 立方体の 12 本の辺を定義
        edges = [
            # 下面の 4 辺
            (0, 1), (1, 2), (2, 3), (3, 0),
            # 上面の 4 辺
            (4, 5), (5, 6), (6, 7), (7, 4),
            # 縦の 4 辺
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        
        # 辺を描画
        for startIdx, endIdx in edges:
            x1, y1, z1 = screenVertices[startIdx]
            x2, y2, z2 = screenVertices[endIdx]
            
            # Z 値による深度表現（手前が明るい）
            avgZ      = (z1 + z2) / 2
            intensity = int(200 + 55 * avgZ)  # 200-255 の範囲
            intensity = max(100, min(255, intensity))  # 範囲制限
            color     = f"#{intensity:02x}{intensity:02x}{intensity:02x}"
            
            self.create_line(x1, y1, x2, y2, fill=color, width=2)
    
    def drawSelectionPoints(self, width, height):
        # 選択中の点のみ表示
        if (self.dialog.tempSelectedPointIndex is not None 
        and self.dialog.tempSelectedPointIndex < len(self.dialog.tempSelectionPoints3d)):
            
            i = self.dialog.tempSelectedPointIndex
            x, y, z, radius, feather = self.dialog.tempSelectionPoints3d[i]
            
            # 3D→ 2D 投影
            screenX, screenY = self.project3DTo2D(x, y, z)
            
            # 半径に応じた円のサイズ（ピクセル）
            circleRadius = radius * 100  # 半径 0.1 → 10px
            
            # 黒白の二重円（外側黒、内側白）
            # 外側の黒い円
            self.create_oval(
                screenX - circleRadius, screenY - circleRadius,
                screenX + circleRadius, screenY + circleRadius,
                fill="", outline="black", width=3
            )
            
            # 内側の白い円
            self.create_oval(
                screenX - circleRadius, screenY - circleRadius,
                screenX + circleRadius, screenY + circleRadius,
                fill="", outline="white", width=1
            )
    
    def project3DTo2D(self, x, y, z):
        from utils import numpy_helpers as nh
        
        # 色空間座標を中心原点に変換
        centered = nh.array([x - 0.5, y - 0.5, z - 0.5])
        
        # 回転適用
        rotated = self.applyRotationToPoint(centered)
        
        # 画面座標に変換
        width  = self.winfo_width()
        height = self.winfo_height()
        screenX = (rotated[0] / 2.0 + 0.5) * width
        screenY = (rotated[1] / 2.0 + 0.5) * height
        
        return screenX, screenY
    
    def isInsideSelectedMask(self, screenX, screenY):
        """選択中のマスク円内か判定"""
        if (self.dialog.tempSelectedPointIndex is not None 
        and self.dialog.tempSelectedPointIndex < len(self.dialog.tempSelectionPoints3d)):
            
            i = self.dialog.tempSelectedPointIndex
            x, y, z, radius, feather = self.dialog.tempSelectionPoints3d[i]
            
            # 3D→2D 投影
            maskScreenX, maskScreenY = self.project3DTo2D(x, y, z)
            
            # 半径に応じた円のサイズ
            circleRadius = radius * 100
            
            # マウス位置が円内か判定
            distance = ((screenX - maskScreenX) ** 2 + (screenY - maskScreenY) ** 2) ** 0.5
            return distance <= circleRadius
        
        return False
    
    def moveMask(self, screenX, screenY):
        """選択中のマスクを移動"""
        from utils import numpy_helpers as nh
        
        if (self.dialog.tempSelectedPointIndex is not None 
        and self.dialog.tempSelectedPointIndex < len(self.dialog.tempSelectionPoints3d)):
            
            # 断面位置を取得
            selectedPoint = self.dialog.tempSelectionPoints3d[self.dialog.tempSelectedPointIndex]
            _, _, _, radius, feather = selectedPoint
            
            # カメラ目線での Z 値を断面位置とする
            x, y, z, _, _ = selectedPoint
            centered = nh.array([x - 0.5, y - 0.5, z - 0.5])
            rotated = self.applyRotationToPoint(centered)
            sliceZ = rotated[2]
            
            # 画面座標 → [-1.0, 1.0] 座標系
            width  = self.winfo_width()
            height = self.winfo_height()
            
            uScreen = (screenX / width  - 0.5) * 2.0
            vScreen = (screenY / height - 0.5) * 2.0
            
            # 断面上の 3D 点
            screenPoint = nh.array([uScreen, vScreen, sliceZ])
            
            # 逆回転で色空間座標を取得
            colorPoint  = self.dialog.tempRotationMatrix.T @ screenPoint
            colorCoords = colorPoint + 0.5
            
            # 範囲チェック
            if (0.0 <= colorCoords[0] <= 1.0 
            and 0.0 <= colorCoords[1] <= 1.0 
            and 0.0 <= colorCoords[2] <= 1.0):
                
                # マスク位置を更新
                x, y, z = colorCoords
                self.dialog.tempSelectionPoints3d[self.dialog.tempSelectedPointIndex] = (x, y, z, radius, feather)
                
                # リストを更新
                self.dialog.maskList.item(str(self.dialog.tempSelectedPointIndex), values=(
                    self.dialog.tempSelectedPointIndex, f"{x:.3f}", f"{y:.3f}", f"{z:.3f}", f"{radius:.3f}", f"{feather:.1f}"
                ))
                
                # 描画更新
                self.updateDisplay()
    
    def deleteMask(self):
        """選択中のマスクを削除"""
        if (self.dialog.tempSelectedPointIndex is not None 
        and self.dialog.tempSelectedPointIndex < len(self.dialog.tempSelectionPoints3d)):
            
            # マスクを削除
            del self.dialog.tempSelectionPoints3d[self.dialog.tempSelectedPointIndex]
            self.dialog.tempSelectedPointIndex = None
            
            # リストを全体更新（インデックスが変わるため）
            self.dialog.updateMaskList()
            self.updateDisplay()