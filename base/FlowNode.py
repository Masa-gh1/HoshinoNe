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
        self.connections = []
        self.flowDatas = []
        self.dragging = False
        self.startX = 0
        self.startY = 0
        self._lastInputHash = None
        self._lastConfigHash = None
        self.filetypes = [("CSV files", "*.csv")]
        self.defaultextension = ".csv"
        self.createVisual()
        self.bindEvents()
    
    def createVisual(self):
        color = self.getColor()
        self.rect = self.canvas.create_rectangle(self.x-50, self.y-20, self.x+50, self.y+20, fill=color, outline='black')
        self.label = self.canvas.create_text(self.x, self.y, text=self.text, font=('Arial', 8))
    
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
    
    def needsReprocessing(self, inputNodes):
        """再処理が必要かどうかを判定"""
        # ハッシュを計算
        inputHash = self.getInputHashe(inputNodes)
        configHash = self.getConfigHash()
        
        # 初回実行または変更ありの場合は再処理
        return (self._lastInputHash != inputHash 
                or self._lastConfigHash != configHash 
                or 0 == len(self.flowDatas))
    
    def updateExecutionHashes(self, inputNodes):
        """実行後にハッシュを更新"""
        # ハッシュを更新
        self._lastInputHash = self.getInputHashe(inputNodes)
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
        filePaths = filedialog.askopenfilenames(filetypes=self.filetypes)
        if not filePaths:
            raise ValueError("ファイルが選択されませんでした")
        
        self.setFilePaths(filePaths)
        self.updateNodeText()
        
    def selectOutputFile(self):
        outputPath = filedialog.asksaveasfilename(
            defaultextension=self.defaultextension,
            filetypes=self.filetypes
        )
        if not outputPath:
            raise ValueError("出力ファイルが選択されませんでした")
        
        self.filePath = outputPath
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
        if hasattr(self, 'filePaths') or hasattr(self, 'filePath'):
            menu.add_command(label="編集", command=self.onEdit)
            menu.add_separator()
        menu.add_command(label="削除", command=lambda: self.editor.deleteNode(self))
        menu.post(event.x_root, event.y_root)
    
    def onEdit(self):
        """編集メニューから呼び出される編集処理"""
        try:
            if hasattr(self, 'filePaths'):
                self.selectFiles()
            elif hasattr(self, 'filePath'):
                self.selectOutputFile()
            
            newHash = self.getConfigHash()
            if newHash != self._lastConfigHash:
                self.editor.onNodeConfigChanged(self)
            else:
                self.editor.highlightReprocessingNodes()
        except ValueError:
            pass
