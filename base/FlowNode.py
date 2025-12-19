'''
FlowNode base class

@author: Masakazu Inoue
'''

import hashlib
import os
import tkinter as tk
from tkinter import filedialog
from .FlowData import FlowData

class FlowNode:
    def __init__(self, canvas, editor, x, y, nodeType, text):
        self.canvas = canvas
        self.editor = editor
        self.x, self.y = x, y
        self.type = nodeType
        self.text = text
        self.outputNodes = [] # 接続先ノードの一覧
        self.inputNodes = []  # 入力元ノードの一覧
        self.flowDatas = []   # 処理結果データ
        self.dragging = False
        self.startX = 0
        self.startY = 0
        self._lastInputHash = None
        self._lastConfigHash = None
        self.fileTypes = [("CSV files", "*.csv")]
        self.defaultOutputExtension = ".csv"
        self.createVisual()
        self.bindEvents()
    
    def createVisual(self):
        color = self.getColor()
        self.rect = self.canvas.create_rectangle(self.x-50, self.y-20, self.x+50, self.y+20, fill=color, outline='black')
        self.label = self.canvas.create_text(self.x, self.y, text=self.text, font=('Arial', 8))
    
    _color_const = 'lightcyan'    # 定数系 cyan
    _color_coff  = 'lightblue'    # 係数系 blue
    _color_func  = 'plum'         # 関数系 magenta
    _color_op    = 'pink'         # 演算系 red
    _color_io    = 'lightyellow'  # 入出系 yellow
    _color_xxx   = 'lightgreen'   # 予約  
    
    def getColor(self):
        return 'lightgreen'
    
    def bindEvents(self):
        self.canvas.tag_bind(self.rect, '<Button-1>', self.onClick)
        self.canvas.tag_bind(self.label, '<Button-1>', self.onClick)
        self.canvas.tag_bind(self.rect, '<B1-Motion>', self.onDrag)
        self.canvas.tag_bind(self.label, '<B1-Motion>', self.onDrag)
        self.canvas.tag_bind(self.rect, '<ButtonRelease-1>', self.onRelease)
        self.canvas.tag_bind(self.label, '<ButtonRelease-1>', self.onRelease)
        self.canvas.tag_bind(self.rect, '<Button-3>', self.onRightClick)
        self.canvas.tag_bind(self.label, '<Button-3>', self.onRightClick)
        self.canvas.tag_bind(self.rect, '<Double-Button-1>', self.onDoubleClick)
        self.canvas.tag_bind(self.label, '<Double-Button-1>', self.onDoubleClick)
    
    def process(self, context):
        # サブクラスでオーバーライドする
        raise NotImplementedError("サブクラスで実装してください")
    
    def processPreviewOnly(self):
        """プレビュー専用処理（自ノードのみ）"""
        if not self.inputNodes or not self.inputNodes[0].flowDatas:
            return
        
        try:
            context = {}
            self.process(context)
            
            # 開いているResultWindowがあれば直接更新
            if hasattr(self, '_result_window') and self._result_window.winfo_exists():
                self.editor._updateResultWindow(self)
        except Exception as e:
            print(f"プレビューエラー: {e}")
    
    def needsReprocessing(self):
        """再処理が必要かどうかを判定"""
        # ハッシュを計算
        inputHash = self.getInputHashe(self.inputNodes)
        configHash = self.getConfigHash()
        
        # 初回実行または変更ありの場合は再処理
        return (self._lastInputHash != inputHash 
                or self._lastConfigHash != configHash 
                or 0 == len(self.flowDatas))
    
    def updateExecutionHashes(self):
        """実行後にハッシュを更新"""
        # ハッシュを更新
        self._lastInputHash = self.getInputHashe(self.inputNodes)
        self._lastConfigHash = self.getConfigHash()
    
    def getInputHashe(self, inputNodes):
        inputHashes = []
        for node in inputNodes:
            inputHashes.append(str(id(node)))
            for flowData in node.flowDatas:
                inputHashes.append(str(id(flowData)))
        return hashlib.md5(''.join(inputHashes).encode()).hexdigest()
    
    def getConfigHash(self):
        """ノード固有の設定ハッシュを取得（サブクラスでオーバーライド）"""
        return hashlib.md5(str(self.type).encode()).hexdigest()
    
    def reportProgress(self, context, message, current=None, total=None):
        """処理経過を報告"""
        if 'progress_callback' in context:
            context['progress_callback'](message, current, total)
    
    def selectFiles(self):
        filePaths = filedialog.askopenfilenames(filetypes=self.fileTypes)
        
        self.setFilePaths(filePaths)
        self.updateNodeText()
        
    def selectOutputFile(self):
        outputPath = filedialog.asksaveasfilename( defaultextension=self.defaultOutputExtension, filetypes=self.outputFileTypes)
        
        self.outputFilePath = outputPath
        self.updateNodeText()
    
    def updateNodeText(self):
        """ノードのテキストを更新（サブクラスでオーバーライド）"""
        self.editor.updateNodeText(self, self.text)
    
    def onClick(self, event):
        self.startX = event.x
        self.startY = event.y
        self.dragging = False
    
    def onDrag(self, event):
        if hasattr(self, 'isDoubleClick') and self.isDoubleClick:
            return
        
        if not self.dragging:
            # ドラッグ開始の判定
            dx = abs(event.x - self.startX)
            dy = abs(event.y - self.startY)
            if dx > 5 or dy > 5:
                self.dragging = True
        
        if self.dragging:
            # ノードを移動
            self.editor.unselectNode()
            dx = event.x - self.startX
            dy = event.y - self.startY
            self.canvas.move(self.rect, dx, dy)
            self.canvas.move(self.label, dx, dy)
            self.x += dx
            self.y += dy
            self.startX = event.x
            self.startY = event.y
            
            # canvasの自動拡大/縮小をチェック
            self.editor.adjustCanvasSize()
            
            self.editor.updateConnections()
            self.editor.highlightReprocessingNodes()
    
    def onRelease(self, event):
        if hasattr(self, 'isDoubleClick') and self.isDoubleClick:
            self.isDoubleClick = False
            return
        
        if not self.dragging:
            # クリックとして処理
            self.editor.selectNode(self)
        self.dragging = False
    
    def onDoubleClick(self, event):
        self.editor.unselectNode()
        self.isDoubleClick = True
        
        """ダブルクリックで処理結果を表示"""
        self.editor.showNodeResult(self)
    
    def onRightClick(self, event):
        menu = tk.Menu(self.canvas, tearoff=0)
        if hasattr(self, 'setFilePaths'):
            menu.add_command(label="ファイル選択", command=self.onSelectFiles)
        if hasattr(self, 'setOutputFilePath'):
            menu.add_command(label="出力ファイル選択", command=self.onSelectOutputFile)
        if hasattr(self, 'onEdit'):
            menu.add_command(label="設定", command=self.onEdit)
        menu.add_separator()
        menu.add_command(label="削除", command=lambda: self.editor.deleteNode(self))
        menu.post(event.x_root, event.y_root)
    
    def onSelectFiles(self):
        """編集メニューから呼び出される編集処理"""
        try:
            self.selectFiles()
            newHash = self.getConfigHash()
            if newHash != self._lastConfigHash:
                self.editor.onNodeConfigChanged(self)
        except ValueError:
            pass
        
    def onSelectOutputFile(self):
        """編集メニューから呼び出される編集処理"""
        try:
            self.selectOutputFile()
            newHash = self.getConfigHash()
            if newHash != self._lastConfigHash:
                self.editor.onNodeConfigChanged(self)
        except ValueError:
            pass
