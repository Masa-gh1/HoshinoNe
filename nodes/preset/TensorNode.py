'''
TensorNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk
from tkinter import simpledialog

from base import FlowNode, FlowData, DataBlock
from nodes import ConfigurableNode
from utils.interval_helper import createHalfOpenEnd

class TensorNode(FlowNode,ConfigurableNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "tensor", "数列")
        self.planeCount = 3
        self.xOrder = 1
        self.yOrder = 1
        self.planeNames = ["Plane 0","Plane 1","Plane 2"]
        self.tensor = {"0,0,0": 1.0,"1,0,0": 1.0,"2,0,0": 1.0}  # {"planeIdx,i,j": value}
        self.updateNodeText()
    
    def getColor(self):
        return self._color_const
    
    def updateNodeText(self):
        constVal = ""
        for planeIndex in range(self.planeCount):
            value = self.tensor.get(f"{planeIndex},0,0", 0)
            if     -1 < value < 1:
                constVal += f" {value:.3f}"
            elif  -10 < value < 10:
                constVal += f" {value:.2f}"
            elif -100 < value < 100:
                constVal += f" {value:.1f}"
            else:
                constVal += f" {value:.0f}"
        displayText = f"{self.text}\nP:{self.planeCount} xy:{self.xOrder}x{self.yOrder}\n{constVal}"
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        nodeData["planeCount"] = self.planeCount
        nodeData["xOrder"] = self.xOrder
        nodeData["yOrder"] = self.yOrder
        nodeData["tensor"] = self.tensor
        nodeData["planeNames"] = self.planeNames
    
    def restore(self, nodeData):
        if "planeCount" in nodeData:
            self.planeCount = nodeData["planeCount"]
        if "xOrder" in nodeData:
            self.xOrder = nodeData["xOrder"]
        if "yOrder" in nodeData:
            self.yOrder = nodeData["yOrder"]
        if "tensor" in nodeData:
            self.tensor = nodeData["tensor"]
        if "planeNames" in nodeData:
            self.planeNames = nodeData["planeNames"]
        else:
            # デフォルト名を生成
            self.planeNames = [f"Plane {i}" for i in range(self.planeCount)]
        self.updateNodeText()
    
    def onEdit(self):
        return TensorSettingsDialog(self.editor.root, self)
    
    def applySettings(self, planeCount, xOrder, yOrder, tensor, planeNames):
        self.planeCount = planeCount
        self.xOrder = xOrder
        self.yOrder = yOrder
        self.tensor = tensor
        self.planeNames = planeNames
        self.updateNodeText()
        
        newHash = self.getConfigHash()
        if newHash != self._lastConfigHash:
            self.editor.onNodeConfigChanged(self)
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 指定されたサイズの tensor を作成
        width = self.xOrder
        height = self.yOrder
        
        # モードを判断
        if width == 1 and height == 1:
            mode = "0D"
        elif width == 1 and height > 1:
            mode = "1D"
        elif width > 1 and height == 1:
            mode = "1D"
        elif width > 1 and height > 1:
            mode = "2D"
        else:
            mode = "2D"
        
        # プレーン名
        planeNames = self.planeNames
        
        # 列ラベルと行ラベルを生成
        columns = [f'{i}' for i in range(width)]
        lines = [f'{j}' for j in range(height)]
        
        headers = {
            'category': 'auxiliary',
            'type': 'tensor',
            'mode': mode,
            'axes': ['x_order', 'y_order'],
            'columns': columns,
            'lines': lines,
            'planes': planeNames,
            'max_orders': [self.xOrder, self.yOrder],
        }
        
        outputFlowData = FlowData(headers)
        outputFlowData.setDimensions(width, height)
        
        # 各プレーンに数列を設定
        for planeIdx in range(self.planeCount):
            polynomialData = []
            for j in range(height):
                row = []
                for i in range(width):
                    key = f"{planeIdx},{i},{j}"
                    row.append(self.tensor.get(key, 0))
                polynomialData.append(row)
            dataBlock = DataBlock(polynomialData, planeIdx, 0, 0)
            outputFlowData.setBlock(dataBlock)
        
        minValue = outputFlowData.getMinValue()
        maxValue = outputFlowData.getMaxValue()
        outputFlowData.headers['display_levels'] = {'min': minValue, 'exclusive_upper': createHalfOpenEnd( minValue, maxValue)}
        
        self.flowDatas = [outputFlowData]
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        tensorStr = str(sorted(self.tensor.items()))
        planeStr = str(self.planeNames)
        config = f"{self.type}_{self.planeCount}_{self.xOrder}_{self.yOrder}_{tensorStr}_{planeStr}"
        return hashlib.md5(config.encode()).hexdigest()

class TensorSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.coeffEntries = {}
        self.planeNameEntries = []
        
        self.title(f"{node.text}設定")
        self.geometry("600x450")
        
        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(basicFrame, text="プレーン数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.planeEntry = tk.Entry(basicFrame, width=5)
        self.planeEntry.insert(0, str(node.planeCount))
        self.planeEntry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(basicFrame, text="x項数:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.xOrderEntry = tk.Entry(basicFrame, width=5)
        self.xOrderEntry.insert(0, str(node.xOrder))
        self.xOrderEntry.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(basicFrame, text="Y項数:").grid(row=0, column=4, sticky="w", padx=5, pady=2)
        self.yOrderEntry = tk.Entry(basicFrame, width=5)
        self.yOrderEntry.insert(0, str(node.yOrder))
        self.yOrderEntry.grid(row=0, column=5, padx=5, pady=2)
        
        tk.Button(basicFrame, text="項数更新", command=self.updateOrder).grid(row=1, column=0, columnspan=6, pady=10)
        
        # 係数設定フレーム（スクロール可能）
        coeffFrame = tk.Frame(self, height=120)
        coeffFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        coeffFrame.pack_propagate(False)
        
        canvas = tk.Canvas(coeffFrame)
        scrollbar = tk.Scrollbar(coeffFrame, orient="vertical", command=canvas.yview)
        self.scrollableFrame = tk.Frame(canvas)
        
        self.scrollableFrame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollableFrame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # ボタン
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        # 初期係数表示
        self.updateOrder()
        
        # ウィンドウが閉じられたときのクリーンアップ
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def updateOrder(self):
        # 既存の係数エントリーをクリア
        for widget in self.scrollableFrame.winfo_children():
            widget.destroy()
        self.coeffEntries.clear()
        self.planeNameEntries.clear()
        
        planes = int(self.planeEntry.get())
        xOrd = int(self.xOrderEntry.get())
        yOrd = int(self.yOrderEntry.get())
        
        if planes <= 0 or xOrd <= 0 or yOrd <= 0:
            return
        
        row = 0
        for planeIdx in range(planes):
            # プレーン名をテキストボックスで表示
            planeNameEntry = tk.Entry(self.scrollableFrame, font=("Arial", 10, "bold"), width=20)
            if planeIdx < len(self.node.planeNames):
                planeNameEntry.insert(0, self.node.planeNames[planeIdx])
            else:
                planeNameEntry.insert(0, f"Plane {planeIdx}")
            planeNameEntry.grid(row=row, column=0, columnspan=4, sticky="w", pady=5, padx=5)
            
            self.planeNameEntries.append(planeNameEntry)
            
            row += 1
            
            # X軸ラベル（上部）
            for i in range(xOrd):
                tk.Label(self.scrollableFrame, text=f"x:{i}").grid(row=row, column=i + 1, padx=5, pady=2)
            row += 1
            
            # 係数エントリー
            for j in range(yOrd):
                # Y軸ラベル（左側）
                tk.Label(self.scrollableFrame, text=f"y:{j}").grid(row=row, column=0, sticky="w", padx=5, pady=2)
                
                for i in range(xOrd):
                    entry = tk.Entry(self.scrollableFrame, width=8)
                    key = f"{planeIdx},{i},{j}"
                    if key in self.node.tensor:
                        entry.insert(0, str(self.node.tensor[key]))
                    else:
                        entry.insert(0, "0")
                    entry.grid(row=row, column=i + 1, padx=5, pady=2)
                    self.coeffEntries[key] = entry
                
                row += 1
            
            row += 1
    
    def onApply(self):
        planes = int(self.planeEntry.get())
        xOrd = int(self.xOrderEntry.get())
        yOrd = int(self.yOrderEntry.get())
        
        if planes > 0 and xOrd >= 0 and yOrd >= 0:
            # 係数を収集
            tensor = {}
            for key, entry in self.coeffEntries.items():
                try:
                    val = float(entry.get())
                    if val != 0:
                        tensor[key] = val
                except ValueError:
                    print(f"Warning: Invalid coefficient value for {key}")
            
            # プレーン名を収集
            planeNames = []
            for entry in self.planeNameEntries:
                name = entry.get().strip()
                if not name:
                    name = f"Plane {len(planeNames)}"
                planeNames.append(name)
            
            self.node.applySettings(planes, xOrd, yOrd, tensor, planeNames)
    
    def onClose(self):
        self.destroy()