'''
CoefficientsNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

class CoefficientsNode(FlowNode,ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_CONST
    minorType = 'coefficients'
    # ノード名
    name      = '係数'
    # 入出力タイプ
    ioType    = _IO_TYPE_0N
    outputCat = _OUT_CAT_NON

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self.outputCat = _OUT_CAT_AUX # オーバーライド
        self.planes = ["Plane 0","Plane 1","Plane 2"]
        self.xOrder = 0
        self.yOrder = 0
        self.coefficients = {"0,0,0": 1.0,"1,0,0": 1.0,"2,0,0": 1.0}  # {"planeIndex,i,j": value}
    
    def getText(self):
        """ノードのテキストを取得"""
        from utils import string_helper as sh
        
        constVal = ""
        count = 0
        for x in range(self.xOrder + 1):
            for y in range(self.yOrder + 1):
                for planeIndex in range(len(self.planes)):
                    key = f"{planeIndex},{x},{y}"
                    value = self.coefficients.get(key, 0)
                    constVal += f" {sh.dispS(value)}"
                    count += 1
                    if 3 <= count:
                        displayText = f"{self.name}\nP:{len(self.planes)} xy:{self.xOrder}x{self.yOrder}\n{constVal}"
                        return displayText
        displayText = f"{self.name}\nP:{len(self.planes)} xy:{self.xOrder}x{self.yOrder}\n{constVal}"
        return displayText
    
    def store(self, nodeData):
        nodeData["category"    ] = self.outputCat
        nodeData["planes"      ] = self.planes
        nodeData["xOrder"      ] = self.xOrder
        nodeData["yOrder"      ] = self.yOrder
        nodeData["coefficients"] = self.coefficients
    
    def restore(self, nodeData):
        if "category" in nodeData:
            self.outputCat = nodeData["category"]
        if "planes" in nodeData:
            self.planes = nodeData["planes"]
        if "xOrder" in nodeData:
            self.xOrder = nodeData["xOrder"]
        if "yOrder" in nodeData:
            self.yOrder = nodeData["yOrder"]
        if "coefficients" in nodeData:
            self.coefficients = nodeData["coefficients"]
    
    def createSettingWindow(self):
        return PolynomialSettingsDialog(self.view.editor.root, self)
    
    def applySettings(self, outputCat, planes, xOrder, yOrder, coefficients):
        self.outputCat    = outputCat
        self.planes       = planes
        self.xOrder       = xOrder
        self.yOrder       = yOrder
        self.coefficients = coefficients
        self.view.onNodeConfigChanged(self)
    
    def process(self, context=None):
        from utils.interval_helper import createHalfOpenEnd
        from base import DataBlock
        from base import FlowData
        
        self.reportProgress(context, "開始")
        
        # 指定されたサイズの polynomial を作成
        planeCount = len(self.planes)
        width      = self.xOrder + 1
        height     = self.yOrder + 1
        
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
        
        # 列ラベルと行ラベルを生成
        columns = [f'x^{i}' for i in range(width)]
        lines   = [f'y^{j}' for j in range(height)]
        
        headers = {
            'category'  : self.outputCat,
            'type'      : 'polynomial',
            'mode'      : mode,
            'planes'    : self.planes,
            'columns'   : columns,
            'lines'     : lines,
            'axes'      : ['x_order', 'y_order'],
            'max_orders': [self.xOrder, self.yOrder],
            'equations' : [f'{name} = coefficients' for name in self.planes]
        }
        
        outputFlowData = FlowData(headers)
        outputFlowData.setDimensions(width, height)
        
        # 各プレーンに係数を設定
        for planeIndex in range(planeCount):
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
        config = f"{self.minorType}_{self.outputCat}_{self.planes}_{self.xOrder}_{self.yOrder}_{coeffStr}"
        return hashlib.md5(config.encode()).hexdigest()

class PolynomialSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node   = node
        self.outputCat = tk.BooleanVar(value=node.outputCat == _OUT_CAT_AUX)
        self.planes    = node.planes.copy()
        self.xOrder    = node.xOrder
        self.yOrder    = node.yOrder
        self.coeff     = node.coefficients.copy()
        
        self.title(f"{node.name}設定")
        self.geometry("600x450")
        
        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(basicFrame, text="プレーン数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.planeCountEntry = tk.Entry(basicFrame, width=5)
        self.planeCountEntry.insert(0, str(len(self.planes)))
        self.planeCountEntry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(basicFrame, text="x次数:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.xOrderEntry = tk.Entry(basicFrame, width=5)
        self.xOrderEntry.insert(0, str(node.xOrder))
        self.xOrderEntry.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(basicFrame, text="y次数:").grid(row=0, column=4, sticky="w", padx=5, pady=2)
        self.yOrderEntry = tk.Entry(basicFrame, width=5)
        self.yOrderEntry.insert(0, str(node.yOrder))
        self.yOrderEntry.grid(row=0, column=5, padx=5, pady=2)
        
        tk.Checkbutton(basicFrame, text="補正値", variable=self.outputCat).grid(row=0, column=6, sticky="w", padx=5, pady=2)
        
        tk.Button(basicFrame, text="次数サイズ更新", command=self.updateOrder).grid(row=1, column=0, columnspan=6, pady=10)
        
        # 係数設定フレーム（スクロール可能）
        frame = tk.Frame(self, height=120)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        frame.pack_propagate(False)
        
        canvas = tk.Canvas(frame)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
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
        
        self.planeEntries = []
        self.coeffEntries = {}
        
        planeCount = int(self.planeCountEntry.get())
        xOrder     = int(self.xOrderEntry.get())
        yOrder     = int(self.yOrderEntry.get())
        
        if planeCount <= 0 or xOrder < 0 or yOrder < 0:
            return
        
        row = 0
        for planeIndex in range(planeCount):
            # プレーン名をテキストボックスで表示
            if len(self.node.planes) <= planeIndex:
                self.planes.append(f"Plane {planeIndex}")
            
            entry = tk.Entry(self.scrollableFrame, font=("Arial", 10, "bold"), width=20)
            entry.insert(0, self.planes[planeIndex])
            entry.grid(row=row, column=0, columnspan=4, sticky="w", pady=5, padx=5)
            self.planeEntries.append(entry)
            row += 1
            
            # X軸ラベル（上部）
            for i in range(xOrder + 1):
                entry = tk.Label(self.scrollableFrame, text=f"x^{i}")
                entry.grid(row=row, column=i + 1, padx=5, pady=2)
            row += 1
            
            for j in range(yOrder + 1):
                # Y軸ラベル（左側）
                entry = tk.Label(self.scrollableFrame, text=f"y^{j}")
                entry.grid(row=row, column=0, sticky="w", padx=5, pady=2)
                
                # 係数エントリー
                for i in range(xOrder + 1):
                    entry = tk.Entry(self.scrollableFrame, width=8)
                    key = f"{planeIndex},{i},{j}"
                    if key in self.coeff:
                        entry.insert(0, str(self.coeff[key]))
                    else:
                        entry.insert(0, "0")
                    entry.grid(row=row, column=i + 1, padx=5, pady=2)
                    self.coeffEntries[key] = entry
                row += 1
            row += 1
            
            entry = tk.Label(self.scrollableFrame, text=" ")
            entry.grid(row=row, column=0, sticky="w", padx=5, pady=2)
            row += 1
    
    def onApply(self):
        planes = [entry.get() for entry in self.planeEntries]
        xOrder = int(self.xOrderEntry.get())
        yOrder = int(self.yOrderEntry.get())
        
        if planes and 0 <= xOrder and 0 <= yOrder:
            # 係数を収集
            coeff = {}
            for key, entry in self.coeffEntries.items():
                try:
                    val = float(entry.get())
                    if val != 0:
                        coeff[key] = val
                except ValueError:
                    from utils.Debug import Debug
                    Debug.log(type(self).__name__, f"Warning: Invalid coefficient value for {key}")
            
            outputCat = _OUT_CAT_AUX if self.outputCat.get() else _OUT_CAT_PRI
            self.planes = planes
            self.xOrder = xOrder
            self.yOrder = yOrder
            self.coeff  = coeff
            self.node.applySettings(outputCat, planes, xOrder, yOrder, coeff)
    
    def onClose(self):
        self.destroy()
