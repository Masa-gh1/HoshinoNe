'''
FlowNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import ABC as AbstractBaseClass, abstractmethod
import hashlib
import traceback
import sys
import tkinter as tk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MAX_WORKERS
from main.ResultWindow import ResultWindow
from utils.ThreadPool import ProcessExecutor

class FlowNode(AbstractBaseClass):
    def __init__(self, canvas, editor, x, y, nodeType, text, **kwargs):
        self.canvas = canvas
        self.editor = editor
        self._binds = []
        self._window = {}
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
    
    _color_func  = 'plum'         # 関数系 magenta
    _color_op    = 'pink'         # 演算系 red
    _color_io    = 'lightyellow'  # 入出系 yellow
    _color_xxx   = 'lightgreen'   # 予約 green
    _color_const = 'lightcyan'    # 定数系 blue
    _color_yyy   = 'lightblue'    # 予約 cyan
    _color_util  = 'lightgrey'    # ユーティリティ grey
    
    def getColor(self):
        return 'lightgreen'
    
    def createVisual(self):
        color = self.getColor()
        self.rect = self.canvas.create_rectangle(self.x-50, self.y-20, self.x+50, self.y+20, fill=color, outline='black')
        self.label = self.canvas.create_text(self.x, self.y, text=self.text, font=('Arial', 8))
    
    def bindEvents(self):
        self.canvasBind('<Button-1>'       , self.onClick      )
        self.canvasBind('<B1-Motion>'      , self.onDrag       )
        self.canvasBind('<ButtonRelease-1>', self.onRelease    )
        self.canvasBind('<Button-3>'       , self.onRightClick )
        self.canvasBind('<Double-Button-1>', self.onDoubleClick)
    
    def canvasBind(self, sequence, callback):
        fid1 = self.canvas.tag_bind( self.rect , sequence, callback)
        fid2 = self.canvas.tag_bind( self.label, sequence, callback)
        self._binds.append((sequence,fid1))
        self._binds.append((sequence,fid2))
    
    def cleanUp(self):
        # 接続の初期化
        self.outputNodes = [] # 接続先ノードの一覧
        self.inputNodes = []  # 入力元ノードの一覧

        # データの初期化
        self.flowDatas = []   # 処理結果データ
        
        # UIウィンドウを閉じる
        for window in self._window.values():
            window.destroy()
        self._window = {}
        
        # bindを削除
        for sequence,fid in self._binds:
            self.canvas.unbind(sequence,fid)
        self._binds = []
            
        # ノード図を削除
        self.canvas.delete(self.rect)
        self.canvas.delete(self.label)
        self.canvas = None
        self.rect = None
        self.label = None

        self.editor = None
    
    @abstractmethod
    def process(self, context=None):
        """ノードの処理を実行（サブクラスで実装）
        
        Args:
            context: 処理コンテキスト（progress_callbackなど）
        """
        pass
    
    def execute(self, context=None):
        """ノードの処理を実行"""
        self.process(context)
        self.updateExecutionHashes()
        self.editor.root.after(0,self.updateResult)

    def preview(self):
        """プレビュー専用処理（ノード個別実行）"""
        if not self.inputNodes or not self.inputNodes[0].flowDatas:
            return
        
        try:
            with(ThreadPoolExecutor(max_workers=MAX_WORKERS) as processExecutor):
                ProcessExecutorInNode .setExecutor(processExecutor) # グローバルにスレッドプールを提供
                context = {}
                self.process(context)
            self.editor.root.after(0,self.updateResult)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
    
    def needsReprocessing(self):
        """再処理が必要かどうかを判定"""
        # ハッシュを計算
        inputHash = self.getInputHashe()
        configHash = self.getConfigHash()
        
        # 初回実行または変更ありの場合は再処理
        return (self._lastInputHash != inputHash 
                or self._lastConfigHash != configHash 
                or 0 == len(self.flowDatas))
    
    def updateExecutionHashes(self):
        """実行後にハッシュを更新"""
        # ハッシュを更新
        self._lastInputHash = self.getInputHashe()
        self._lastConfigHash = self.getConfigHash()
    
    def getInputHashe(self):
        inputHashes = []
        for node in self.inputNodes:
            inputHashes.append(str(id(node)))
            for flowData in node.flowDatas:
                inputHashes.append(str(id(flowData)))
        return hashlib.md5(':'.join(inputHashes).encode()).hexdigest()
    
    def getConfigHash(self):
        """ノード固有の設定ハッシュを取得（サブクラスでオーバーライド）"""
        return hashlib.md5(str(self.type).encode()).hexdigest()
    
    def store(self, nodeData):
        """ノード固有の設定 nodeData に保存（サブクラスでオーバーライド）
        
        Args:
            nodeData: 保存先
        """
        pass
    
    def restore(self, nodeData):
        """ノード固有の設定 nodeData から復元（サブクラスでオーバーライド）
        
        Args:
            nodeData: 復元元
        """
        pass
    
    def serialize(self):
        """ノードをシリアライズ"""
        serial = {
            "type": self.type,
            "text": self.text,
            "x"   : self.x,
            "y"   : self.y,
        }
        self.store(serial)
        serial["connections"] = [id(node) for node in self.outputNodes]
        return serial
    
    def deserialize(self, serial):
        """ノードをデシリアライズ"""
        self.x = serial["x"]
        self.y = serial["y"]
        self.restore(serial)

    def reportProgress(self, context, message, current=None, total=None):
        """処理経過を報告"""
        if context and 'progress_callback' in context:
            context['progress_callback'](message, current, total)
    
    def selectFiles(self):
        filePaths = filedialog.askopenfilenames(filetypes=self.fileTypes)
        if filePaths:
            self.setFilePaths(filePaths)
            self.updateNodeText()
        
    def selectOutputFile(self):
        outputPath = filedialog.asksaveasfilename( defaultextension=self.defaultOutputExtension, filetypes=self.outputFileTypes)
        if outputPath:
            self.outputFilePath = outputPath
            self.updateNodeText()
    
    def updateNodeText(self):
        """ノードのテキストを更新（サブクラスでオーバーライド）"""
        self.editor.updateNodeText(self, self.text)
    
    def updatePosition(self):
        self.canvas.coords(self.rect, self.x-50, self.y-20, self.x+50, self.y+20)
        self.canvas.coords(self.label, self.x, self.y)

    def updatePositionAndAppearance(self):
        """位置と外観を更新"""
        self.updatePosition()
        self.updateNodeText()

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
                # ドラッグ開始時にハイライトを消す
                self.editor.clearSelectedHighlight()
                self.editor.clearReprocessingHighlights()
                # ドラッグ開始時にノードをノード/トレイ群の最前に移動
                self.editor._placeItemBeforeConnections(self.rect, self.label)
        
        if self.dragging:
            # ノードを移動
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
    
    def onRelease(self, event):
        if hasattr(self, 'isDoubleClick') and self.isDoubleClick:
            self.isDoubleClick = False
            return
        
        if not self.dragging:
            # クリックとして処理
            self.editor.selectNode(self)
        self.dragging = False
    
    def onDoubleClick(self, event):
        """ダブルクリックで処理結果を表示"""
        self.editor.unselectNode()
        self.isDoubleClick = True
        
        self.onResult()
    
    def onRightClick(self, event):
        if "menu" in self._window and self._window["menu"].winfo_exists():
            self._window["menu"].post(event.x_root, event.y_root)
        else:
            menu = tk.Menu(self.canvas, tearoff=0)
            
            if hasattr(self, 'setFilePaths'):
                menu.add_command(label="ファイル選択", command=self.onSelectFiles)
            if hasattr(self, 'setOutputFilePath'):
                menu.add_command(label="出力ファイル選択", command=self.onSelectOutputFile)
            if hasattr(self, 'onEdit'):
                menu.add_command(label="設定", command=self._onEdit)
                
            if None != menu.index(tk.END):
                menu.add_separator()
            
            menu.add_command(label="削除", command=lambda: self.editor.deleteNode(self))
            
            self._window["menu"] = menu
        
            menu.post(event.x_root, event.y_root)
    
    def onSelectFiles(self):
        """編集メニューから呼び出される編集処理"""
        self.selectFiles()
        newHash = self.getConfigHash()
        if newHash != self._lastConfigHash:
            self.editor.onNodeConfigChanged(self)
        
    def onSelectOutputFile(self):
        """編集メニューから呼び出される編集処理"""
        self.selectOutputFile()
        newHash = self.getConfigHash()
        if newHash != self._lastConfigHash:
            self.editor.onNodeConfigChanged(self)

    def _onEdit(self):
        """編集メニューから呼び出される編集処理"""
        if not hasattr(self, 'onEdit'):
            pass
        elif not 'settings_dialog' in self._window:
            self._window["settings_dialog"] = self.onEdit()
        elif not self._window["settings_dialog"].winfo_exists():
            self._window["settings_dialog"].destroy()
            self._window["settings_dialog"] = self.onEdit()
        else:
            self._window["settings_dialog"].lift()
    
    def onResult(self):
        """ノードの処理結果を表示"""
        if not 'result_window' in self._window:
            self._window["result_window"] = ResultWindow(self.editor.root, self)
        elif not self._window["result_window"].winfo_exists():
            self._window["result_window"].destroy()
            self._window["result_window"] = ResultWindow(self.editor.root, self)
        else:
            self._window["result_window"].lift()

    def updateResult(self):
        if( 'result_window' in self._window
          and self._window["result_window"].winfo_exists()
          ):
            self._window["result_window"].updateResult()
    
    def liftWindow(self):
        """ウィンドウを最前面に表示"""
        for window in self._window.values():
            window.lift()
            window.focus_force()

    def lift(self):
        """ノードを最前面に表示"""
        self.canvas.tag_raise(self.rect)
        self.canvas.tag_raise(self.label)
