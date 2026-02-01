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
    minorType = 'table'
    # ノード名
    name      = '表'
    # 入出力タイプ
    ioType    = _IO_TYPE_0N
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self.planes  = ["Plane 0"]
        self.columns = ["A", "B", "C"]
        self.lines   = ["1", "2", "3"]
        self.table = {"0,0,0": 0.0, "0,1,0": 0.0, "0,2,0": 0.0, # {"planeIndex,i,j": value}
                      "0,0,1": 0.0, "0,1,1": 0.0, "0,2,1": 0.0,
                      "0,0,2": 0.0, "0,1,2": 0.0, "0,2,2": 0.0,
                     }
    
    def getText(self):
        """ノードのテキストを取得"""
        from utils import string_helper as sh

        constVal = ""
        for planeIndex in range(len(self.planes)):
            value = self.table.get(f"{planeIndex},0,0", 0)
            constVal += f" {sh.dispS(value)}"
        displayText = f"{self.name}\nP:{len(self.planes)} xy:{len(self.columns)}x{len(self.lines)}\n{constVal}"
        return displayText
    
    def store(self, nodeData):
        nodeData["planes" ] = self.planes
        nodeData["columns"] = self.columns
        nodeData["lines"  ] = self.lines
        nodeData["table"  ] = self.table
    
    def restore(self, nodeData):
        if "planes" in nodeData:
            self.planes = nodeData["planes"]
        if "columns" in nodeData:
            self.columns = nodeData["columns"]
        if "lines" in nodeData:
            self.lines = nodeData["lines"]
        if "table" in nodeData:
            self.table = nodeData["table"]
    
    def createSettingWindow(self):
        return TensorSettingsDialog(self.view.editor.root, self)
    
    def applySettings(self, planes, columns, lines, table):
        self.planes  = planes
        self.columns = columns
        self.lines   = lines
        self.table   = table
        self.view.onNodeConfigChanged(self)
    
    def process(self, context=None):
        from utils.interval_helper import createHalfOpenEnd
        from base import DataBlock
        from base import FlowData
        
        self.reportProgress(context, "開始")
        
        # 指定されたサイズの table を作成
        planeCount = len(self.planes)
        width      = len(self.columns)
        height     = len(self.lines)
        
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
        
        headers = {
            'category': 'auxiliary',
            'type'    : 'table',
            'mode'    : mode,
            'planes'  : self.planes,
            'columns' : self.columns,
            'lines'   : self.lines,
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
                    row.append(self.table.get(key, 0))
                result.append(row)
            dataBlock = DataBlock(result, planeIndex, 0, 0)
            outputFlowData.setBlock(dataBlock)
        
        minValue = outputFlowData.getMinValue()
        maxValue = outputFlowData.getMaxValue()
        outputFlowData.headers['display_levels'] = {'min': minValue, 'exclusive_upper': createHalfOpenEnd( minValue, maxValue)}
        
        self.flowDatas = [outputFlowData]
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        tensorStr = str(sorted(self.table.items()))
        planeStr = str(self.planes)
        config = f"{self.minorType}_{self.planes}_{self.columns}_{self.lines}_{tensorStr}_{planeStr}"
        return hashlib.md5(config.encode()).hexdigest()

class TensorSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node    = node
        self.planes  = node.planes.copy()
        self.columns = node.columns.copy()
        self.lines   = node.lines.copy()
        self.table   = node.table.copy()
        
        self.title(f"{node.name}設定")
        self.geometry("600x450")
        
        # 基本設定フレーム
        basicFrame = tk.Frame(self)
        basicFrame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(basicFrame, text="プレーン数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.planeCountEntry = tk.Entry(basicFrame, width=5)
        self.planeCountEntry.insert(0, str(len(node.planes)))
        self.planeCountEntry.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(basicFrame, text="x項数:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.xOrderEntry = tk.Entry(basicFrame, width=5)
        self.xOrderEntry.insert(0, str(len(node.columns)))
        self.xOrderEntry.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(basicFrame, text="Y項数:").grid(row=0, column=4, sticky="w", padx=5, pady=2)
        self.yOrderEntry = tk.Entry(basicFrame, width=5)
        self.yOrderEntry.insert(0, str(len(node.lines)))
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
        
        self.planeEntries  = []
        self.columnEntries = []
        self.lineEntries   = []
        self.tableEntry    = {}
        
        planes = int(self.planeCountEntry.get())
        xOrder = int(self.xOrderEntry.get())
        yOrder = int(self.yOrderEntry.get())
        
        if planes <= 0 or xOrder <= 0 or yOrder <= 0:
            return
        
        row = 0
        for planeIndex in range(planes):
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
                if len(self.columns) <= i:
                    self.columns.append(f"{chr(ord('A') + (i%26))}")
                entry = tk.Entry(self.scrollableFrame, font=("Arial", 10, "bold"), width=8)
                entry.insert(0, self.columns[i])
                entry.grid(row=row, column=i + 1, padx=5, pady=2)
                self.columnEntries.append(entry)
            
            row += 1
            
            # 係数エントリー
            for j in range(yOrder):
                # Y軸ラベル（左側）
                if len(self.lines) <= j:
                    self.lines.append(f"{j}")
                entry = tk.Entry(self.scrollableFrame, font=("Arial", 10, "bold"), width=8)
                entry.insert(0, self.lines[j])
                entry.grid(row=row, column=0, sticky="w", padx=5, pady=2)
                self.lineEntries.append(entry)
                
                for i in range(xOrder):
                    entry = tk.Entry(self.scrollableFrame, width=8)
                    key = f"{planeIndex},{i},{j}"
                    if key in self.table:
                        entry.insert(0, str(self.table[key]))
                    else:
                        entry.insert(0, "0")
                    entry.grid(row=row, column=i + 1, padx=5, pady=2)
                    self.tableEntry[key] = entry
                
                row += 1
            
            row += 1
    
    def onApply(self):
        planes = []
        for entry in self.planeEntries:
            planes.append(entry.get())
        
        columns = []
        for entry in self.columnEntries:
            columns.append(entry.get())
        
        lines = []
        for entry in self.lineEntries:
            lines.append(entry.get())
        
        if self.planes and self.columns and self.lines:
            # 係数を収集
            table = {}
            for key, entry in self.tableEntry.items():
                try:
                    val = float(entry.get())
                    if val != 0:
                        table[key] = val
                except ValueError:
                    print(f"Warning: Invalid coefficient value for {key}")
            
            self.planes  = planes
            self.columns = columns
            self.lines   = lines
            self.table   = table
            self.node.applySettings(self.planes, self.columns, self.lines, self.table)
    
    def onClose(self):
        self.destroy()
