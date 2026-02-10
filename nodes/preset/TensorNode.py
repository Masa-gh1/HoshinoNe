'''
TensorNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

class TensorNode(FlowNode,ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_CONST
    minorType = 'tensor'
    # ノード名
    name      = '数列'
    # 入出力タイプ
    ioType    = _IO_TYPE_0N
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self.planes = ["Plane 0","Plane 1","Plane 2"]
        self.xOrder = 1
        self.yOrder = 1
        self.tensor = {"0,0,0": 1.0,"1,0,0": 1.0,"2,0,0": 1.0}  # {"planeIndex,i,j": value}
    
    def getText(self):
        """ノードのテキストを取得"""
        from utils import string_helper as sh

        constVal = ""
        for planeIndex in range(len(self.planes)):
            value = self.tensor.get(f"{planeIndex},0,0", 0)
            constVal += f" {sh.dispS(value)}"
        displayText = f"{self.name}\nP:{len(self.planes)} xy:{self.xOrder}x{self.yOrder}\n{constVal}"
        return displayText
    
    def store(self, nodeData):
        nodeData["planes"] = self.planes
        nodeData["xOrder"] = self.xOrder
        nodeData["yOrder"] = self.yOrder
        nodeData["tensor"] = self.tensor
    
    def restore(self, nodeData):
        if "planeNames" in nodeData:
            self.planes = nodeData["planeNames"]
        if "planes" in nodeData:
            self.planes = nodeData["planes"]
        if "xOrder" in nodeData:
            self.xOrder = nodeData["xOrder"]
        if "yOrder" in nodeData:
            self.yOrder = nodeData["yOrder"]
        if "tensor" in nodeData:
            self.tensor = nodeData["tensor"]
    
    def createSettingWindow(self):
        return TensorSettingsDialog(self.view.editor.root, self)
    
    def applySettings(self, planes, xOrder, yOrder, tensor):
        self.planes = planes
        self.xOrder = xOrder
        self.yOrder = yOrder
        self.tensor = tensor
        self.view.onNodeConfigChanged(self)
    
    def process(self, context=None):
        from utils.interval_helper import createHalfOpenEnd
        from base import DataBlock
        from base import FlowData
        
        self.reportProgress(context, "開始")
        
        # 指定されたサイズの tensor を作成
        planeCount = len(self.planes)
        width      = self.xOrder
        height     = self.yOrder
        
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
        planes = self.planes
        
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
            'planes': planes,
            'max_orders': [self.xOrder, self.yOrder],
        }
        
        outputFlowData = FlowData(headers)
        outputFlowData.setDimensions(width, height)
        
        # 各プレーンに数列を設定
        for planeIndex in range(planeCount):
            result = []
            for j in range(height):
                row = []
                for i in range(width):
                    key = f"{planeIndex},{i},{j}"
                    row.append(self.tensor.get(key, 0))
                result.append(row)
            dataBlock = DataBlock(result, planeIndex, 0, 0)
            outputFlowData.setBlock(dataBlock)
        
        minValue = outputFlowData.getMinValue()
        maxValue = outputFlowData.getMaxValue()
        outputFlowData.headers['display_levels'] = {'min': minValue, 'exclusive_upper': createHalfOpenEnd( minValue, maxValue)}
        
        self.flowDatas = [outputFlowData]
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        tensorStr = str(sorted(self.tensor.items()))
        config = f"{self.minorType}_{self.planes}_{self.xOrder}_{self.yOrder}_{tensorStr}"
        return hashlib.md5(config.encode()).hexdigest()

class TensorSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node   = node
        self.planes = node.planes.copy()
        self.xOrder = node.xOrder
        self.yOrder = node.yOrder
        self.tensor = node.tensor.copy()
        
        self.title(f"{node.name}設定")
        self.geometry("600x450")
        
        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(basicFrame, text="プレーン数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.planeCountEntry = tk.Entry(basicFrame, width=5)
        self.planeCountEntry.insert(0, str(len(self.planes)))
        self.planeCountEntry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(basicFrame, text="x項数:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.xOrderEntry = tk.Entry(basicFrame, width=5)
        self.xOrderEntry.insert(0, str(node.xOrder))
        self.xOrderEntry.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(basicFrame, text="y項数:").grid(row=0, column=4, sticky="w", padx=5, pady=2)
        self.yOrderEntry = tk.Entry(basicFrame, width=5)
        self.yOrderEntry.insert(0, str(node.yOrder))
        self.yOrderEntry.grid(row=0, column=5, padx=5, pady=2)
        
        tk.Button(basicFrame, text="項数更新", command=self.updateOrder).grid(row=1, column=0, columnspan=6, pady=10)
        
        # 数列設定フレーム（スクロール可能）
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
        
        # 初期数列表示
        self.updateOrder()
        
        # ウィンドウが閉じられたときのクリーンアップ
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def updateOrder(self):
        # 既存の数列エントリーをクリア
        for widget in self.scrollableFrame.winfo_children():
            widget.destroy()
        
        self.planeEntries  = []
        self.tensorEntries = {}
        
        planeCount = int(self.planeCountEntry.get())
        xOrder     = int(self.xOrderEntry.get())
        yOrder     = int(self.yOrderEntry.get())
        
        if planeCount <= 0 or xOrder <= 0 or yOrder <= 0:
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
            for i in range(xOrder):
                entry = tk.Label(self.scrollableFrame, text=f"x:{i}")
                entry.grid(row=row, column=i + 1, padx=5, pady=2)
            row += 1
            
            for j in range(yOrder):
                # Y軸ラベル（左側）
                entry = tk.Label(self.scrollableFrame, text=f"y:{j}")
                entry.grid(row=row, column=0, sticky="w", padx=5, pady=2)
                
                # 数列エントリー
                for i in range(xOrder):
                    entry = tk.Entry(self.scrollableFrame, width=8)
                    key = f"{planeIndex},{i},{j}"
                    if key in self.tensor:
                        entry.insert(0, str(self.tensor[key]))
                    else:
                        entry.insert(0, "0")
                    entry.grid(row=row, column=i + 1, padx=5, pady=2)
                    self.tensorEntries[key] = entry
                row += 1
            row += 1
            
            entry = tk.Label(self.scrollableFrame, text=" ")
            entry.grid(row=row, column=0, sticky="w", padx=5, pady=2)
            row += 1
    
    def onApply(self):
        planes = [entry.get() for entry in self.planeEntries]
        xOrder = int(self.xOrderEntry.get())
        yOrder = int(self.yOrderEntry.get())
        
        if planes and 0 < xOrder and 0 < yOrder:
            # 数列を収集
            tensor = {}
            for key, entry in self.tensorEntries.items():
                try:
                    val = float(entry.get())
                    if val != 0:
                        tensor[key] = val
                except ValueError:
                    from utils.Debug import Debug
                    Debug.log(type(self).__name__, f"Warning: Invalid tensor value for {key}")
            
            self.planes = planes
            self.xOrder = xOrder
            self.yOrder = yOrder
            self.tensor = tensor
            self.node.applySettings(planes, xOrder, yOrder, tensor)
    
    def onClose(self):
        self.destroy()
