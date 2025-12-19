'''
Flow Editor - Visual Flow-based Image Processing Tool

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import inspect
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import datetime
import json
import sys
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import atexit
import gc

from config import VERSION
from base import FlowNode
from base import FlowData
from nodes import NodeFactory
from . import CacheManager
from . import Debug
from utils.ThreadPool import CoalescingExecutor

# グローバルスレッドプール
MAX_NODE_WORKERS = 4
NodeExecutor = ThreadPoolExecutor(max_workers=MAX_NODE_WORKERS)
atexit.register(NodeExecutor.shutdown)

class Tray:
    def __init__(self, canvas, editor, x, y, width=200, height=150, title="トレイ"):
        self.canvas = canvas
        self.editor = editor
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title

        self.isDragging = False
        self.isResizing = False
        self.dragStartX = 0
        self.dragStartY = 0
        self.dragNodes = []  # ドラッグ時に一緒に移動するノードリスト
        self.dragTrays = []  # ドラッグ時に一緒に移動するトレイリスト
        
        # 描画要素を作成
        self.rect = canvas.create_rectangle(
            x - width//2, y - height//2, x + width//2, y + height//2,
            outline='gray', width=2, fill='lightgray', stipple='gray25'
        )
        self.label = canvas.create_text(
            x - width//2 + 10, y - height//2 + 10, text=title, anchor=tk.NW, font=('Arial', 10, 'bold')
        )
        self.updateDepthAppearance()
        
        # イベントバインディング
        canvas.tag_bind(self.rect, '<Button-1>', self.onMouseDown)
        canvas.tag_bind(self.rect, '<B1-Motion>', self.onMouseDrag)
        canvas.tag_bind(self.rect, '<ButtonRelease-1>', self.onMouseUp)
        canvas.tag_bind(self.rect, '<Button-3>', self.onRightClick)
        canvas.tag_bind(self.label, '<Button-1>', self.onMouseDown)
        canvas.tag_bind(self.label, '<B1-Motion>', self.onMouseDrag)
        canvas.tag_bind(self.label, '<ButtonRelease-1>', self.onMouseUp)
        canvas.tag_bind(self.label, '<Button-3>', self.onRightClick)
    
    def onMouseDown(self, event):
        self.dragStartX = event.x
        self.dragStartY = event.y
        canvasX = self.canvas.canvasx(event.x)
        canvasY = self.canvas.canvasy(event.y)
        
        # 境界近くかチェック（リサイズ判定）
        margin = 10
        left = self.x - self.width//2
        right = self.x + self.width//2
        top = self.y - self.height//2
        bottom = self.y + self.height//2
        
        # リサイズハンドルの判定
        self.resizeHandle = None
        if abs(canvasX - right) < margin and abs(canvasY - bottom) < margin:
            self.resizeHandle = 'se'  # 右下
        elif abs(canvasX - left) < margin and abs(canvasY - bottom) < margin:
            self.resizeHandle = 'sw'  # 左下
        elif abs(canvasX - right) < margin and abs(canvasY - top) < margin:
            self.resizeHandle = 'ne'  # 右上
        elif abs(canvasX - left) < margin and abs(canvasY - top) < margin:
            self.resizeHandle = 'nw'  # 左上
        elif abs(canvasX - right) < margin:
            self.resizeHandle = 'e'   # 右
        elif abs(canvasX - left) < margin:
            self.resizeHandle = 'w'   # 左
        elif abs(canvasY - bottom) < margin:
            self.resizeHandle = 's'   # 下
        elif abs(canvasY - top) < margin:
            self.resizeHandle = 'n'   # 上
        
        if self.resizeHandle:
            self.isResizing = True
            # リサイズ開始時の座標を保存
            self.resizeStartX = self.x
            self.resizeStartY = self.y
            self.resizeStartWidth = self.width
            self.resizeStartHeight = self.height
        else:
            self.isDragging = True
            self.dragNodes = self.getVisuallyContainedNodes()  # 視覚的に上にあるノードのみを固定
            self.dragTrays = self.getVisuallyContainedTrays()  # 視覚的に上にあるトレイを固定
            # ドラッグ開始時にハイライトを消す
            self.editor.clearSelectedHighlight()
            self.editor.clearReprocessingHighlights()
            # ドラッグ開始時にトレイと含まれるアイテムを前面に
            groupItems = [self.rect, self.label]
            for node in self.dragNodes:
                groupItems.extend([node.rect, node.label])
            for tray in self.dragTrays:
                groupItems.extend([tray.rect, tray.label])
            self.editor._placeItemBeforeConnections(*groupItems)
            # ドラッグ開始時に外観を更新
            self.editor.updateAllTrayAppearance()
    
    def onMouseDrag(self, event):
        dx = event.x - self.dragStartX
        dy = event.y - self.dragStartY
        
        if self.isDragging:
            # トレイを移動
            self.x += dx
            self.y += dy
            self.canvas.move(self.rect, dx, dy)
            self.canvas.move(self.label, dx, dy)
            
            # ドラッグ開始時に固定したノードを一緒に移動
            for node in self.dragNodes:
                node.x += dx
                node.y += dy
                self.canvas.move(node.rect, dx, dy)
                self.canvas.move(node.label, dx, dy)
            
            # ドラッグ開始時に固定したトレイを一緒に移動
            for tray in self.dragTrays:
                tray.x += dx
                tray.y += dy
                self.canvas.move(tray.rect, dx, dy)
                self.canvas.move(tray.label, dx, dy)
            
            # ドラッグ中はグループ全体を順序を維持して前面に保持
            groupItems = [self.rect, self.label]
            for node in self.dragNodes:
                groupItems.extend([node.rect, node.label])
            for tray in self.dragTrays:
                groupItems.extend([tray.rect, tray.label])
            self.editor._placeItemBeforeConnections(*groupItems)
            # ドラッグ中に外観を更新
            self.editor.updateAllTrayAppearance()
            
            # 接続線を更新
            self.editor.updateConnections()
        elif self.isResizing:
            canvasX = self.canvas.canvasx(event.x)
            canvasY = self.canvas.canvasy(event.y)
            
            # ハンドルに応じてリサイズ処理
            # 固定点を計算
            fixedLeft = self.resizeStartX - self.resizeStartWidth//2
            fixedRight = self.resizeStartX + self.resizeStartWidth//2
            fixedTop = self.resizeStartY - self.resizeStartHeight//2
            fixedBottom = self.resizeStartY + self.resizeStartHeight//2
            
            # 新しい境界を計算
            newLeft = fixedLeft
            newRight = fixedRight
            newTop = fixedTop
            newBottom = fixedBottom
            
            if 'e' in self.resizeHandle:  # 右辺移動
                newRight = max(fixedLeft + 100, canvasX)
            elif 'w' in self.resizeHandle:  # 左辺移動
                newLeft = min(fixedRight - 100, canvasX)
            
            if 's' in self.resizeHandle:  # 下辺移動
                newBottom = max(fixedTop + 80, canvasY)
            elif 'n' in self.resizeHandle:  # 上辺移動
                newTop = min(fixedBottom - 80, canvasY)
            
            # 新しい中心とサイズを計算
            newWidth = newRight - newLeft
            newHeight = newBottom - newTop
            newX = (newLeft + newRight) // 2
            newY = (newTop + newBottom) // 2
            
            self.x = int(newX)
            self.y = int(newY)
            self.width = int(newWidth)
            self.height = int(newHeight)
            
            # 矩形を再描画
            self.canvas.coords(self.rect,
                self.x - self.width//2, self.y - self.height//2,
                self.x + self.width//2, self.y + self.height//2)
            self.canvas.coords(self.label,
                self.x - self.width//2 + 10, self.y - self.height//2 + 10)
        
        self.dragStartX = event.x
        self.dragStartY = event.y
    
    def onMouseUp(self, event):
        self.isDragging = False
        self.isResizing = False
        self.dragNodes = []  # ドラッグノードリストをクリア
        self.dragTrays = []  # ドラッグトレイリストをクリア
        # 全トレイの外観を更新
        self.editor.updateAllTrayAppearance()
    
    def onRightClick(self, event):
        menu = tk.Menu(self.canvas, tearoff=0)
        menu.add_command(label="編集", command=self.editTray)
        menu.add_command(label="削除", command=self.deleteTray)
        menu.post(event.x_root, event.y_root)
    
    def editTray(self):
        dialog = tk.Toplevel(self.editor.root)
        dialog.title("トレイ編集")
        dialog.geometry("300x150")
        dialog.grab_set()
        
        tk.Label(dialog, text="タイトル:").pack(pady=5)
        titleEntry = tk.Entry(dialog, width=30)
        titleEntry.insert(0, self.title)
        titleEntry.pack(pady=5)
        
        def applyChanges():
            self.title = titleEntry.get()
            self.canvas.itemconfig(self.label, text=self.title)
            dialog.destroy()
        
        tk.Button(dialog, text="適用", command=applyChanges).pack(pady=10)
    
    def deleteTray(self):
        self.editor.deleteTray(self)
    
    def updateDepthAppearance(self):
        """Z-orderに基づいて外観を更新"""
        if not hasattr(self, 'rect') or len(self.editor.trays) <= 1:
            return
        
        allItems = self.canvas.find_all()
        if self.rect not in allItems:
            return
            
        zIndex = allItems.index(self.rect)
        relativeDepth = min(1.0, zIndex / (len(allItems) - 1))
        
        # 深度に応じて外観を調整
        width = max(2, int(2 + relativeDepth * 3))
        grayLevel = max(64, int(128 - relativeDepth * 64))
        bgGray = max(200, int(240 - relativeDepth * 40))
        stipplePattern = ['gray12', 'gray25', 'gray50'][min(2, int(relativeDepth * 3))]
        
        self.canvas.itemconfig(self.rect, 
            outline=f"#{grayLevel:02x}{grayLevel:02x}{grayLevel:02x}",
            width=width, 
            fill=f"#{bgGray:02x}{bgGray:02x}{bgGray:02x}", 
            stipple=stipplePattern)
    
    def getVisuallyContainedNodes(self):
        """視覚的にトレイの上にあるノードを取得"""
        contained = []
        for node in self.editor.nodes:
            if (self.x - self.width//2 <= node.x <= self.x + self.width//2 and
                self.y - self.height//2 <= node.y <= self.y + self.height//2):
                # ノードがトレイより前面にあるかチェック
                nodeItems = [node.rect, node.label]
                trayItems = [self.rect, self.label]
                
                # キャンバスのアイテム順序で比較
                allItems = self.canvas.find_all()
                nodeMaxIndex = max(allItems.index(item) for item in nodeItems if item in allItems)
                trayMaxIndex = max(allItems.index(item) for item in trayItems if item in allItems)
                
                if nodeMaxIndex > trayMaxIndex:
                    contained.append(node)
        return contained
    
    def getVisuallyContainedTrays(self):
        """視覚的にトレイの上にある他のトレイを取得"""
        contained = []
        for tray in self.editor.trays:
            if tray == self:  # 自分自身は除外
                continue
            if (self.x - self.width//2 <= tray.x <= self.x + self.width//2 and
                self.y - self.height//2 <= tray.y <= self.y + self.height//2):
                # トレイがこのトレイより前面にあるかチェック
                trayItems = [tray.rect, tray.label]
                selfItems = [self.rect, self.label]
                
                # キャンバスのアイテム順序で比較
                allItems = self.canvas.find_all()
                trayMaxIndex = max(allItems.index(item) for item in trayItems if item in allItems)
                selfMaxIndex = max(allItems.index(item) for item in selfItems if item in allItems)
                
                if trayMaxIndex > selfMaxIndex:
                    contained.append(tray)
        return contained
    
    def toDict(self):
        return {
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'title': self.title,
            'zOrder': 0  # 保存時に動的に設定
        }
    
    def fromDict(self, data):
        self.x = data['x']
        self.y = data['y']
        self.width = data['width']
        self.height = data['height']
        self.title = data['title']
        # zOrderは読み込み時に動的に設定される
        
        # 描画要素を更新
        self.canvas.coords(self.rect,
            self.x - self.width//2, self.y - self.height//2,
            self.x + self.width//2, self.y + self.height//2)
        self.canvas.coords(self.label,
            self.x - self.width//2 + 10, self.y - self.height//2 + 10)
        self.canvas.itemconfig(self.label, text=self.title)

class FlowEditor:
    def __init__(self, root, text):
        self.root = root
        self.text = text
        self.root.title(f"{self.text} - {VERSION}")
        self.nodes = []
        self.trays = []
        self.reprocessingHighlights = []
        self.selectedHighlight = None
        self.selectedNode = None
        self.connectionLines = []
        self.autoExecute = tk.BooleanVar(value=False)
        self.currentFlowPath = None
        self.createWidgets()
    
    def createWidgets(self):
        # ツールバー
        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(toolbar, text="ホーム", command=self.goHome, bg='gray', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="最前面", command=self.bringChildWindowsToFront, bg='gray', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="読込", command=self.loadFlow, bg='orange', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="保存", command=self.saveFlow, bg='blue', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Checkbutton(toolbar, text="自動実行", variable=self.autoExecute).pack(side=tk.RIGHT, padx=2)
        tk.Button(toolbar, text="実行", command=self.executeFlow, bg='green', fg='white').pack(side=tk.RIGHT, padx=2)
        
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
        
        self.canvas.bind('<ButtonRelease-1>', self.onCanvasRelease)
        self.canvas.bind('<ButtonRelease-3>', self.onCanvasRightRelease)
        self.canvas.bind('<MouseWheel>', self.onMouseWheel)
        self.canvas.bind('<Shift-MouseWheel>', self.onShiftMouseWheel)
        
        # 右クリックメニュー
        self.contextMenu = tk.Menu(self.root, tearoff=0)
        for nodeType, label in NodeFactory.getMenuItems():
            if nodeType == 'separator':
                self.contextMenu.add_separator()
            else:
                self.contextMenu.add_command(label=label, command=lambda nt=nodeType: self.addNodeAtPosition(nt))
        
        self.contextMenu.add_separator()
        self.contextMenu.add_command(label="トレイ作成", command=self.addTrayAtPosition)
        
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
        for i in range(MAX_NODE_WORKERS):
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
        self.updateCacheStats()
        self.root.after(5000, self.updateCacheStats)
    
    def bringChildWindowsToFront(self):
        """子画面を最前面に持ち上げる"""
        # 各ノードの設定ダイアログをチェック
        for node in self.nodes:
            node.lift()
        
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
                if clickedItem == node.rect or clickedItem == node.label:
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
        try:
            x = self.canvas.canvasx(self.rightClickX)
            y = self.canvas.canvasy(self.rightClickY)
            node = NodeFactory.createNode(nodeType, self.canvas, self, x, y)
            if node:
                self.nodes.append(node)
                self._placeItemBeforeConnections(node.rect, node.label)
        except ValueError:
            pass
    
    def addTrayAtPosition(self):
        x = self.canvas.canvasx(self.rightClickX)
        y = self.canvas.canvasy(self.rightClickY)
        tray = Tray(self.canvas, self, x, y)
        self.trays.append(tray)
        self._placeItemBeforeConnections(tray.rect, tray.label)
        self.updateAllTrayAppearance()
    
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
    
    def updateNodeText(self, node, text):
        if Debug.LEVEL_NONE < Debug.LEVEL and hasattr(node, '_loadFlowId'):
            text = f"{node._loadFlowId} {text}"
        self.canvas.itemconfig(node.label, text=text)
    
    def adjustCanvasSize(self):
        """ノードとトレイの位置に合わせてcanvasサイズを調整"""
        if not self.nodes and not self.trays:
            return
        
        # 全ノードとトレイの範囲を計算
        items = []
        for node in self.nodes:
            items.extend([node.x - 60, node.x + 60, node.y - 30, node.y + 30])
        for tray in self.trays:
            items.extend([tray.x - tray.width//2, tray.x + tray.width//2, 
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
        #中心間の線とノード境界の交点を計算
        dx = toNode.x - fromNode.x
        dy = toNode.y - fromNode.y
        
        if dx == 0 and dy == 0:
            return fromNode.x, fromNode.y, toNode.x, toNode.y
        
        # fromNodeからの交点を計算
        if abs(dx) * 20 > abs(dy) * 50:  # 水平方向が主
            x1 = fromNode.x + (50 if dx > 0 else -50)
            y1 = max(-20, min(20, fromNode.y + dy * 50 / abs(dx) - fromNode.y)) + fromNode.y
        else:  # 垂直方向が主
            x1 = max(-50, min(50, fromNode.x + dx * 20 / abs(dy) - fromNode.x)) + fromNode.x
            y1 = fromNode.y + (20 if dy > 0 else -20)
        
        # toNodeへの交点を計算
        if abs(dx) * 20 > abs(dy) * 50:  # 水平方向が主
            x2 = toNode.x - (50 if dx > 0 else -50)
            y2 = max(-20, min(20, toNode.y - dy * 50 / abs(dx) - toNode.y)) + toNode.y
        else:  # 垂直方向が主
            x2 = max(-50, min(50, toNode.x - dx * 20 / abs(dy) - toNode.x)) + toNode.x
            y2 = toNode.y - (20 if dy > 0 else -20)
        
        return x1, y1, x2, y2
    
    def updateConnections(self):
        """接続線の位置を更新"""
        for fromNode, toNode, line in self.connectionLines:
            x1, y1, x2, y2 = self._getConnectionPoints(fromNode, toNode)
            self.canvas.coords(line, x1, y1, x2, y2)
    
    def selectNode(self, node):
        self.statusLabel.config(text=f"ノードクリック: {node.text}")
        
        # 前の選択をクリア
        self.clearSelectedHighlight()
        
        if self.selectedNode and self.selectedNode != node:
            # 既存の接続をチェック（順方向と逆方向）
            if node in self.selectedNode.outputNodes:
                # 順方向接続を削除
                self.selectedNode.outputNodes.remove(node)
                node.inputNodes.remove(self.selectedNode)
                # 接続線を削除
                for i, (f, t, l) in enumerate(self.connectionLines):
                    if f == self.selectedNode and t == node:
                        self.canvas.delete(l)
                        del self.connectionLines[i]
                        break
                # 削除情報を表示
                self.resultText.delete(1.0, tk.END)
                self.resultText.insert(tk.END, f"接続削除: {self.selectedNode.text} → {node.text}\n")
                self.resultText.see(tk.END)
                self.statusLabel.config(text=f"接続削除: {self.selectedNode.text} → {node.text}")
            elif self.selectedNode in node.outputNodes:
                # 逆方向接続を削除
                node.outputNodes.remove(self.selectedNode)
                self.selectedNode.inputNodes.remove(node)
                # 接続線を削除
                for i, (f, t, l) in enumerate(self.connectionLines):
                    if f == node and t == self.selectedNode:
                        self.canvas.delete(l)
                        del self.connectionLines[i]
                        break
                # 削除情報を表示
                self.resultText.delete(1.0, tk.END)
                self.resultText.insert(tk.END, f"逆向き接続削除: {node.text} → {self.selectedNode.text}\n")
                self.resultText.see(tk.END)
                self.statusLabel.config(text=f"逆向き接続削除: {node.text} → {self.selectedNode.text}")
            else:
                # 新規接続を作成
                self.selectedNode.outputNodes.append(node)
                node.inputNodes.append(self.selectedNode)
                x1, y1, x2, y2 = self._getConnectionPoints(self.selectedNode, node)
                line = self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, width=2, fill='red')
                self.connectionLines.append((self.selectedNode, node, line))
                # 接続情報を表示
                self.resultText.delete(1.0, tk.END)
                self.resultText.insert(tk.END, f"接続: {self.selectedNode.text} → {node.text}\n")
                self.resultText.see(tk.END)
                self.statusLabel.config(text=f"接続完了: {self.selectedNode.text} → {node.text}")
                # 新しい接続線は自動的に最上位に配置される
            
            self.selectedNode = None
            
            # 強調表示更新
            self.highlightReprocessingNodes()
            
            # 自動実行が有効な場合、自動で実行開始
            if self.autoExecute.get():
                self.executeFlow()
        else:
            # ノードを選択
            self.selectedNode = node
            # 選択状態を表示
            self.selectedHighlight = self.canvas.create_rectangle(
                node.x-55, node.y-25, node.x+55, node.y+25, 
                outline='red', width=3, fill=''
            )
            self.resultText.delete(1.0, tk.END)
            self.resultText.insert(tk.END, f"選択中: {node.text}\n次のノードをクリックして接続")
            self.resultText.see(tk.END)
            self.statusLabel.config(text=f"選択中: {node.text}")
    
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
                if clickedItem == node.rect or clickedItem == node.label:
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
    
    def goHome(self):
        """キャンバスをホームポジションに戻す"""
        if self.nodes or self.trays:
            # ノードやトレイがある場合は重心に移動
            items = [(node.x, node.y) for node in self.nodes] + [(tray.x, tray.y) for tray in self.trays]
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
        CoalescingExecutor.submit( self, self.processNodes)
    
    def processNodes(self):
        startTime = time.time()
        try:
            # ステータス表示
            self.root.after(0, lambda: self.statusLabel.config(text="フロー実行中..."))
            self.root.after(0, lambda: self.resultText.delete(1.0, tk.END))
            self.root.after(0, lambda: self.highlightReprocessingNodes())
            
            # トポロジカルソートで処理レベルを決定
            processLevels = self.getProcessLevels()
            
            for level, nodes in enumerate(processLevels):
                if nodes:
                    # 同レベルのノードを並列実行
                    text=""
                    sep="開始: "
                    
                    futures = []
                    for node in nodes:
                        # 再処理が必要かチェック
                        if node.needsReprocessing():
                            self.root.after(0, lambda id=id(node), t=node.text: self.showProgress( id, t, "待機中"))
                            context = {
                                'result_callback': self.showResult,
                                'progress_callback': lambda msg, current=None, total=None, id=id(node), t=node.text: self.showProgress( id, t, msg, current, total)
                            }
                            future = NodeExecutor.submit(self._executeNode, node, context)
                            futures.append((node, future))
                            text +=f"{sep}{node.text}"
                            sep=","
                        elif not self.autoExecute.get():
                            # スキップしたノードを表示
                            self.root.after(0, lambda t=node.text: self.resultText.insert(tk.END, f"スキップ: {t}\n"))
                            self.root.after(0, lambda: self.resultText.see(tk.END))
                        
                    
                    if 0<len(text):
                        self.root.after(0, lambda: self.statusLabel.config(text=f"状態: {text}"))
                    if 0<len(text) and not self.autoExecute.get():
                        self.root.after(0, lambda text=text: self.resultText.insert(tk.END, text))
                        self.root.after(0, lambda: self.resultText.insert(tk.END, f"\n"))
                        self.root.after(0, lambda: self.resultText.see(tk.END))
                    
                    # 同レベルの全ノードの完了を待つ
                    futureToNode = {future: node for node, future in futures}
                    for future in as_completed([f for n, f in futures]):
                        node = futureToNode[future]
                        elapsedMs = future.result()
                        self.root.after(0, lambda t=node.text, ms=elapsedMs: self.resultText.insert(tk.END, f"完了: {t} ({ms}ms)\n"))
                        self.root.after(0, lambda: self.resultText.see(tk.END))
                        self.root.after(0, lambda t=node.text: self.statusLabel.config(text=f"完了: {t}"))
                        self.root.after(0, lambda: self._clearAllProgress())
                        self.root.after(0, lambda: self.highlightReprocessingNodes())
                        self.root.after(0, lambda n=node: n.updateResult())
            
            if not self.autoExecute.get():
                self.root.after(0, lambda: self.resultText.insert(tk.END, f"実行完了\n"))
                self.root.after(0, lambda: self.resultText.see(tk.END))
            self.root.after(0, lambda: self.statusLabel.config(text="状態: 実行完了"))
            self.root.after(0, lambda: self._clearAllProgress())
            self.root.after(0, lambda: self.highlightReprocessingNodes())
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            errorMsg = f"フロー実行エラー: {str(e)}"
            self.root.after(0, lambda: messagebox.showerror("エラー", errorMsg))
            self.root.after(0, lambda: self.statusLabel.config(text="状態: エラー"))
            self.root.after(0, lambda: self._clearAllProgress())
            self.root.after(0, lambda: self.highlightReprocessingNodes())
        endTime = time.time()
        elapsedMs = int((endTime - startTime) * 1000)
        self.root.after(0, lambda ms=elapsedMs: self.resultText.insert(tk.END, f"({ms}ms)\n"))
    
    def getProcessLevels(self):
        """ノードを依存レベル別にグループ化"""
        # 入次数を計算
        inDegree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for connectedNode in node.outputNodes:
                inDegree[connectedNode] += 1
        
        levels = []
        remaining = set(self.nodes)
        
        while remaining:
            # 現在のレベルで実行可能なノードを収集
            currentLevel = [node for node in remaining if inDegree[node] == 0]
            if not currentLevel:
                break
            
            levels.append(currentLevel)
            
            # 処理したノードを削除し、後続ノードの入次数を更新
            for node in currentLevel:
                remaining.remove(node)
                for connectedNode in node.outputNodes:
                    if connectedNode in remaining:
                        inDegree[connectedNode] -= 1
        
        return levels
    
    def _executeNode(self, node, context):
        """ノード実行"""
        try:
            # 時間を測定
            startTime = time.time()
            node.process(context)
            # 実行後にハッシュを更新
            node.updateExecutionHashes()
            endTime = time.time()
            elapsedMs = int((endTime - startTime) * 1000)
            return elapsedMs
        except Exception as e:
            raise Exception(f"ノード '{node.text}' でエラー") from e
    

    def saveFlow(self):
        if not self.nodes and not self.trays:
            messagebox.showwarning("警告", "保存するフローがありません")
            return
        
        filePath = filedialog.asksaveasfilename(
            defaultextension=".flow",
            filetypes=[("flow files", "*.flow"), ("All files", "*.*")]
        )
        
        if not filePath:
            return
        
        # 現在のflowファイルパスを保存
        self.currentFlowPath = filePath
        
        # ノードのIDマッピングを作成
        nodeIds = {node: i for i, node in enumerate(self.nodes)}
        
        flowData = {
            "nodes": [],
            "connections": [],
            "trays": []
        }
        
        # ノード情報を保存
        for node in self.nodes:
            # ノードのZ-orderを取得
            allItems = self.canvas.find_all()
            nodeZOrder = max(allItems.index(node.rect), allItems.index(node.label))
            
            nodeData = {
                "id": nodeIds[node],
                "type": node.type,
                "x": node.x,
                "y": node.y,
                "text": node.text,
                "zOrder": nodeZOrder
            }
            
            # ノード固有のデータを保存
            if hasattr(node, 'store'):
                node.store(nodeData)
            
            flowData["nodes"].append(nodeData)
        
        # トレイ情報を保存
        for tray in self.trays:
            # トレイのZ-orderを取得
            allItems = self.canvas.find_all()
            trayZOrder = max(allItems.index(tray.rect), allItems.index(tray.label))
            trayData = tray.toDict()
            trayData['zOrder'] = trayZOrder
            flowData["trays"].append(trayData)
        
        # 接続情報を保存
        for node in self.nodes:
            for outputNode in node.outputNodes:
                flowData["connections"].append({
                    "from": nodeIds[node],
                    "to": nodeIds[outputNode]
                })
        
        try:
            with open(filePath, 'w', encoding='utf-8') as f:
                json.dump(flowData, f, ensure_ascii=False, indent=2)
            
            # ウィンドウタイトルにファイル名を追記
            fileName = os.path.basename(filePath)
            self.root.title(f"{self.text} - {fileName}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            messagebox.showerror("エラー", f"保存に失敗しました: {str(e)}")
    
    def loadFlow(self):
        filePath = filedialog.askopenfilename(
            filetypes=[("flow files", "*.flow"), ("All files", "*.*")]
        )
        
        if not filePath:
            return
            
        # 現在のflowファイルパスを保存
        self.currentFlowPath = filePath
        
        try:
            with open(filePath, 'r', encoding='utf-8') as f:
                flowData = json.load(f)
            
            # 自動実行をオフにする
            self.autoExecute.set(False)
            
            # 現在のフローをクリア
            self.clearFlow()
            
            # ノードとトレイをZ-order順で作成
            allItems = []
            
            # ノード情報を収集
            for nodeData in flowData["nodes"]:
                allItems.append(('node', nodeData))
            
            # トレイ情報を収集
            if "trays" in flowData:
                for trayData in flowData["trays"]:
                    allItems.append(('tray', trayData))
            
            # Z-orderでソート
            allItems.sort(key=lambda x: x[1].get('zOrder', 0))
            
            # 順序を維持して作成
            nodeMap = {}
            for itemType, itemData in allItems:
                if itemType == 'node':
                    node = self.createNodeFromData(itemData)
                    if node:
                        # ノード固有のデータ復元
                        if hasattr(node, 'restore'):
                            node.restore(itemData)
                        node._loadFlowId = itemData["id"]
                        
                        nodeMap[itemData["id"]] = node
                        self.nodes.append(node)
                elif itemType == 'tray':
                    tray = Tray(self.canvas, self, 0, 0)
                    tray.fromDict(itemData)
                    self.trays.append(tray)
            
            # 接続線を最上位に配置
            
            # 接続を作成（双方向）
            for connection in flowData["connections"]:
                fromNode = nodeMap[connection["from"]]
                toNode = nodeMap[connection["to"]]
                fromNode.outputNodes.append(toNode)
                toNode.inputNodes.append(fromNode)
                
                # 接続線を描画
                x1, y1, x2, y2 = self._getConnectionPoints(fromNode, toNode)
                line = self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, width=2, fill='red')
                self.connectionLines.append((fromNode, toNode, line))
            
            # 接続線を最上位に配置
            for _, _, line in self.connectionLines:
                self.canvas.tag_raise(line)
            
            # トレイの外観を更新
            self.updateAllTrayAppearance()
            
            # canvasサイズを調整
            self.adjustCanvasSize()
            
            # ウィンドウタイトルにファイル名を追記
            fileName = os.path.basename(filePath)
            self.root.title(f"{self.text} - {fileName}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            messagebox.showerror("エラー", f"読み込みに失敗しました: {str(e)}")
    
    def createNodeFromData(self, nodeData):
        # ファイル選択をスキップしてノードを作成
        return NodeFactory.createNode(nodeData["type"], self.canvas, self, nodeData["x"], nodeData["y"], nonDialog=True)
    
    def clearFlow(self):
        # ノードのイベントバインディングを解除してFlowData参照をクリア
        for node in self.nodes:
            node.cleanUp()
            
        # キャンバスをクリア
        self.canvas.delete("all")
        # ノード、トレイ、接続をクリア
        self.nodes = []
        self.trays = []
        self.connectionLines = []
        self.selectedNode = None
        # 選択ハイライトをクリア
        self.selectedHighlight = None
        
    def deleteNode(self, node):
        node.cleanUp()
        
        # ノードをキャンバスから削除
        self.canvas.delete(node.rect)
        self.canvas.delete(node.label)
        
        # 削除対象ノードに関連する接続線を削除
        newConnectionLines = []
        for f, t, l in self.connectionLines:
            if f == node or t == node:
                self.canvas.delete(l)
            else:
                newConnectionLines.append((f, t, l))
        self.connectionLines = newConnectionLines
        
        # ノードの接続をクリア（双方向）
        for n in self.nodes:
            if node in n.outputNodes:
                n.outputNodes.remove(node)
            if node in n.inputNodes:
                n.inputNodes.remove(node)
        
        # 削除されるノードの接続もクリア（双方向）
        for connectedNode in node.outputNodes:
            if node in connectedNode.inputNodes:
                connectedNode.inputNodes.remove(node)
        for inputNode in node.inputNodes:
            if node in inputNode.outputNodes:
                inputNode.outputNodes.remove(node)
        
        node.outputNodes.clear()
        node.inputNodes.clear()
        
        # ノードリストから削除
        self.nodes.remove(node)
        
        # 選択状態をクリア
        if self.selectedNode == node:
            self.clearSelectedHighlight()
            self.selectedNode = None
        
        # 強調表示更新
        self.highlightReprocessingNodes()
        
        # 自動実行が有効な場合、自動で実行開始
        if self.autoExecute.get():
            self.executeFlow()
    
    def showResult(self, headers, data):
        self.resultText.delete(1.0, tk.END)
        self.resultText.insert(tk.END, f"総行数: {len(data)}\n")
        self.resultText.insert(tk.END, ','.join(headers) + '\n')
        for row in data[:10]:
            self.resultText.insert(tk.END, ','.join(row) + '\n')
    
    def highlightReprocessingNodes(self):
        """再実行されるノードを強調表示"""
        # 既存のハイライトをクリア
        self.clearReprocessingHighlights()
        
        # 再実行が必要なノードを特定してハイライト
        for node in self.nodes:
            if self._needsReprocessingRecursive(node):
                highlight = self.canvas.create_rectangle(
                    node.x-55, node.y-25, node.x+55, node.y+25,
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
    
    def onNodeConfigChanged(self, changedNode):
        """ノードの設定変更時に呼び出される"""
        # 強調表示更新
        self.highlightReprocessingNodes()
        
        # 自動実行が有効かつ再実行が必要なノードがある場合、自動で実行開始
        if self.autoExecute.get() and self.reprocessingHighlights:
            self.executeFlow()
    
    def _clearAllProgress(self):
        """全てのプログレスバーをクリア"""
        for progressInfo in self.progressBars:
            progressInfo['label'].config(text="待機中")
            progressInfo['bar'].config(value=0)
        self.activeProgressBars.clear()
    
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
        
        if nodeId in self.activeProgressBars:
            progressInfo = self.progressBars[self.activeProgressBars[nodeId]]
            progressInfo['label'].config(text=f"{nodeName}: {message}")
            
            if current is not None and total is not None and total > 0:
                progress = (current / total) * 100
                progressInfo['bar'].config(value=progress)
            else:
                progressInfo['bar'].config(value=0)
    
    def updateCacheStats(self):
        """キャッシュ統計を更新"""
        
        flowNodeCount = f"{len(self.nodes)}個"
        trayCount = f"{len(self.trays)}個" if self.trays else ""
        
        cacheNodeCount = f"{self.getNodeCount()}個"
        
        cacheSize, storageSize, cacheMissCount, purgeCount, saveCount, loadCount = CacheManager.getCacheStats()
        
        # キャッシュサイズを適切な単位で表示
        if cacheSize < 10*1024:
            cacheStr = f"{int(cacheSize)}B"
        elif cacheSize < 10*1024*1024:
            cacheStr = f"{int(cacheSize/1024)}KB"
        elif cacheSize < 10*1024*1024*1024:
            cacheStr = f"{int(cacheSize/1024/1024)}MB"
        else:
            cacheStr = f"{int(cacheSize/1024/1024/1024)}GB"
        
        # ディスクサイズを適切な単位で表示
        if storageSize < 10*1024:
            storageStr = f"{int(storageSize)}B"
        elif storageSize < 10*1024*1024:
            storageStr = f"{int(storageSize/1024)}KB"
        elif storageSize < 10*1024*1024*1024:
            storageStr = f"{int(storageSize/1024/1024)}MB"
        else:
            storageStr = f"{int(storageSize/1024/1024/1024)}GB"
        
        # 使用量ラベルを更新
        nodeInfo = f"Node: {flowNodeCount}"
        if trayCount:
            nodeInfo += f" Tray: {trayCount}"
        
        if Debug.LEVEL_NONE < Debug.LEVEL:
            self.usageLabel.config(text=f"CacheMissCount: {cacheMissCount} PurgeCount: {purgeCount} SaveCount:{saveCount} LoadCount: {loadCount} {nodeInfo} Cache:{cacheNodeCount} {cacheStr} storage: {storageStr}")
        else:
            self.usageLabel.config(text=f"{nodeInfo} Cache: {cacheNodeCount} {cacheStr} storage: {storageStr}")
        
        # 5秒後に再度更新
        self.root.after(5000, self.updateCacheStats)

    def getNodeCount(self):
        nodes = []
        for obj in gc.get_objects():
            if hasattr(obj, '__class__') and isinstance( obj, FlowNode):
                nodes.append(obj)
        return(len(nodes))

    def forceGarbageCollection(self):
        """ガベージコレクションを強制実行"""
        # 実行前のメモリ使用量を取得
        beforeNodeCount = self.getNodeCount()
        beforeCache, beforeStorage, _, _, _, _ = CacheManager.getCacheStats()
        
        # ガベージコレクションを実行
        collected = gc.collect()
        
        # 実行後のメモリ使用量を取得
        afterNodeCount = self.getNodeCount()
        afterCache, afterStorage, _, _, _, _  = CacheManager.getCacheStats()
        
        # 結果を表示
        freedNodeCount = beforeNodeCount - afterNodeCount
        freedMemory = beforeCache - afterCache
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
            self._debugNodeReferences()
            print("========================")
            if hasattr(self, '_bugReportLog'):
                for msg in self._bugReportLog:
                    print(msg)
                print("========================")

    def toggleDebugMode(self, event):
        """デバッグモードを切り替える"""
        Debug.LEVEL = Debug.LEVEL_NONE if Debug.LEVEL_NONE != Debug.LEVEL else Debug.LEVEL_ALL
        self.statusLabel.config(text=f"状態: DEBUGモード {'OFF' if Debug.LEVEL == Debug.LEVEL_NONE else 'ON'}")

        for node in self.nodes:
            node.updateNodeText()

        return "break"
    
    def bugReport(self, name, message):
        if not hasattr(self, '_bugReportLog'):
            self._bugReportLog=[]
        text = f"{datetime.datetime.now().isoformat()}: {name}: {message}"
        self._bugReportLog.append(text)
        if Debug.LEVEL_NONE < Debug.LEVEL:
            print(text)

    def _debugNodeReferences(self):
        """ノードの参照状況をデバッグ出力"""
        # 全オブジェクトからflowNodeを探す
        objs = []
        for obj in gc.get_objects():
            if(  isinstance( obj, FlowNode)
        #      or isinstance( obj, FlowData)
              ):
                objs.append(obj)
        
        print(f"残存flowNode数: {len(objs)}")
        
        for i, obj in enumerate(objs):
            print(f"残存ノード{i}: {getattr(obj, 'text', type(obj).__name__)} (id: {id(obj)})")
            
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

    def _debugReport(self):
        if hasattr(self, '_bugReportLog'):
            print("バグレポート")
            for log in self._bugReportLog:
                print(log)


if __name__ == '__main__':
    root = tk.Tk()
    app = FlowEditor(root)
    root.mainloop()