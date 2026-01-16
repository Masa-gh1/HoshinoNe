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
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'colorspace_mask'
    # ノード名
    name      = '色空間マスク'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        from utils import numpy_helpers as nh
        
        self.colorSpace = "RGB"
        self.mask3dPoints = []

        # 回転行列で管理
        self.rotationMatrix = nh.eye(3)
    
    def getText(self):
        pointCount = len(self.mask3dPoints)
        return f"{self.name}\n{self.colorSpace}空間\n{pointCount}点選択"
    
    def store(self, nodeData):
        nodeData["color_space"    ] = self.colorSpace
        nodeData["rotation_matrix"] = self.rotationMatrix.tolist()
        nodeData["mask_3d_points" ] = self.mask3dPoints
    
    def restore(self, nodeData):
        from utils import numpy_helpers as nh
        
        self.colorSpace     = nodeData.get("color_space", "RGB")
        matrixData          = nodeData.get("rotation_matrix", nh.eye(3).tolist())
        self.rotationMatrix = nh.array(matrixData)
        self.mask3dPoints   = nodeData.get("mask_3d_points", [])
    
    def createSettingWindow(self):
        return ColorSpaceMaskDialog(self.view.editor.root, self)
    
    def applySettings(self, colorSpace, rotationMatrix, mask3dPoints):
        self.colorSpace = colorSpace
        self.rotationMatrix = rotationMatrix
        self.mask3dPoints = mask3dPoints
        self.view.onNodeConfigChanged(self)
    
    def createLazyFlowData(self, inputData):
        return ColorSpaceMaskLazyFlowData(inputData, self.colorSpace, self.mask3dPoints)
    
    def getConfigHash(self):
        import numpy as np
        
        config = f"{self.colorSpace}_{self.mask3dPoints}"
        return hashlib.sha256(config.encode()).hexdigest()

class ColorSpaceMaskLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y, colorSpace, mask3dPoints):
        from base import DataBlock
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        import numpy as np
        
        # 色マスクがない場合は全て通す (1.0)
        if not mask3dPoints:
            maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
            return DataBlock(maskData, planeIndex, x, y)
        
        # モードに応じてRGBデータを取得
        mode = flowData.getMode()
        if mode in ["RGB", "RGBA"]:
            rBlock = flowData.getBlock(0, x, y)  # R
            gBlock = flowData.getBlock(1, x, y)  # G
            bBlock = flowData.getBlock(2, x, y)  # B
            
            if rBlock is None or gBlock is None or bBlock is None:
                maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
                return DataBlock(maskData, planeIndex, x, y)
            
            _R = rBlock.data
            _G = gBlock.data
            _B = bBlock.data

            if "Lab" == colorSpace:
                from utils import colorSpace
                # RGB/Lab 変換
                _L, _a, _b = colorSpace.rgbToLab(_R, _G, _B)
                colorBlock = np.stack([_L, _a, _b], axis=-1)  # (H, W, 3)
            else:  # RGB
                colorBlock = np.stack([_R, _G, _B], axis=-1)  # (H, W, 3)
            
        elif "RGBG" == mode:
            rBlock  = flowData.getBlock(0, x, y)  # R
            g1Block = flowData.getBlock(1, x, y)  # G1
            bBlock  = flowData.getBlock(2, x, y)  # B
            g2Block = flowData.getBlock(3, x, y)  # G2
            
            if rBlock is None or g1Block is None or bBlock is None or g2Block is None:
                maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
                return DataBlock(maskData, planeIndex, x, y)
            
            _R = rBlock.data
            _G = (g1Block.data + g2Block.data) / 2  # G
            _B = bBlock.data

            if "Lab" == colorSpace:
                from utils import colorSpace
                # RGB/Lab 変換
                _L, _a, _b = colorSpace.rgbToLab(_R, _G, _B)
                colorBlock = np.stack([_L, _a, _b], axis=-1)  # (H, W, 3)
            else:  # RGB
                colorBlock = np.stack([_R, _G, _B], axis=-1)  # (H, W, 3)
            
        elif "Lab" == mode:
            lBlock = flowData.getBlock(0, x, y)  # L
            aBlock = flowData.getBlock(1, x, y)  # a
            bBlock = flowData.getBlock(2, x, y)  # b
            
            if lBlock is None or aBlock is None or bBlock is None:
                maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
                return DataBlock(maskData, planeIndex, x, y)
            
            _L = lBlock.data
            _a = aBlock.data
            _b = bBlock.data
            
            if "Lab" == colorSpace:
                # Lab 値を画面の座標系へ変換
                colorBlock = np.stack([_L, _a, _b], axis=-1)
            else:  # RGB
                from utils import colorSpace
                # Lab/RGB 変換
                _R, _G, _B = colorSpace.labToRgb(_L, _a, _b)
                colorBlock = np.stack([_R, _G, _B], axis=-1)  # (H, W, 3)
        else:
            # 未対応モードは全て通す
            maskData = nh.ones((BLOCK_SIZE, BLOCK_SIZE))
            return DataBlock(maskData, planeIndex, x, y)
        
        # 色マスク生成 (ベクトル化)
        blockH, blockW = colorBlock.shape[:2]
        mask = nh.ones((blockH, blockW))  # 初期値は 1.0 (全て通す)
        
        for maskX, maskY, maskZ, radius, feather in mask3dPoints:
            # 色マスク中心
            maskCenter = nh.array([maskX, maskY, maskZ])
            
            # 全ピクセルとの距離を一度に計算
            diff = colorBlock - maskCenter  # (H, W, 3)
            distances = np.linalg.norm(diff, axis=-1)  # (H, W)
            
            # ガウシアンを計算
            sigma = feather
            effectiveRange = radius + sigma * 3.0
            isValid   =                        (distances <= effectiveRange)
            isFeather = (radius < distances) & (distances <= effectiveRange)
            if np.any(isFeather):
                maskValues = np.where(
                    isFeather,
                    1.0 - np.exp(-(((distances - radius) / sigma) ** 2)),
                    0.0
                )
                mask *= np.where(isValid, maskValues, 1.0)
            elif np.any(isValid):
                mask *= np.where(isValid, 0.0, 1.0)
            else:
                pass # なにもしない
        
        return DataBlock(mask, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['type', 'mode', 'planes', 'display_levels']
    
    def headerOperation(self, lazyFlowData, key, *args, **kwargs):
        return {
            'type': 'image',
            'mode': 'L',
            'planes': ['Mask'] * len(lazyFlowData.sourceFlowData.headers['planes']),
            'display_levels': {'min': 0.0, 'exclusive_upper': 1.0}
        }

class ColorSpaceMaskDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name}設定")
        self.geometry("500x650")
        
        # 元の設定を保存
        self.originalSettings = {
            'colorSpace'    : self.node.colorSpace,
            'rotationMatrix': self.node.rotationMatrix.copy(),
            'mask3dPoints'  : self.node.mask3dPoints.copy(),
        }
        
        # 一時的な設定
        self.tempColorSpace     = self.node.colorSpace
        self.tempRotationMatrix = self.node.rotationMatrix.copy()
        self.tempMask3dPoints   = self.node.mask3dPoints.copy()
        
        self.createWidgets()
        self.updateMaskList()
        self.after(100, self.updateDisplay)
        
        # ウィンドウが閉じられたときのクリーンアップ
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def addMask(self, x, y, z, radius=0.1, feather=0.05):
        self.tempMask3dPoints.append([x, y, z, radius, feather])
        return len(self.tempMask3dPoints) - 1

    def updateMask(self, index, x=None, y=None, z=None, radius=None, feather=None):
        if index < len(self.tempMask3dPoints):
            if x is not None:
                self.tempMask3dPoints[index][0] = x
            if y is not None:
                self.tempMask3dPoints[index][1] = y
            if z is not None:
                self.tempMask3dPoints[index][2] = z
            if radius is not None:
                self.tempMask3dPoints[index][3] = radius
            if feather is not None:
                self.tempMask3dPoints[index][4] = feather

    def deleteMask(self, index):
        if index < len(self.tempMask3dPoints):
            del self.tempMask3dPoints[index]
    
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
        
        # 操作説明
        helpFrame = tk.Frame(self)
        helpFrame.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(helpFrame, text="操作: ドラッグ=空間回転, 左クリック=追加, 右クリック=削除, マスクドラッグ=移動",
                font=("Arial", 9), foreground="gray").pack(side=tk.LEFT)
        
        # 色マスクリスト
        frameList = tk.Frame(self)
        frameList.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(frameList, text="色マスク:").pack(anchor=tk.W)
        
        # Treeview作成
        columns = ("index", "x", "y", "z", "radius", "feather")
        self.maskList = ttk.Treeview(frameList, columns=columns, show="headings", height=3)
        
        # 列設定
        self.maskList.heading("index", text="#")
        self.maskList.heading("x", text="R")
        self.maskList.heading("y", text="G")
        self.maskList.heading("z", text="B")
        self.maskList.heading("radius", text="半径")
        self.maskList.heading("feather", text="ぼかし")
        
        self.maskList.column("index", width=30)
        self.maskList.column("x", width=60)
        self.maskList.column("y", width=60)
        self.maskList.column("z", width=60)
        self.maskList.column("radius", width=50)
        self.maskList.column("feather", width=50)
        
        self.maskList.pack(fill=tk.BOTH, expand=True)
        self.maskList.bind("<<TreeviewSelect>>", self.onMaskSelect)
        self.maskList.bind("<Double-1>", self.onCellEdit)
        
        # ボタン
        frame3 = tk.Frame(self)
        frame3.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(frame3, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(frame3, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
    
    def onColorSpaceChange(self, event=None):
        self.tempColorSpace = self.colorSpaceVar.get()

        # 列ヘッダーを色空間に応じて更新
        if "RGB" == self.tempColorSpace:
            import numpy as np
            from utils import colorSpace
            self.maskList.heading("x", text="R")
            self.maskList.heading("y", text="G")
            self.maskList.heading("z", text="B")

            # 色マスクの位置を RGB に変換する
            for i, (l, a, b, radius, feather) in enumerate(self.tempMask3dPoints):
                rgb = colorSpace.labToRgb(l,a,b)
                r, g, b = np.clip(rgb, 0.0, 1.0)
                self.tempMask3dPoints[i] = [r, g, b, radius, feather]
            
            self.updateMaskList()
            self.updateDisplay()
        else:  # Lab
            from utils import colorSpace
            self.maskList.heading("x", text="L")
            self.maskList.heading("y", text="a")
            self.maskList.heading("z", text="b")

            # 色マスクの位置を Lab に変換する
            for i, (r, g, b, radius, feather) in enumerate(self.tempMask3dPoints):
                l, a, b = colorSpace.rgbToLab(r, g, b)
                self.tempMask3dPoints[i] = [l, a, b, radius, feather]
        
            self.updateMaskList()
            self.updateDisplay()

    def updateDisplay(self):
        self.canvas.updateDisplay()
    
    def updateMaskList(self):
        # リストを更新
        listCnt = len(self.maskList.get_children())
        maskCnt = len(self.tempMask3dPoints)
        for id, (x, y, z, radius, feather) in zip(self.maskList.get_children(), self.tempMask3dPoints):
            self.maskList.item(id, values=(id, f"{x:.3f}", f"{y:.3f}", f"{z:.3f}", f"{radius:.3f}", f"{feather:.3f}"))

        # 余分なリストを削除
        for id in self.maskList.get_children()[maskCnt:]:
            self.maskList.delete(id)
        
        # 色マスクを追加
        for i, (x, y, z, radius, feather) in enumerate(self.tempMask3dPoints[listCnt:]):
            id = listCnt + i
            self.maskList.insert("", "end", iid=str(id),
                                 values=(id, f"{x:.3f}", f"{y:.3f}", f"{z:.3f}", f"{radius:.3f}", f"{feather:.3f}"))
    
    def onMaskSelect(self, event=None):
        self.canvas.updateDisplay()
    
    def selectMaskIndex(self, index):
        if index < len(self.tempMask3dPoints):
            self.maskList.selection_set(index)
        
    def unselectMask(self):
        selection = self.maskList.selection()
        if selection:
            self.maskList.selection_remove(selection)
        
    def getSelectionMaskIndex(self):
        selection = self.maskList.selection()
        if not selection:
            return None
        else:
            return int(selection[0])

    def onApply(self):
        # 一時的な設定を確定
        self.node.applySettings(
            self.tempColorSpace,
            self.tempRotationMatrix,
            self.tempMask3dPoints
        )
        
        # 確定値を更新
        self.originalSettings = {
            'colorSpace'    : self.tempColorSpace,
            'rotationMatrix': self.tempRotationMatrix.copy(),
            'mask3dPoints'  : self.tempMask3dPoints.copy(),
        }
    
    def onClose(self):
        # 元の設定に戻す
        self.node.colorSpace     = self.originalSettings['colorSpace']
        self.node.rotationMatrix = self.originalSettings['rotationMatrix']
        self.node.mask3dPoints   = self.originalSettings['mask3dPoints']
        
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
                if 0.01 <= newValue <= 1.0:
                    self.updateMask(itemIndex, radius=newValue)
                    self.updateMaskList()
                    self.canvas.updateDisplay()
            else:  # feather
                if 0.0 <= newValue <= 1.0:
                    self.updateMask(itemIndex, feather=newValue)
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
        """
        色空間を描画するキャンバス
        色空間は一辺 [0.0, 1.0) の立方体
        スクリーン座標系の width, height の短い方向をワールド座標系 [-1.0, 1.0) とする

        :param parent: 親ウィジェット
        :param width:  描画幅
        :param height: 描画高さ
        """
        super().__init__(parent, width=width, height=height, bg="black")
        self.dialog = parent
        self.node = parent.node

        self.sliceZ      = 0.0  # 色空間断面の z 位置
        self._sliceImage = None # 色空間断面画像
        
        self.bind("<Button-1>", self.onPress)
        self.bind("<Button-3>", self.onRightPress)
        self.bind("<B1-Motion>", self.onDrag)
        self.bind("<ButtonRelease-1>", self.onRelease)
        
        self.isDragging = False
        self.isDraggingMask = False
        self.isClickedMask = False
        self.last_x = 0
        self.last_y = 0
    
    def onPress(self, event):
        self.last_x = event.x
        self.last_y = event.y
        self.isDragging = False
        self.isDraggingMask = False
        
        # 選択中の色マスク円内をクリックしたかチェック
        self.isClickedMask = self.isInsideSelectedMask(event.x, event.y)
    
    def onRightPress(self, event):
        self.last_x = event.x
        self.last_y = event.y
        self.isDragging = False
        self.isDraggingMask = False
        
        # 選択中の色マスク円内をクリックしたかチェック
        if self.isInsideSelectedMask(event.x, event.y):
            # 色マスク円内をクリックしたので削除
            self.dialog.deleteMask(self.dialog.getSelectionMaskIndex())
            self.dialog.unselectMask()
            self.dialog.updateMaskList()
    
    def onDrag(self, event):
        from utils import numpy_helpers as nh
        
        if self.isClickedMask:
            # 色マスク円内からドラッグなので色マスクの移動
            self.isDraggingMask = True
            self.moveMask(event.x, event.y)
            return
        else:
            # 色空間を回転
            self.isDragging = True
            
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
            
            self.updateDisplay()  # リアルタイム描画
            self.last_x = event.x
            self.last_y = event.y
    
    def onRelease(self, event):
        if self.isDraggingMask:
            # 色マスク移動終了
            self.isClickedMask = False
            self.isDraggingMask = False
        elif self.isDragging:
            # 色空間回転終了
            self.isDragging = False
        elif self.isClickedMask:
            # なにもしない
            self.isClickedMask = False
        else:
            # 空き領域をクリックしたので色マスク追加
            self.addMask(event.x, event.y)
    
    def addMask(self, screenX, screenY):
        from utils import numpy_helpers as nh
        
        # スクリーン座標をワールド座標に変換
        worldX, worldY = self.screenToWorld(screenX, screenY)
        
        # 断面上の 3D 点
        screenPoint = nh.array([worldX, worldY, self.sliceZ])
        
        # 逆回転で色空間座標を取得
        colorPoint  = self.dialog.tempRotationMatrix.T @ screenPoint
        colorCoords = colorPoint + 0.5 # 原点を色空間の中心から端へ移動
        
        # 範囲チェック
        if (   0.0 <= colorCoords[0] <= 1.0 
           and 0.0 <= colorCoords[1] <= 1.0 
           and 0.0 <= colorCoords[2] <= 1.0
           ):
            
            x, y, z = colorCoords
            if "RGB" == self.dialog.tempColorSpace:
                r, g, b = self.cubeToRGB(x, y, z)
                newIndex = self.dialog.addMask(r, g, b)
                self.dialog.updateMaskList() # リストを更新
            else:  # Lab
                l, a, b = self.cubeToLab(x, y, z)
                newIndex = self.dialog.addMask(l, a, b)
                self.dialog.updateMaskList() # リストを更新
                
            # 新しいアイテムを選択
            self.dialog.selectMaskIndex(newIndex)

            self.updateDisplay()
    
    def moveMask(self, screenX, screenY):
        """選択中の色マスクを移動"""
        from utils import numpy_helpers as nh
        
        selection = self.dialog.getSelectionMaskIndex()
        if(   not selection is None 
          and     selection < len(self.dialog.tempMask3dPoints)
          ):
            # スクリーン座標をワールド座標に変換
            worldX, worldY = self.screenToWorld(screenX, screenY)
            
            # 断面上の 3D 点
            screenPoint = nh.array([worldX, worldY, self.sliceZ])
            
            # 逆回転で色空間座標を取得
            colorPoint  = self.dialog.tempRotationMatrix.T @ screenPoint
            colorCoords = colorPoint + 0.5
            
            # 範囲チェック
            if(   0.0 <= colorCoords[0] <= 1.0 
              and 0.0 <= colorCoords[1] <= 1.0 
              and 0.0 <= colorCoords[2] <= 1.0
              ):
                # 色マスク位置を更新
                if "RGB" == self.dialog.tempColorSpace:
                    r, g, b = self.cubeToRGB(*colorCoords)
                    self.dialog.updateMask(selection, x=r, y=g, z=b)
                    self.dialog.updateMaskList()
                    self.updateDisplay()
                else:  # Lab
                    l, a, b = self.cubeToLab(*colorCoords)
                    self.dialog.updateMask(selection, x=l, y=a, z=b)
                    self.dialog.updateMaskList()
                    self.updateDisplay()

    def updateDisplay(self):
        self.delete("all")
        
        # 色空間の立方体を描画
        self.drawColorspaceSlice()
        self.drawWireframe()
        self.drawSelectionPoints()
    
    def drawColorspaceSlice(self):
        import numpy as np
        from utils import numpy_helpers as nh
        from PIL import Image, ImageTk
        
        width  = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            return
        
        selection = self.dialog.getSelectionMaskIndex()

        # 断面位置を決定
        if (   not selection is None 
           and     selection < len(self.dialog.tempMask3dPoints)
           ):
            # 選択中の色マスクの Z 位置をカメラ目線で計算
            selectedPoint = self.dialog.tempMask3dPoints[selection]
            if "RGB" == self.dialog.tempColorSpace:
                r, g, b, radius, feather = selectedPoint
                x, y, z = self.rgbToCube(r, g, b)
            else:  # Lab
                l, a, b, radius, feather = selectedPoint
                x, y, z = self.labToCube(l, a, b)
            
            # 回転適用
            centered = nh.array([x - 0.5, y - 0.5, z - 0.5])    # 色空間の中心で回転
            rotated = self.dialog.tempRotationMatrix @ centered
            
            # カメラ目線での Z 値を断面位置とする
            self.sliceZ = rotated[2]
        else:
            # 選択なしの場合は中央 (Z=0)
            self.sliceZ = 0.0
        
        # Z=sliceZ 断面の色空間を描画
        
        # スクリーン座標のグリッドを生成
        y_coords, x_coords = np.mgrid[0:height, 0:width]

        # スクリーン座標をワールド座標に変換
        worldX, worldY = self.screenToWorld(x_coords, y_coords)
        worldPoints = np.stack([worldX, worldY, np.full_like(worldX, self.sliceZ)], axis=-1)

        # 逆回転で色空間座標を取得
        colorPoints = worldPoints @ self.dialog.tempRotationMatrix
        colorCoords = colorPoints + 0.5 # 原点を色空間の中心から端へ移動

        # 範囲外のピクセルマスクを作成
        valided = np.all((0.0 <= colorCoords) & (colorCoords < 1.0), axis=-1)
        
        # 画像作成
        imageData = np.zeros((height, width, 3), dtype=np.uint8)
        
        if np.any(valided):
            validCoords = colorCoords[valided]
            
            # RGB 色に変換
            if "RGB" == self.dialog.tempColorSpace:
                r, g, b = self.cubeToRGB(validCoords[:, 0], validCoords[:, 1], validCoords[:, 2])
            else:  # Lab
                from utils import colorSpace
                l, a, b = self.cubeToLab(validCoords[:, 0], validCoords[:, 1], validCoords[:, 2])
                r, g, b = colorSpace.labToRgb(l, a, b)
            
            # RGB値を [0, 255] の整数に変換
            r = np.clip(r * 256, 0, 255).astype(np.uint8)
            g = np.clip(g * 256, 0, 255).astype(np.uint8)
            b = np.clip(b * 256, 0, 255).astype(np.uint8)
            
            # マスクされた部分に色を適用
            imageData[valided] = np.stack([r, g, b], axis=-1)

        # PIL Imageを作成し、Tkinter PhotoImageに変換して描画
        img = Image.fromarray(imageData, 'RGB')
        
        self._sliceImage = ImageTk.PhotoImage(image=img)
        self.create_image(0, 0, image=self._sliceImage, anchor=tk.NW)
    
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
    
    def cubeToRGB(self, x, y, z):
        """
        色空間座標から RGB 色に変換

        :param x [0.0,1.0)
        :param y [0.0,1.0)
        :param z [0.0,1.0)
        :return (R, G, B) [0.0,1.0)
        """
        _R = x
        _G = y
        _B = z
        
        return (_R, _G, _B)
    
    def rgbToCube(self, r, g, b):
        """
        RGB 色から色空間座標に変換

        :param r [0.0,1.0)
        :param g [0.0,1.0)
        :param b [0.0,1.0)
        :return (x, y, z) [0.0,1.0)
        """
        _x = r
        _y = g
        _z = b
        
        return (_x, _y, _z)
    
    def cubeToLab(self, x, y, z):
        """
        色空間座標から Lab 色に変換

        :param x [0.0,1.0)
        :param y [0.0,1.0)
        :param z [0.0,1.0)
        :return (L, a, b) [0.0,1.0), (-1.415,1.415), (-1.415,1.415)
        """
        _L = x
        _a = (y-0.5)*(2.0*1.41421356237)
        _b = (z-0.5)*(2.0*1.41421356237)
        
        return (_L, _a, _b)
    
    def labToCube(self, l, a, b):
        """
        Lab 色から色空間座標に変換

        :param l [0.0,1.0)
        :param a [-1.415,1.415)
        :param b [-1.415,1.415)
        :return (x, y, z) [0.0,1.0)
        """
        _x = l
        _y = a/(2.0*1.41421356237)+0.5
        _z = b/(2.0*1.41421356237)+0.5
        
        return (_x, _y, _z)

    def drawWireframe(self):
        """色空間立方体のワイヤーフレームを描画"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        # 立方体の 8 個の頂点 (色空間座標)
        vertices = nh.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],  # 下面
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]   # 上面
        ])

        # 頂点を一度に回転・変換 (ベクトル化)
        centered = vertices - 0.5 # 色空間の中心で回転
        rotated = centered @ self.dialog.tempRotationMatrix.T
        
        # ワールド座標をスクリーン座標に変換
        screen_x, screen_y = self.worldToScreen(rotated[:, 0], rotated[:, 1])
        screenVertices = np.stack([screen_x, screen_y, rotated[:, 2]], axis=1)
        
        # 立方体の 12 本の辺を定義
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),  # 下面
            (4, 5), (5, 6), (6, 7), (7, 4),  # 上面
            (0, 4), (1, 5), (2, 6), (3, 7)   # 縦
        ]
        
        # 辺を描画
        for startIdx, endIdx in edges:
            x1, y1, z1 = screenVertices[startIdx]
            x2, y2, z2 = screenVertices[endIdx]
            
            # Z 値による深度表現（手前が明るい）
            avgZ = (z1 + z2) / 2
            intensity = np.clip(int(200 + 55 * avgZ), 100, 255)
            color     = f"#{intensity:02x}{intensity:02x}{intensity:02x}"
            self.create_line(x1, y1, x2, y2, fill=color, width=2)
    
    def drawSelectionPoints(self):
        # 選択中の色マスクのみ表示
        selection = self.dialog.getSelectionMaskIndex()
        if (   not selection is None 
           and     selection < len(self.dialog.tempMask3dPoints)
           ):
            
            if "RGB" == self.dialog.tempColorSpace:
                r, g, b, radius, feather = self.dialog.tempMask3dPoints[selection]
                x, y, z = self.rgbToCube(r, g, b)
            else:  # Lab
                l, a, b, radius, feather = self.dialog.tempMask3dPoints[selection]
                x, y, z = self.labToCube(l, a, b)
            
            # 3D/2D 投影
            screenX, screenY = self.project3DTo2D(x, y, z)
            
            # 色空間座標の半径をスクリーン座標に変換
            radiusPixels    = radius                   / self.worldPerScreen()
            effectivePixels = (radius + feather * 3.0) / self.worldPerScreen()
            
            # ガウシアン範囲（薄い円）
            self.create_oval(
                screenX - effectivePixels, screenY - effectivePixels,
                screenX + effectivePixels, screenY + effectivePixels,
                fill="", outline="gray", width=1
            )
            
            # 基本半径（濃い円）
            self.create_oval(
                screenX - radiusPixels, screenY - radiusPixels,
                screenX + radiusPixels, screenY + radiusPixels,
                fill="", outline="white", width=2
            )
    
    def project3DTo2D(self, x, y, z):
        """色空間座標をスクリーン座標に投影"""
        from utils import numpy_helpers as nh
        
        # 回転適用
        centered = nh.array([x - 0.5, y - 0.5, z - 0.5]) # 色空間の中心で回転
        rotated = self.dialog.tempRotationMatrix @ centered
        
        # ワールド座標をスクリーン座標に変換
        screenX, screenY = self.worldToScreen(rotated[0], rotated[1])
        
        return screenX, screenY
    
    def worldPerScreen(self):
        """スクリーン座標当たりのワールド座標の長さ"""
        width  = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width = height = 400
        return 2.0/min(width,height)

    def screenToWorld(self, screenX, screenY):
        """スクリーン座標をワールド座標に変換"""
        width  = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width = height = 400
        scale = 2.0/min(width,height)

        worldX = (screenX - width  / 2) * scale
        worldY = (screenY - height / 2) * scale
        
        return worldX, worldY
    
    def worldToScreen(self, worldX, worldY):
        """ワールド座標をスクリーン座標に変換"""
        width  = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width = height = 400
        scale = 2.0/min(width,height)

        screenX = worldX / scale + width  / 2
        screenY = worldY / scale + height / 2
        
        return screenX, screenY

    def isInsideSelectedMask(self, screenX, screenY):
        """選択中の色マスク円内か判定"""
        selection = self.dialog.getSelectionMaskIndex()
        if selection is None:
            return False
        elif len(self.dialog.tempMask3dPoints) <= selection:
            return False
        else:
            if "RGB" == self.dialog.tempColorSpace:
                r, g, b, radius, feather = self.dialog.tempMask3dPoints[selection]
                x, y, z = self.rgbToCube(r, g, b)
            else:  # Lab
                l, a, b, radius, feather = self.dialog.tempMask3dPoints[selection]
                x, y, z = self.labToCube(l, a, b)
            
            # 3D/2D 投影
            maskScreenX, maskScreenY = self.project3DTo2D(x, y, z)
            
            # 半径に応じた円のサイズ
            circleRadius = radius / self.worldPerScreen()
            
            # マウス位置が円内か判定
            distance = ((screenX - maskScreenX) ** 2 + (screenY - maskScreenY) ** 2) ** 0.5
            return distance <= circleRadius
