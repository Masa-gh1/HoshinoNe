'''
Flow Editor - Visual Flow-based Image Processing Tool

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import sys
import os
import traceback

from Version import VERSION
from base.FlowNode_CONST import *
from base import FlowControl
from base import FlowFile
from nodes import NodeFactory
from .Tray import Tray
from utils.ThreadPool import CoalescingExecutor

class FlowEditor:
    def __init__(self, root, name):
        self.root = root
        self.name = name
        self.root.title(f"{self.name} - {VERSION}")
        self.autoExecute = tk.BooleanVar(value=False)
        self.reprocessingHighlights = []
        self.selectedHighlight = None
        self.selectedNode = None

        self.nodes = []
        self.trays = []
        self.connectionLines = [] # (fromNode, toNode, line)
        self.flowControl     = FlowControl()

        self.applicationHome = None
        self.currentFlowPath = None
        self.lastDirectory   = None
        
        self.take           = 0
        self.maxObjectCount = 0

        self.createWidgets()
    
    def createWidgets(self):
        # ツールバー
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(toolbar, text="ホーム", command=self.goHome, bg='lightgray').pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="最前面", command=self.bringChildWindowsToFront, bg='lightgray').pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="読込", command=self.loadFlow, bg='orange').pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="保存", command=self.saveFlow, bg='lightgreen').pack(side=tk.LEFT, padx=2)
        tk.Checkbutton(toolbar, text="自動実行", variable=self.autoExecute).pack(side=tk.RIGHT, padx=2)
        tk.Button(toolbar, text="中断", command=self.stopFlow, bg='pink').pack(side=tk.RIGHT, padx=2)
        tk.Button(toolbar, text="実行", command=self.executeFlow, bg='lightblue').pack(side=tk.RIGHT, padx=2)
        
        # キャンバスフレーム
        canvasFrame = tk.Frame(self.root)
        canvasFrame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # キャンバスとスクロールバー
        self.canvas = tk.Canvas(canvasFrame, width=800, height=400, bg='white')
        vScrollbar = tk.Scrollbar(canvasFrame, orient=tk.VERTICAL, command=self.canvas.yview)
        hScrollbar = tk.Scrollbar(canvasFrame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vScrollbar.set, xscrollcommand=hScrollbar.set)
        
        # グリッド配置
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vScrollbar.grid(row=0, column=1, sticky="ns")
        hScrollbar.grid(row=1, column=0, sticky="ew")
        
        # グリッドの重み設定
        canvasFrame.grid_rowconfigure(0, weight=1)
        canvasFrame.grid_columnconfigure(0, weight=1)
        
        # キャンバスのイベントバインディング
        self.canvas.bind('<ButtonRelease-1>', self.onCanvasRelease)
        self.canvas.bind('<ButtonRelease-3>', self.onCanvasRightRelease)
        self.canvas.bind('<MouseWheel>', self.onMouseWheel)
        self.canvas.bind('<Shift-MouseWheel>', self.onShiftMouseWheel)
        
        # 右クリックメニュー
        self.contextMenu = tk.Menu(self.root, tearoff=0)
        for nodeType, label in NodeFactory.getMenuItems():
            if '---' in nodeType:
                self.contextMenu.add_separator()
            else:
                self.contextMenu.add_command(label=label, command=lambda nt=nodeType: self.addNodeAtPosition(nt))
        
        self.contextMenu.add_separator()
        self.contextMenu.add_command(label="トレイ作成", command=self.addTrayAtPosition)
        self.contextMenu.add_command(label="別のフローをインポート", command=self.addFlowAtPosition)
        
        # 使い方説明
        infoLabel = tk.Label(self.root, text="使い方: 1.右クリックでノード/トレイ追加 2.ドラッグで移動 3.クリックで接続 4.実行 5.ダブルクリックで結果表示", bg='lightyellow')
        infoLabel.pack(fill=tk.X, padx=5, pady=2)
        
        # 結果表示
        self.resultText = tk.Text(self.root, height=8)
        self.resultText.pack(fill=tk.X, padx=5, pady=5)
        
        # 処理経過表示エリア
        self.progressFrame = tk.Frame(self.root)
        self.progressFrame.pack(fill=tk.X, padx=5, pady=2)
        
        # MAX_NODE_WORKERS数のプログレスバーを事前作成
        self.progressBars = []
        for i in range(self.flowControl.getMaxNodeWorkers()):
            frame = tk.Frame(self.progressFrame)
            frame.pack(fill=tk.X, pady=1)
            
            label = tk.Label(frame, text="待機中", anchor=tk.W, width=20)
            label.pack(side=tk.LEFT)
            
            bar = ttk.Progressbar(frame, mode='determinate')
            bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
            
            self.progressBars.append({'frame': frame, 'label': label, 'bar': bar})
        
        self.activeProgressBars = {}
        
        # ステータス表示（一番下段）
        statusFrame = tk.Frame(self.root, bg='lightgray', relief=tk.SUNKEN, bd=1)
        statusFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        
        self.statusLabel = tk.Label(statusFrame, text="状態: 待機中", bg='lightgray', anchor=tk.W)
        self.statusLabel.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.gcButton = tk.Button(statusFrame, text="ゴミ掃除", command=self.forceGarbageCollection,
                                 bg='lightgray', relief=tk.FLAT, padx=5)
        self.gcButton.bind('<Double-Button-3>', self.toggleDebugMode)
        self.gcButton.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.usageLabel = tk.Label(statusFrame, text="Cache: 0B storage: 0B", bg='lightgray', anchor=tk.E)
        self.usageLabel.pack(side=tk.RIGHT)
        
        # キャッシュ統計の定期更新
        self.startUpdateCacheStats()
    
    def bringChildWindowsToFront(self):
        """子画面を最前面に持ち上げる"""
        # 各ノードの設定ダイアログをチェック
        for node in self.nodes:
            node.view.liftWindow()
        
        self.statusLabel.config(text=f"状態: 子画面を最前面に移動")
    
    def onCanvasRightRelease(self, event):
        # ノードやトレイ以外の場所をクリックした場合のみメニューを表示
        isItemClick = False

        # canvas座標に変換
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        clickedItems = self.canvas.find_overlapping(x, y, x, y)
        if clickedItems:
            clickedItem = clickedItems[0]
            for node in self.nodes:
                if clickedItem == node.view.rect or clickedItem == node.view.label:
                    isItemClick = True
                    break
            if not isItemClick:
                for tray in self.trays:
                    if clickedItem == tray.rect or clickedItem == tray.label:
                        isItemClick = True
                        break
        
        if not isItemClick:
            self.rightClickX = event.x
            self.rightClickY = event.y
            self.contextMenu.post(event.x_root, event.y_root)
    
    def addNodeAtPosition(self, nodeType):
        from nodes import NodeFactory
        x = self.canvas.canvasx(self.rightClickX)
        y = self.canvas.canvasy(self.rightClickY)
        node = NodeFactory.createNode(nodeType, self.canvas, self, x, y)
        if node:
            self.nodes.append(node)
            self._placeItemBeforeConnections(node.view.rect, node.view.label)
            node.view.updatePositionAndAppearance(node)
    
    def addTrayAtPosition(self):
        x = self.canvas.canvasx(self.rightClickX)
        y = self.canvas.canvasy(self.rightClickY)
        tray = Tray(self.canvas, self, x, y)
        self.trays.append(tray)
        self._placeItemBeforeConnections(tray.rect, tray.label)
        self.updateAllTrayAppearance()

    def addFlowAtPosition(self):
        """右クリック位置にフローをインポート"""
        # クリック位置をcanvas座標に変換
        clickX = self.canvas.canvasx(self.rightClickX)
        clickY = self.canvas.canvasy(self.rightClickY)
        
        # 追加モードで読み込み
        self.loadFlow(targetX=clickX, targetY=clickY, appendMode=True, initialdir=os.path.join(self.applicationHome, "subFlow"))

    def updateAllTrayAppearance(self):
        """全トレイの外観を更新"""
        for tray in self.trays:
            tray.updateDepthAppearance()
    
    def _placeItemBeforeConnections(self, *items):
        """アイテムを接続線より後ろに配置"""
        # Z-orderでソートして順序を保持
        allItems = self.canvas.find_all()
        items = sorted(items, key=lambda item: allItems.index(item))
        
        if self.connectionLines:
            target = self.connectionLines[0][2]
            for item in items:
                self.canvas.tag_lower(item, target)
        else:
            for item in items:
                self.canvas.tag_raise(item)
    
    def clearSelectedHighlight(self):
        """選択ハイライトを消す"""
        if self.selectedHighlight:
            self.canvas.delete(self.selectedHighlight)
            self.selectedHighlight = None
    
    def clearReprocessingHighlights(self):
        """再処理ハイライトを消す"""
        for highlight in self.reprocessingHighlights:
            self.canvas.delete(highlight)
        self.reprocessingHighlights = []
    
    def deleteTray(self, tray):
        # トレイ上のアイテムを取得
        containedNodes = tray.getVisuallyContainedNodes()
        containedTrays = tray.getVisuallyContainedTrays()
        
        # トレイ上のノードを削除
        for node in containedNodes:
            self.deleteNode(node)
        
        # トレイ上の他のトレイを再帰的に削除
        for containedTray in containedTrays:
            self.deleteTray(containedTray)
        
        # トレイ自身を削除
        self.canvas.delete(tray.rect)
        self.canvas.delete(tray.label)
        if tray in self.trays:
            self.trays.remove(tray)
        # 残りのトレイの外観を更新
        self.updateAllTrayAppearance()
    
    def adjustCanvasSize(self):
        """ノードとトレイの位置に合わせてcanvasサイズを調整"""
        if not self.nodes and not self.trays:
            return
        
        # 全ノードとトレイの範囲を計算
        items = []
        for node in self.nodes:
            items.extend([node.view.x - 60, node.view.x + 60, node.view.y - 30, node.view.y + 30])
        for tray in self.trays:
            items.extend([tray.x - tray.width //2, tray.x + tray.width //2,
                          tray.y - tray.height//2, tray.y + tray.height//2])
        
        if not items:
            return
            
        minX = min(items[::4] + items[1::4])
        maxX = max(items[::4] + items[1::4])
        minY = min(items[2::4] + items[3::4])
        maxY = max(items[2::4] + items[3::4])
        
        # マージンを追加
        margin = 50
        minX -= margin
        maxX += margin
        minY -= margin
        maxY += margin
        
        # 現在のcanvasサイズを取得
        currentWidth = self.canvas.winfo_width()
        currentHeight = self.canvas.winfo_height()
        
        # 必要なサイズを計算
        requiredWidth = max(800, maxX - minX)
        requiredHeight = max(400, maxY - minY)
        
        # サイズを更新
        if requiredWidth != currentWidth or requiredHeight != currentHeight:
            self.canvas.config(scrollregion=(minX, minY, maxX, maxY))
    
    def _getConnectionPoints(self, fromNode, toNode):
        """ノード間の接続点を取得する"""
        dx = toNode.view.x - fromNode.view.x
        dy = toNode.view.y - fromNode.view.y
        
        x1, y1 = fromNode.view.getConnectionPoint(dx, dy)
        x2, y2 = toNode.view.getConnectionPoint(-dx, -dy)

        cat = fromNode.getOutputCategory()
        if _OUT_CAT_PRI == cat:
            color = "red"
        elif _OUT_CAT_AUX == cat:
            color = "black"
        else:
            color = "gray"
        
        count = fromNode.getOutputCount()
        if count <= 1:
            arrowshape=(8, 12, 4) # 中央の長さ,端の長さ,半幅
        elif count <= 5:
            arrowshape=(8, 8, 2+count)
        else:
            arrowshape=(8, 8, 8)

        return x1, y1, x2, y2, color, arrowshape
    
    def createConnections(self, fromNode, toNode):
        """接続線を作成"""
        x1, y1, x2, y2, color, arrowshape = self._getConnectionPoints(fromNode, toNode)
        line = self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, width=2, fill=color, arrowshape=arrowshape)
        self.connectionLines.append((fromNode, toNode, line))
        return line
    
    def removeConnections(self, node, nodeB=None):
        """接続線を削除"""
        for i, (fromNode, toNode, line) in reversed(list(enumerate(self.connectionLines))):
            if nodeB:
                if node == fromNode and nodeB == toNode:
                    self.canvas.delete(line)
                    del self.connectionLines[i]
            else:
                if node == fromNode or node == toNode:
                    self.canvas.delete(line)
                    del self.connectionLines[i]
    
    def updateConnections(self):
        """接続線の位置を更新"""
        for fromNode, toNode, line in self.connectionLines:
            x1, y1, x2, y2, color, arrowshape = self._getConnectionPoints(fromNode, toNode)
            self.canvas.coords(line, x1, y1, x2, y2)
            self.canvas.itemconfig(line, fill=color, arrowshape=arrowshape)
    
    def selectNode(self, node):
        self.statusLabel.config(text=f"ノードクリック: {node.name}")
        
        # 前の選択をクリア
        self.clearSelectedHighlight()
        
        if self.selectedNode and self.selectedNode != node:
            # 既存の接続をチェック（順方向と逆方向）
            if node in self.selectedNode.outputNodes:
                # 順方向接続を削除
                self.selectedNode.outputNodes.remove(node)
                node.inputNodes.remove(self.selectedNode)
                # 接続線を削除
                self.removeConnections(self.selectedNode, node)
                self.updateConnections()
                # 削除情報を表示
                self.resultText.delete(1.0, tk.END)
                self.resultText.insert(tk.END, f"接続削除: {self.selectedNode.name} → {node.name}\n")
                self.resultText.see(tk.END)
                self.statusLabel.config(text=f"接続削除: {self.selectedNode.name} → {node.name}")
            elif self.selectedNode in node.outputNodes:
                # 逆方向接続を削除
                node.outputNodes.remove(self.selectedNode)
                self.selectedNode.inputNodes.remove(node)
                # 接続線を削除
                self.removeConnections(node, self.selectedNode)
                self.updateConnections()
                # 削除情報を表示
                self.resultText.delete(1.0, tk.END)
                self.resultText.insert(tk.END, f"接続削除: {node.name} → {self.selectedNode.name}\n")
                self.resultText.see(tk.END)
                self.statusLabel.config(text=f"接続削除: {node.name} → {self.selectedNode.name}")
            else:
                # 新規接続を作成
                self.selectedNode.outputNodes.append(node)
                node.inputNodes.append(self.selectedNode)
                self.createConnections(self.selectedNode, node)
                self.updateConnections()
                # 接続情報を表示
                self.resultText.delete(1.0, tk.END)
                self.resultText.insert(tk.END, f"接続: {self.selectedNode.name} → {node.name}\n")
                self.resultText.see(tk.END)
                self.statusLabel.config(text=f"接続完了: {self.selectedNode.name} → {node.name}")
            
            self.selectedNode = None
            
            # 強調表示更新
            self.highlightReprocessingNodes()
        else:
            # ノードを選択
            self.selectedNode = node
            # 選択状態を表示
            x1, y1, x2, y2 = node.view.getShapeBounds()
            self.selectedHighlight = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline='red', width=3, fill=''
            )
            self.resultText.delete(1.0, tk.END)
            self.resultText.insert(tk.END, f"選択中: {node.name}\n次のノードをクリックして接続")
            self.resultText.see(tk.END)
            self.statusLabel.config(text=f"選択中: {node.name}")
    
    def unselectNode(self):
        if self.selectedNode:
            self.clearSelectedHighlight()
            self.selectedNode = None
            self.resultText.delete(1.0, tk.END)
            self.resultText.insert(tk.END, "選択をクリアしました")
            self.resultText.see(tk.END)
            self.statusLabel.config(text="状態: 選択クリア")
    
    def onCanvasRelease(self, event):
        # ノードやトレイ以外の場所をクリックした場合のみ選択をクリア
        isItemClick = False

        # canvas座標に変換
        canvasX = self.canvas.canvasx(event.x)
        canvasY = self.canvas.canvasy(event.y)
        
        clickedItems = self.canvas.find_overlapping(canvasX, canvasY, canvasX, canvasY)
        if clickedItems:
            clickedItem = clickedItems[0]
            for node in self.nodes:
                if clickedItem == node.view.rect or clickedItem == node.view.label:
                    isItemClick = True
                    break
            if not isItemClick:
                for tray in self.trays:
                    if clickedItem == tray.rect or clickedItem == tray.label:
                        isItemClick = True
                        break
        
        if not isItemClick:
            self.unselectNode()
    
    def onMouseWheel(self, event):
        """マウスホイールで縦スクロール"""
        # スクロール範囲をチェック
        scrollRegion = self.canvas.cget('scrollregion')
        if scrollRegion:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def onShiftMouseWheel(self, event):
        """Shift+マウスホイールで横スクロール"""
        # スクロール範囲をチェック
        scrollRegion = self.canvas.cget('scrollregion')
        if scrollRegion:
            self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def onNodeClick(self, view):
        for node in self.nodes:
            if view == node.view:
                self.selectNode(node)
                break
    
    def onNodeDoubleClick(self, view):
        self.unselectNode()
        for node in self.nodes:
            if view == node.view:
                node.view.onResult(node)
                break
    
    def onNodeRightClick(self, view, event):
        for node in self.nodes:
            if view == node.view:
                if "menu" in node.view._window and node.view._window["menu"].winfo_exists():
                    node.view._window["menu"].post(event.x_root, event.y_root)
                else:
                    menu = tk.Menu(self.canvas, tearoff=0)
                    
                    if hasattr(node, 'setFilePaths'):
                        menu.add_command(label="ファイル選択", command=lambda n=node:self.onSelectFiles(n))
                    if hasattr(node, 'setOutputFilePath'):
                        menu.add_command(label="出力ファイル選択", command=lambda n=node: self.onSelectOutputFile(n))
                    if hasattr(node, 'createSettingWindow'):
                        menu.add_command(label="設定", command=lambda n=node: node.view.onEdit(n))
                        
                    if None != menu.index(tk.END):
                        menu.add_separator()
                    
                    menu.add_command(label="削除", command=lambda: self.deleteNode(node))
                    
                    node.view._window["menu"] = menu
                
                    menu.post(event.x_root, event.y_root)
                break

    def onSelectFiles(self, node):
        filePaths = self.openFilesSelector(title=f"{node.name} - ファイルを選択", filetypes=node.fileTypes)
        if filePaths:
            node.setFilePaths(filePaths)
            node.view.onNodeConfigChanged(node)
        
    def onSelectOutputFile(self, node):
        outputPath = self.openOutputFileSelector(title=f"{node.name} - 出力ファイルを選択", defaultextension=node.defaultOutputExtension, filetypes=node.outputFileTypes)
        if outputPath:
            node.setOutputFilePath(outputPath)
            node.view.onNodeConfigChanged(node)
    
    def openFilesSelector(self, *args, **kwargs):
        newKwargs = kwargs.copy()
        if kwargs.get("initialdir",None) is None:
            newKwargs["initialdir"] = self.lastDirectory

        filePaths = filedialog.askopenfilenames( *args, **newKwargs)
        if not filePaths:
            return []

        if kwargs.get("initialdir",None) is None:
            self.lastDirectory = os.path.dirname(filePaths[0])

        return filePaths
    
    def openFileSelector(self, *args, **kwargs):
        newKwargs = kwargs.copy()
        if kwargs.get("initialdir",None) is None:
            newKwargs["initialdir"] = self.lastDirectory
        
        filePath = filedialog.askopenfilename( *args, **newKwargs)
        if not filePath:
            return None
        
        if kwargs.get("initialdir",None) is None:
            self.lastDirectory = os.path.dirname(filePath)
        
        return filePath
    
    def openOutputFileSelector(self, *args, **kwargs):
        newKwargs = kwargs.copy()
        if kwargs.get("initialdir",None) is None:
            newKwargs["initialdir"] = self.lastDirectory
        
        filePath = filedialog.asksaveasfilename(*args, **newKwargs)
        if not filePath:
            return None
        
        if kwargs.get("initialdir",None) is None:
            self.lastDirectory = os.path.dirname(filePath)
        
        return filePath

    def goHome(self):
        """キャンバスをホームポジションに戻す"""
        if self.nodes or self.trays:
            # ノードやトレイがある場合は重心に移動
            items = [(node.view.x, node.view.y) for node in self.nodes] + [(tray.x, tray.y) for tray in self.trays]
            centerX = sum(x for x, y in items) / len(items)
            centerY = sum(y for x, y in items) / len(items)
            
            scrollRegion = self.canvas.cget('scrollregion')
            if scrollRegion:
                x1, y1, x2, y2 = map(float, scrollRegion.split())
                relativeX = (centerX - x1) / (x2 - x1) if x2 > x1 else 0.5
                relativeY = (centerY - y1) / (y2 - y1) if y2 > y1 else 0.5
                self.canvas.xview_moveto(relativeX - 0.25)
                self.canvas.yview_moveto(relativeY - 0.25)
        else:
            # ノードやトレイがない場合は原点に戻す
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
    
    def executeFlow(self):
        if not self.nodes:
            messagebox.showwarning("警告", "フローが空です")
            return
        
        # フロー実行を別スレッドで実行
        CoalescingExecutor.submit( self, self._executeFlowAsync)
    
    def _executeFlowAsync(self):
        """指定されたノードまでを実行する"""
        try:
            self.take += 1
            self.maxObjectCount = 0
            self.resultText.delete(1.0, tk.END)
            
            import gc
            gc.collect()
            
            if not self.selectedNode is None:
                nodes = [self.selectedNode]
            else:
                nodes = self.nodes
            
            self.flowControl.execute( nodes, self.showMessage, self.showProgress)
            
            from utils.Debug import Debug
            if Debug.isTestMode() and 1==self.take and self.currentFlowPath and self.selectedNode is None:
                # テストモード and ファーストテイク and 全実行なので結果を記録
                filename = os.path.basename(self.currentFlowPath)
                Debug.log(type(self).__name__, f"{filename} elapsed {self.flowControl.elapsedMs} ms")
                Debug.log(type(self).__name__, f"{filename} maxObjectCount {self.maxObjectCount}")
                Debug.record( self.currentFlowPath, "elapsed ms", self.flowControl.elapsedMs)
                Debug.record( self.currentFlowPath, "maxObjectCount", self.maxObjectCount)
        except Exception as e:
            self.root.after(0, lambda m = str(e): messagebox.showerror("エラー", f"フロー実行エラー: {m}"))
            raise
        finally:
            self.root.after(0, lambda: self._clearAllProgress())
    
    def stopFlow(self):
        self.flowControl.stop()

    def saveFlow(self):
        if not self.nodes and not self.trays:
            messagebox.showwarning("警告", "保存するフローがありません")
            return
        
        filePath = self.openOutputFileSelector(
            title="フローを保存",
            initialfile=self.currentFlowPath,
            initialdir=os.path.dirname(self.currentFlowPath) if self.currentFlowPath else None,
            defaultextension=".flow",
            filetypes=[("flow files", "*.flow"), ("All files", "*.*")]
        )
        
        if not filePath:
            return
        
        # 現在のflowファイルパスを保存
        self.currentFlowPath = filePath
        
        try:
            flowFile = FlowFile()
            flowFile.save( filePath, self.canvas, self, self.nodes, self.trays)
        
            # ウィンドウタイトルにファイル名を追記
            filename = os.path.basename(filePath)
            self.root.title(f"{self.name} - {filename}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            messagebox.showerror("エラー", f"保存に失敗しました: {str(e)}")
    
    def loadFlow(self, targetX=0, targetY=0, appendMode=False, filePath=None, initialdir=None):
        if not filePath:
            filePath = self.openFileSelector(
                title="フローをインポート" if appendMode else "フローを読み込む",
                initialdir=initialdir,
                filetypes=[("flow files", "*.flow"), ("All files", "*.*")]
            )
        
        if not filePath:
            return
            
        # 現在のflowファイルパスを保存
        if not appendMode:
            self.currentFlowPath = filePath
        
        try:
            # 自動実行をオフにする
            self.autoExecute.set(False)
            
            if not appendMode:
                # 現在のフローをクリア
                self.clearFlow()
            
            # zOrder 順を収集
            flowFile = FlowFile()
            nodes, trays, connections, zOrderObj = flowFile.load( filePath, self.createObject, self.canvas, self)

            if (0 != targetX or 0 != targetY) and (nodes or trays):
                # 座標指定があるので、位置を調整
                items = [(node.view.x, node.view.y) for node in nodes] + [(tray.x, tray.y) for tray in trays]
                centerX = sum(x for x, y in items) / len(items)
                centerY = sum(y for x, y in items) / len(items)
                
                # 目標位置へのオフセット計算
                offsetX = targetX - centerX
                offsetY = targetY - centerY
                    
                # 全アイテムの座標を調整
                for node in nodes:
                    node.view.x += offsetX
                    node.view.y += offsetY
                
                for tray in trays:
                    tray.x += offsetX
                    tray.y += offsetY

            self.nodes.extend(nodes)
            self.trays.extend(trays)

            # 接続線を描画
            for connection in connections:
                fromNode = connection[0]
                toNode = connection[1]
                self.createConnections(fromNode, toNode)
            
            # Z-orderで表示順を再現
            for obj in zOrderObj:
                if hasattr( obj, 'view'):
                    obj.view.lift()
                else:
                    obj.lift()
            
            # 接続線を最上位に配置
            for _, _, line in self.connectionLines:
                self.canvas.tag_raise(line)
            
            # 全アイテムの座標と外観を更新
            for node in self.nodes:
                # 描画を更新
                node.view.updatePositionAndAppearance(node)
            
            for tray in self.trays:
                # 描画を更新
                tray.updatePositionAndAppearance()
            
            # canvasサイズを調整
            self.adjustCanvasSize()
            
            if not appendMode:
                # ウィンドウタイトルにファイル名を追記
                filename = os.path.basename(filePath)
                self.root.title(f"{self.name} - {filename}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            messagebox.showerror("エラー", f"読み込みに失敗しました: {str(e)}")
    
    def createObject(self, type):
        # タイプを指定して各種オブジェクトを作成する
        if "Tray" == type:
            return Tray( self.canvas, self, nonDialog=True)
        else:
            return NodeFactory.createNode( type, self.canvas, self, 0, 0, nonDialog=True)
    
    def clearFlow(self):
        # ノードをクリーンアップ
        for node in self.nodes:
            node.cleanUp()
            
        # キャンバスをクリア
        self.canvas.delete("all")
        # ノード、トレイ、接続をクリア
        self.nodes = []
        self.trays = []
        self.connectionLines = []
        # 状態をクリア
        self.reprocessingHighlights = []
        self.selectedHighlight = None
        self.selectedNode = None
        
    def deleteNode(self, node):
        # ノードの接続をクリア（双方向）
        for n in self.nodes:
            if node in n.outputNodes:
                n.outputNodes.remove(node)
            if node in n.inputNodes:
                n.inputNodes.remove(node)
        
        # 削除されるノードの接続もクリア（双方向）
        for outputNode in node.outputNodes:
            if node in outputNode.inputNodes:
                outputNode.inputNodes.remove(node)
        for inputNode in node.inputNodes:
            if node in inputNode.outputNodes:
                inputNode.outputNodes.remove(node)
        
        # ノードリストから削除
        self.nodes.remove(node)
        
        # 選択状態をクリア
        if self.selectedNode == node:
            self.clearSelectedHighlight()
            self.selectedNode = None
        
        # ノードをキャンバスから削除
        self.canvas.delete(node.view.rect)
        self.canvas.delete(node.view.label)
        
        # 削除対象ノードに関連する接続線を削除
        self.removeConnections(node)
        self.updateConnections()
        
        # 強調表示更新
        self.highlightReprocessingNodes()
        
        # ノードのクリーンアップ
        node.cleanUp()
        
    def highlightReprocessingNodes(self):
        """再実行されるノードを強調表示"""
        # 既存のハイライトをクリア
        self.clearReprocessingHighlights()
        
        # 再実行が必要なノードを特定してハイライト
        for node in self.nodes:
            if self._needsReprocessingRecursive(node):
                x1, y1, x2, y2 = node.view.getShapeBounds()
                highlight = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline='orange', width=4, fill='', dash=(5, 5)
                )
                self.reprocessingHighlights.append(highlight)
    
    def _needsReprocessingRecursive(self, node):
        """上流を再帰的にチェックして再実行が必要か判定"""
        # 自分自身の設定が変更されたかチェック
        if node.needsReprocessing():
            return True
        
        # 上流ノードのいずれかが再実行必要かチェック
        for inputNode in node.inputNodes:
            if self._needsReprocessingRecursive(inputNode):
                return True
        
        return False
    
    def onNodeConfigChanged(self, node):
        """ノードの設定変更時に呼び出される"""
        from utils.Debug import Debug
        
        text = node.getText()
        if Debug.LEVEL_NONE < Debug.LEVEL and hasattr(node, '_loadIndex'):
            text = f"{node._loadIndex} {text}"
        self.canvas.itemconfig(node.view.label, text=text)

        # 接続線の更新
        self.updateConnections()
        
        # 強調表示更新
        self.highlightReprocessingNodes()
        
        # 自動実行が有効かつ再実行が必要なノードがある場合、自動で実行開始
        if self.autoExecute.get() and self.reprocessingHighlights:
            self.executeFlow()
    
    def showMessage(self,msg):
        status = msg.split('\n')[0]
        self.root.after(0, self.statusLabel.config, {"text":status})
        self.root.after(0, self.updateResultText, msg)
        self.root.after(0, self.highlightReprocessingNodes)

    def updateResultText(self, msg):
        lines = int(self.resultText.index(tk.END).split('.')[0]) # tk.END 位置を取得 "{line}.{row}"
        if 10000 < lines:
            self.resultText.delete("1.0", "100.0")
        self.resultText.insert(tk.END, msg)
        self.resultText.see(tk.END)
    
    def showProgress(self, nodeId, nodeName, message, current=None, total=None):
        """処理経過をプログレスバーで表示"""
        self.root.after(0, lambda: self._updateProgress(nodeId, nodeName, message, current, total))
        self.root.after(0, lambda: self.statusLabel.config(text=f"{nodeName}: {message}"))
    
    def _updateProgress(self, nodeId, nodeName, message, current, total):
        """プログレスバーを更新"""
        if nodeId not in self.activeProgressBars:
            # 空いているプログレスバーを割り当て
            for i, progressInfo in enumerate(self.progressBars):
                if i not in self.activeProgressBars.values():
                    self.activeProgressBars[nodeId] = i
                    break
            for i, progressInfo in enumerate(self.progressBars):
                if i not in self.activeProgressBars.values():
                    progressInfo['label'].config(text="待機中")
                    progressInfo['bar'].config(value=0)
        
        if nodeId in self.activeProgressBars:
            progressInfo = self.progressBars[self.activeProgressBars[nodeId]]
            progressInfo['label'].config(text=f"{nodeName}: {message}")
            
            if current is None or total is None:
                progressInfo['bar'].config(value=0)
            elif 0 <= total:
                progress = (current / total) * 100
                progressInfo['bar'].config(value=progress)
            else:
                progressInfo['bar'].config(value=100)
                del self.activeProgressBars[nodeId]
        
        from utils.Debug import Debug
        if Debug.isTestMode() and current and int(current)==(total*9)//10:
            import gc
            objectCount = len(gc.get_objects())
            self.maxObjectCount = max(self.maxObjectCount, objectCount)
    
    def _clearAllProgress(self):
        """全てのプログレスバーをクリア"""
        for progressInfo in self.progressBars:
            progressInfo['label'].config(text="待機中")
            progressInfo['bar'].config(value=0)
        self.activeProgressBars.clear()
    
    def startUpdateCacheStats(self):
        self._setCount = 0
        self._getCount = 0
        self._startUpdateCacheStats()
    
    def _startUpdateCacheStats(self):
        self.updateCacheStats()
        # 5秒毎に更新
        self.root.after(5000, self._startUpdateCacheStats)
    
    def updateCacheStats(self):
        """キャッシュ統計を更新"""
        import gc
        from utils.Debug import Debug
        from base import CacheManager
        
        ObjectCount    = f"{len(gc.get_objects())}個"
        flowDataCount = f"{sum([len(node.flowDatas) for node in self.nodes])}個"
        flowNodeCount = f"{len(self.nodes)}個"
        trayCount = f"{len(self.trays)}個"
        
        (objCacheCount, cacheCount, cacheSize, storageCount, storageSize,
         getCount, cacheHitCount, recalculateCount, loadCount,
         setCount, purgeCount, saveCount,
         elapsedHis) = CacheManager.getCacheStats()
        setps = (setCount - self._setCount)//5
        getps = (getCount - self._getCount)//5
        self._setCount = setCount
        self._getCount = getCount
        
        # set/get 回数に単位を表示
        setpsStr = f"{setps}set/s"
        getpsStr = f"{getps}get/s"
        
        # キャッシュサイズを適切な単位で表示
        if cacheSize < 10*1024:
            cacheSizeStr = f"{int(cacheSize)}B"
        elif cacheSize < 10*1024*1024:
            cacheSizeStr = f"{int(cacheSize/1024)}KB"
        elif cacheSize < 10*1024*1024*1024:
            cacheSizeStr = f"{int(cacheSize/1024/1024)}MB"
        else:
            cacheSizeStr = f"{int(cacheSize/1024/1024/1024)}GB"
        
        # ディスクサイズを適切な単位で表示
        if storageSize < 10*1024:
            storageSizeStr = f"{int(storageSize)}B"
        elif storageSize < 10*1024*1024:
            storageSizeStr = f"{int(storageSize/1024)}KB"
        elif storageSize < 10*1024*1024*1024:
            storageSizeStr = f"{int(storageSize/1024/1024)}MB"
        else:
            storageSizeStr = f"{int(storageSize/1024/1024/1024)}GB"
        
        # 使用量ラベルを更新
        if Debug.LEVEL_NONE == Debug.LEVEL:
            blockInfo = f"Block: {getpsStr}, {setpsStr}"
            objInfo   = f"Object: {ObjectCount}"
            CacheInfo = ""
            dataInfo  = f"Data: {flowDataCount} Cache: {cacheCount}({cacheSizeStr}) Storage: {storageSizeStr}"
            nodeInfo  = f"Node: {flowNodeCount}"
        else:
            cacheNodeCount = f"{self.getNodeCount()}個"

            blockInfo = f"Block: {getpsStr}, {setpsStr}"
            objInfo   = f"Object: {ObjectCount}"
            CacheInfo = f"Cache[Hit: {cacheHitCount}({cacheHitCount/getCount:.3f}) Recalculate: {recalculateCount}({recalculateCount/getCount:.3f}) Load: {loadCount}({loadCount/getCount:.3f}) Purge: {purgeCount} {purgeCount/setCount:.3f} Save:{saveCount}({saveCount/setCount:.3f})]" if 0!=getCount and 0!=setCount else ""
            dataInfo  = f"Data: {flowDataCount} Object: {objCacheCount} Cache: {cacheCount}({cacheSizeStr}) Storage: {storageCount}({storageSizeStr})"
            nodeInfo  = f"Node: {flowNodeCount} Exist: {cacheNodeCount}"
        
        info = f"{blockInfo} {objInfo} {CacheInfo} {dataInfo} {nodeInfo}"
        self.usageLabel.config(text=info)

    def getNodeCount(self):
        import gc
        from base import FlowNode
        
        nodes = []
        for obj in gc.get_objects():
            if isinstance( obj, FlowNode):
                nodes.append(obj)
        return(len(nodes))

    def forceGarbageCollection(self):
        """ガベージコレクションを強制実行"""
        import gc
        from utils.Debug import Debug
        from base import CacheManager
        
        # 実行前のメモリ使用量を取得
        b_nodeCount = self.getNodeCount()
        (b_objCacheCount, b_cacheCount, b_cacheSize, b_storageCount, b_storageSize,
         b_getCount, b_cacheHitCount, b_recalculateCount, b_loadCount,
         b_setCount, b_purgeCount, b_saveCount,
         b_elapsedHis) = CacheManager.getCacheStats()
        
        # ガベージコレクションを実行
        collected = gc.collect()
        
        # 実行後のメモリ使用量を取得
        a_nodeCount = self.getNodeCount()
        (a_objCacheCount, a_cacheCount, a_cacheSize, a_storageCount, a_storageSize,
         a_getCount, a_cacheHitCount, a_recalculateCount, a_loadCount,
         a_setCount, a_purgeCount, a_saveCount,
         a_elapsedHis) = CacheManager.getCacheStats()
        
        # 結果を表示
        freedNodeCount = b_nodeCount - a_nodeCount
        freedMemory = b_cacheSize - a_cacheSize
        if freedMemory > 0:
            if freedMemory < 10*1024:
                freedStr = f"{int(freedMemory)}B"
            elif freedMemory < 10*1024*1024:
                freedStr = f"{int(freedMemory/1024)}KB"
            elif freedMemory < 10*1024*1024*1024:
                freedStr = f"{int(freedMemory/1024/1024)}MB"
            else:
                freedStr = f"{int(freedMemory/1024/1024/1024)}GB"
            message = f"GC実行: {freedNodeCount}個解放, {freedStr}解放 ({collected}obj)"
        else:
            message = f"GC実行: {freedNodeCount}個解放 ({collected}obj)"
        
        self.statusLabel.config(text=message)
        
        # キャッシュ統計を即座に更新
        self.updateCacheStats()
        
        if Debug.LEVEL_NONE < Debug.LEVEL:
            print("========================")
            print(f"References report")
            self._debugReferencesReport()
            print("========================")
            print(f"Debug report")
            for text in Debug.getDebugReport():
                print(text)
            print("========================")
            (objCacheCount, cacheCount, cacheSize, storageCount, storageSize,
             getCount, cacheHitCount, recalculateCount, loadCount,
             setCount, purgeCount, saveCount,
             elapsedHis) = CacheManager.getCacheStats()
            print(f"objCacheCount: {objCacheCount}")
            print(f"cacheCount: {cacheCount}")
            print(f"cacheSize: {cacheSize}")
            print(f"storageCount: {storageCount}")
            print(f"storageSize: {storageSize}")
            print(f"getCount: {getCount}")
            print(f"cacheHitCount: {cacheHitCount}")
            print(f"recalculateCount: {recalculateCount}")
            print(f"loadCount: {loadCount}")
            print(f"setCount: {setCount}")
            print(f"purgeCount: {purgeCount}")
            print(f"saveCount: {saveCount}")
            print("------------------------")
            label = 'times it n [us]'
            maxlen = max([len(s) for s in [label] + list(elapsedHis.keys())])
            print(f"{label:{maxlen}s}", end="\t")
            labels = next(iter(elapsedHis.values()))
            for label in labels:
                print(label, end="\t")
            print()
            for name,values in elapsedHis.items():
                print(f"{name:{maxlen}s}", end="\t")
                for value in values.values():
                    print(value, end="\t")
                print()
            print("========================")

    def toggleDebugMode(self, event):
        """デバッグモードを切り替える"""
        from utils.Debug import Debug
        
        Debug.LEVEL = Debug.LEVEL_NONE if Debug.LEVEL_NONE != Debug.LEVEL else Debug.LEVEL_ALL
        self.statusLabel.config(text=f"状態: DEBUGモード {'OFF' if Debug.LEVEL == Debug.LEVEL_NONE else 'ON'}")

        for node in self.nodes:
            node.view.updatePositionAndAppearance(node)

        return "break"

    def _debugReferencesReport(self):
        """ノードの参照状況をデバッグ出力"""
        import gc
        from base import FlowData
        from base import FlowNode
        # 全オブジェクトからflowNodeを探す
        objs = []
        objCount = 0
        moduleCounts = {}
        referrerCounts = {}
        nodeCount = 0
        for obj in gc.get_objects():
            objCount += 1

            objType = type(obj).__name__
            objMod  = getattr(obj, '__module__', getattr(type(obj), '__module__', 'unknown'))
            objMod  = str(objMod) if objMod else ''
            objName = getattr(obj, '__name__', objType) if not objMod in 'six' else objType
            objSym  = f"{objMod}.{objName}" if objMod else f".{objName}"
            moduleCounts[objSym] = moduleCounts.setdefault(objSym,0) + 1

            if not objMod in ['builtins']:
                for ref in gc.get_referents(obj):
                    refType = type(ref).__name__
                    refMod  = getattr(ref, '__module__', getattr(type(ref), '__module__', 'unknown'))
                    refMod  = str(refMod) if refMod else ''
                    refName = getattr(ref, '__name__', refType) if not refMod in 'six' else refType
                    fm      = f"{objMod}" if objMod else f".{objName}"
                    to      = f"{refMod}" if refMod else f".{refName}"
                    refSym = f"{fm} => {to}"
                    referrerCounts[refSym] = referrerCounts.setdefault(refSym, 0) + 1

            if(  isinstance( obj, FlowNode)
        #      or isinstance( obj, FlowData)
              ):
                objs.append(obj)
                nodeCount += 1
        
        print(f"残存object数: {len(moduleCounts)} ", end="")
        _y = 0
        _n = 0
        for x,y in sorted(list(moduleCounts.items()), key=lambda x:x[1]):
            if _y != y:
                if 3<_n:
                    print(f"... {_n-3}", end="")
                _n = 0
                print(f"\n  {y}: ", end="")
            if _n < 3:
                print(x, end=" ")
            _y = y
            _n += 1
        print()

        print(f"残存referrer数", end="")
        _y = 0
        _n = 0
        for x,y in sorted(list(referrerCounts.items()), key=lambda x:x[1]):
            if _y != y:
                if 3<_n:
                    print(f"... {_n-3}", end="")
                _n = 0
                print(f"\n  {y}: ", end="")
            if _n < 3:
                print(x, end=" ")
            _y = y
            _n += 1
        print()

        print(f"残存flowNode数: {nodeCount}")
        
        for i, obj in enumerate(objs):
            print(f"残存ノード{i}: {getattr(obj, 'text', type(obj).__name__)} (id: {id(obj)}) (loadIndex: {getattr(obj,'_loadIndex',None)})")
            
            # 参照カウントを取得
            refCount = sys.getrefcount(obj)
            print(f"  参照カウント: {refCount}")
            
            # gcモジュールで参照元を調査
            referrers = gc.get_referrers(obj)
            print(f"  参照元数: {len(referrers)}")
            for j, ref in enumerate(referrers):
                refs = self._debugNodeReferencesRecursive(ref)
                org = [type(x).__name__ for x in refs] if len(refs)<5 else len(refs)
                refType = type(ref).__name__
                if refType == 'list':
                    print(f"    {j}: list (length: {len(ref)}) (source: {org})")
                elif refType == 'tuple':
                    print(f"    {j}: tuple (length: {len(ref)}) (source: {org})")
                elif refType == 'dict':
                    print(f"    {j}: dict (length: {len(ref)}) (source: {org})")
                elif refType == 'method':
                    print(f"    {j}: method {ref.__name__} ({type(ref.__self__).__name__} object) (source: {org})")
                elif hasattr(ref, '__class__'):
                    print(f"    {j}: {ref.__class__.__name__} object (source: {org})")
                else:
                    print(f"    {j}: {refType} (source: {org})")
            
            # gcモジュールで参照先を調査
            #referrers = gc.get_referents(obj)
            #print(f"  参照先数: {len(referrers)}")
            #for j, ref in enumerate(referrers):
            #    refType = type(ref).__name__
            #    if refType == 'list':
            #        print(f"    {j}: list (length: {len(ref)})")
            #    elif refType == 'tuple':
            #        print(f"    {j}: tuple (length: {len(ref)})")
            #    elif refType == 'dict':
            #        print(f"    {j}: dict (length: {len(ref)})")
            #    elif refType == 'method':
            #        print(f"    {j}: method {ref.__name__} (object: {type(ref.__self__).__name__})")
            #    elif hasattr(ref, '__class__'):
            #        print(f"    {j}: {ref.__class__.__name__} object")
            #    else:
            #        print(f"    {j}: {refType}")
    
    def _debugNodeReferencesRecursive(self, obj, level = 0, exists=set()):
        """ノードの参照状況を再帰的に収集"""
        import gc
        import inspect
        from base import FlowData
        
        level += 16
        objs = set()

        if id(obj) in exists:
            return(objs)
        else:
            exists.add(id(obj))

            if 10 < level:
                objs.add(None)
            elif(  isinstance( obj, FlowEditor)
                or isinstance( obj, FlowData)
                or isinstance( obj, tk.Toplevel)
                or inspect.isfunction(obj)
                or inspect.ismethod(obj) and isinstance( obj.__self__, FlowEditor)
                or inspect.ismethod(obj) and isinstance( obj.__self__, FlowData)
                or inspect.ismethod(obj) and isinstance( obj.__self__, tk.Toplevel)
                ):
                objs.add(obj)
            else:
                referrers = gc.get_referrers(obj)
                for ref in referrers:
                    objs.update(self._debugNodeReferencesRecursive(ref, level))
            return(objs)
