'''
CoefficientsNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk
from tkinter import simpledialog

from base.FlowNode_CONST import *
from base import FlowNode, FlowData, DataBlock
from nodes import ConfigurableNode
from utils import string_helper as sh
from utils.interval_helper import createHalfOpenEnd

class CoefficientsNode(FlowNode,ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_CONST
    minorType = 'coefficients'
    # ノード名
    name      = '係数'
    # 入出力タイプ
    ioType    = _IO_TYPE_0N
    outputCat = _OUT_CAT_AUX 

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self.planeCount = 3
        self.xOrder = 0
        self.yOrder = 0
        self.planeNames = ["Plane 0","Plane 1","Plane 2"]
        self.coefficients = {"0,0,0": 1.0,"1,0,0": 1.0,"2,0,0": 1.0}  # {"planeIndex,i,j": value}
    
    def getText(self):
        """ノードのテキストを取得"""
        constVal = ""
        for planeIndex in range(self.planeCount):
            value = self.coefficients.get(f"{planeIndex},0,0", 0)
            constVal += f" {sh.dispS(value)}"
        displayText = f"{self.name}\nP:{self.planeCount} xy:{self.xOrder}x{self.yOrder}\n{constVal}"
        return displayText
    
    def store(self, nodeData):
        nodeData["planeCount"] = self.planeCount
        nodeData["xOrder"] = self.xOrder
        nodeData["yOrder"] = self.yOrder
        nodeData["coefficients"] = self.coefficients
        nodeData["planeNames"] = self.planeNames
    
    def restore(self, nodeData):
        if "planeCount" in nodeData:
            self.planeCount = nodeData["planeCount"]
        if "xOrder" in nodeData:
            self.xOrder = nodeData["xOrder"]
        if "yOrder" in nodeData:
            self.yOrder = nodeData["yOrder"]
        if "coefficients" in nodeData:
            self.coefficients = nodeData["coefficients"]
        if "planeNames" in nodeData:
            self.planeNames = nodeData["planeNames"]
        else:
            # デフォルト名を生成
            self.planeNames = [f"Plane {i}" for i in range(self.planeCount)]
    
    def createSettingWindow(self):
        return PolynomialSettingsDialog(self.view.editor.root, self)
    
    def applySettings(self, planeCount, xOrder, yOrder, coefficients, planeNames):
        self.planeCount = planeCount
        self.xOrder = xOrder
        self.yOrder = yOrder
        self.coefficients = coefficients
        self.planeNames = planeNames
        self.view.onNodeConfigChanged(self)
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 指定されたサイズの係数Polynomialを作成
        width = self.xOrder + 1
        height = self.yOrder + 1
        
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
        columns = [f'x^{i}' for i in range(width)]
        lines = [f'y^{j}' for j in range(height)]
        
        headers = {
            'category': 'auxiliary',
            'type': 'polynomial',
            'mode': mode,
            'axes': ['x_order', 'y_order'],
            'columns': columns,
            'lines': lines,
            'planes': planeNames,
            'max_orders': [self.xOrder, self.yOrder],
            'equations': [f'{name} = coefficients' for name in planeNames]
        }
        
        outputFlowData = FlowData(headers)
        outputFlowData.setDimensions(width, height)
        
        # 各プレーンに係数を設定
        for planeIndex in range(self.planeCount):
            result = []
            for j in range(height):
                row = []
                for i in range(width):
                    key = f"{planeIndex},{i},{j}"
                    row.append(self.coefficients.get(key, 0))
                result.append(row)
            dataBlock = DataBlock(result, planeIndex, 0, 0)
            outputFlowData.setBlock(dataBlock)
        
        minValue = outputFlowData.getMinValue()
        maxValue = outputFlowData.getMaxValue()
        outputFlowData.headers['display_levels'] = {'min': minValue, 'exclusive_upper': createHalfOpenEnd( minValue, maxValue)}
        
        self.flowDatas = [outputFlowData]
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        coeffStr = str(sorted(self.coefficients.items()))
        planeStr = str(self.planeNames)
        config = f"{self.minorType}_{self.planeCount}_{self.xOrder}_{self.yOrder}_{coeffStr}_{planeStr}"
        return hashlib.md5(config.encode()).hexdigest()

class PolynomialSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.coeffEntries = {}
        self.planeNameEntries = []
        
        self.title(f"{node.name}設定")
        self.geometry("600x450")
        
        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(basicFrame, text="プレーン数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.planeEntry = tk.Entry(basicFrame, width=5)
        self.planeEntry.insert(0, str(node.planeCount))
        self.planeEntry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(basicFrame, text="X次数:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.xOrderEntry = tk.Entry(basicFrame, width=5)
        self.xOrderEntry.insert(0, str(node.xOrder))
        self.xOrderEntry.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(basicFrame, text="Y次数:").grid(row=0, column=4, sticky="w", padx=5, pady=2)
        self.yOrderEntry = tk.Entry(basicFrame, width=5)
        self.yOrderEntry.insert(0, str(node.yOrder))
        self.yOrderEntry.grid(row=0, column=5, padx=5, pady=2)
        
        tk.Button(basicFrame, text="次数更新", command=self.updateOrder).grid(row=1, column=0, columnspan=6, pady=10)
        
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
        
        try:
            planes = int(self.planeEntry.get())
            xOrd = int(self.xOrderEntry.get())
            yOrd = int(self.yOrderEntry.get())
            
            if planes <= 0 or xOrd < 0 or yOrd < 0:
                return
            
            row = 0
            for planeIndex in range(planes):
                # プレーン名をテキストボックスで表示
                planeNameEntry = tk.Entry(self.scrollableFrame, font=("Arial", 10, "bold"), width=20)
                if planeIndex < len(self.node.planeNames):
                    planeNameEntry.insert(0, self.node.planeNames[planeIndex])
                else:
                    planeNameEntry.insert(0, f"Plane {planeIndex}")
                planeNameEntry.grid(row=row, column=0, columnspan=4, sticky="w", pady=5, padx=5)
                
                self.planeNameEntries.append(planeNameEntry)
                
                row += 1
                
                # X軸ラベル（上部）
                for i in range(xOrd + 1):
                    tk.Label(self.scrollableFrame, text=f"x^{i}").grid(row=row, column=i + 1, padx=5, pady=2)
                row += 1
                
                # 係数エントリー
                for j in range(yOrd + 1):
                    # Y軸ラベル（左側）
                    tk.Label(self.scrollableFrame, text=f"y^{j}").grid(row=row, column=0, sticky="w", padx=5, pady=2)
                    
                    for i in range(xOrd + 1):
                        entry = tk.Entry(self.scrollableFrame, width=8)
                        key = f"{planeIndex},{i},{j}"
                        if key in self.node.coefficients:
                            entry.insert(0, str(self.node.coefficients[key]))
                        else:
                            entry.insert(0, "0")
                        entry.grid(row=row, column=i + 1, padx=5, pady=2)
                        self.coeffEntries[key] = entry
                    
                    row += 1
                
                row += 1
        except ValueError:
            print("Waring: Invalid input for plane count, x order, or y order.")
    
    def onApply(self):
        planes = int(self.planeEntry.get())
        xOrd = int(self.xOrderEntry.get())
        yOrd = int(self.yOrderEntry.get())
        
        if planes > 0 and xOrd >= 0 and yOrd >= 0:
            # 係数を収集
            coefficients = {}
            for key, entry in self.coeffEntries.items():
                try:
                    val = float(entry.get())
                    if val != 0:
                        coefficients[key] = val
                except ValueError:
                    print(f"Warning: Invalid coefficient value for {key}")
            
            # プレーン名を収集
            planeNames = []
            for entry in self.planeNameEntries:
                name = entry.get().strip()
                if not name:
                    name = f"Plane {len(planeNames)}"
                planeNames.append(name)
            
            self.node.applySettings(planes, xOrd, yOrd, coefficients, planeNames)
    
    def onClose(self):
        self.destroy()