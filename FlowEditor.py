'''
Created on 2025/10/21

@author: Masakazu Inoue
'''

import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import json
import sys
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import atexit
from nodes import NodeFactory
from base.ResultWindow import ResultWindow

# グローバルスレッドプール
MAX_NODE_WORKERS = 4
NodeExecutor = ThreadPoolExecutor(max_workers=MAX_NODE_WORKERS)
atexit.register(NodeExecutor.shutdown)

class FlowEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Flow Editor")
        self.nodes = []
        self.reprocessingHighlights = []
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
        
        # 使い方説明
        infoLabel = tk.Label(self.root, text="使い方: 1.右クリックでノード追加 2.ドラッグで移動 3.クリックで接続 4.実行", bg='lightyellow')
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
        
        self.usageLabel = tk.Label(statusFrame, text="Cache: 0B Disk: 0B", bg='lightgray', anchor=tk.E)
        self.usageLabel.pack(side=tk.RIGHT)
        
        # キャッシュ統計の定期更新
        self.updateCacheStats()
        self.root.after(5000, self.updateCacheStats)
    
    def bringChildWindowsToFront(self):
        """子画面を最前面に持ち上げる"""
        childWindows = []
        
        # 各ノードの設定ダイアログをチェック
        for node in self.nodes:
            if hasattr(node, '_settings_dialog') and node._settings_dialog.winfo_exists():
                childWindows.append(node._settings_dialog)
            if hasattr(node, '_result_window') and node._result_window.winfo_exists():
                childWindows.append(node._result_window)
        
        # 子画面を最前面に持ち上げ
        for window in childWindows:
            window.lift()
            window.focus_force()
        
        if childWindows:
            self.statusLabel.config(text=f"状態: {len(childWindows)}個の子画面を最前面に移動")
        else:
            self.statusLabel.config(text="状態: 最前面に移動する子画面がありません")
    
    def onCanvasRightRelease(self, event):
        # ノード以外の場所をクリックした場合のみメニューを表示
        isNodeClick = False

        # canvas座標に変換
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        clickedItems = self.canvas.find_overlapping(x, y, x, y)
        if clickedItems:
            clickedItem = clickedItems[0]
            for node in self.nodes:
                if clickedItem == node.rect or clickedItem == node.label:
                    isNodeClick = True
                    break
        
        if not isNodeClick:
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
        except ValueError:
            pass
    
    def updateNodeText(self, node, text):
        self.canvas.itemconfig(node.label, text=text)
    
    def adjustCanvasSize(self):
        """ノードの位置に合わせてcanvasサイズを調整"""
        if not self.nodes:
            return
        
        # 全ノードの範囲を計算
        minX = min(node.x - 60 for node in self.nodes)
        maxX = max(node.x + 60 for node in self.nodes)
        minY = min(node.y - 30 for node in self.nodes)
        maxY = max(node.y + 30 for node in self.nodes)
        
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
        if hasattr(self, 'selectedHighlight'):
            self.canvas.delete(self.selectedHighlight)
        
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
            if hasattr(self, 'selectedHighlight'):
                self.canvas.delete(self.selectedHighlight)
            self.selectedNode = None
            self.resultText.delete(1.0, tk.END)
            self.resultText.insert(tk.END, "選択をクリアしました")
            self.resultText.see(tk.END)
            self.statusLabel.config(text="状態: 選択クリア")
    
    def onCanvasRelease(self, event):
        # ノード以外の場所をクリックした場合のみ選択をクリア
        isNodeClick = False

        # canvas座標に変換
        canvasX = self.canvas.canvasx(event.x)
        canvasY = self.canvas.canvasy(event.y)
        
        clickedItems = self.canvas.find_overlapping(canvasX, canvasY, canvasX, canvasY)
        if clickedItems:
            clickedItem = clickedItems[0]
            for node in self.nodes:
                if clickedItem == node.rect or clickedItem == node.label:
                    isNodeClick = True
                    break
        
        if not isNodeClick:
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
        if self.nodes:
            # ノードがある場合は重心に移動
            centerX = sum(node.x for node in self.nodes) / len(self.nodes)
            centerY = sum(node.y for node in self.nodes) / len(self.nodes)
            
            scrollRegion = self.canvas.cget('scrollregion')
            if scrollRegion:
                x1, y1, x2, y2 = map(float, scrollRegion.split())
                relativeX = (centerX - x1) / (x2 - x1) if x2 > x1 else 0.5
                relativeY = (centerY - y1) / (y2 - y1) if y2 > y1 else 0.5
                self.canvas.xview_moveto(relativeX - 0.25)
                self.canvas.yview_moveto(relativeY - 0.25)
        else:
            # ノードがない場合は原点に戻す
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
    
    def executeFlow(self):
        if not self.nodes:
            messagebox.showwarning("警告", "フローが空です")
            return
        
        # フロー実行を別スレッドで実行
        thread = threading.Thread(target=self.processNodes)
        thread.daemon = True
        thread.start()
    
    def processNodes(self):
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
                    sep="実行: "
                    futures = []
                    for node in nodes:
                        # 再処理が必要かチェック
                        if node.needsReprocessing():
                            self.root.after(0, lambda: self.showProgress(id(node), node.text, "待機中"))
                            context = {
                                'result_callback': self.showResult,
                                'progress_callback': lambda msg, current=None, total=None, n=node: self.showProgress(id(n), n.text, msg, current, total)
                            }
                            future = NodeExecutor.submit(self._executeNodeWithTiming, node, context)
                            futures.append((node, future))
                            text +=f"{sep}{node.text}"
                            sep=","
                        elif not self.autoExecute.get():
                            # スキップしたノードを表示
                            self.root.after(0, lambda n=node: self.resultText.insert(tk.END, f"スキップ: {n.text}\n"))
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
                        self.root.after(0, lambda n=node, ms=elapsedMs: self.resultText.insert(tk.END, f"完了: {n.text} ({ms}ms)\n"))
                        self.root.after(0, lambda: self.resultText.see(tk.END))
                        self.root.after(0, lambda n=node: self.statusLabel.config(text=f"完了: {n.text}"))
                        self.root.after(0, lambda: self._clearAllProgress())
                        self.root.after(0, lambda: self.highlightReprocessingNodes())
                        self.root.after(0, lambda n=node: self._updateOpenResultWindows(n))
            
            if not self.autoExecute.get():
                self.root.after(0, lambda: self.resultText.insert(tk.END, f"実行完了\n"))
                self.root.after(0, lambda: self.resultText.see(tk.END))
            self.root.after(0, lambda: self.statusLabel.config(text="状態: 実行完了"))
            self.root.after(0, lambda: self._clearAllProgress())
            self.root.after(0, lambda: self.highlightReprocessingNodes())
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            errorMsg = f"フロー実行エラー: {str(e)}\n\nトラックバック:\n{tb}"
            self.root.after(0, lambda: messagebox.showerror("エラー", errorMsg))
            self.root.after(0, lambda: self.statusLabel.config(text="状態: エラー"))
            self.root.after(0, lambda: self._clearAllProgress())
            self.root.after(0, lambda: self.highlightReprocessingNodes())
    
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
    
    def _executeNodeWithTiming(self, node, context):
        """ノード実行時間を測定"""
        try:
            startTime = time.time()
            node.process(context)
            # 実行後にハッシュを更新
            node.updateExecutionHashes()
            endTime = time.time()
            elapsedMs = int((endTime - startTime) * 1000)
            return elapsedMs
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            errorMsg = f"ノード '{node.text}' でエラー: {str(e)}\n\nトラックバック:\n{tb}"
            raise Exception(errorMsg)
    

    def saveFlow(self):
        if not self.nodes:
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
            "connections": []
        }
        
        # ノード情報を保存
        for node in self.nodes:
            nodeData = {
                "id": nodeIds[node],
                "type": node.type,
                "x": node.x,
                "y": node.y,
                "text": node.text
            }
            
            # ノード固有のデータを保存
            if hasattr(node, 'store'):
                node.store(nodeData)
            
            flowData["nodes"].append(nodeData)
        
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
            self.root.title(f"Flow Editor - {fileName}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            errorMsg = f"保存に失敗しました: {str(e)}\n\nトラックバック:\n{tb}"
            messagebox.showerror("エラー", errorMsg)
    
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
            
            # 現在のフローをクリア
            self.clearFlow()
            
            # ノードを作成
            nodeMap = {}
            for nodeData in flowData["nodes"]:
                node = self.createNodeFromData(nodeData)
                if node:
                    # ノード固有のデータ復元
                    if hasattr(node, 'restore'):
                        node.restore(nodeData)
                    
                    nodeMap[nodeData["id"]] = node
                    self.nodes.append(node)
            
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
            
            # canvasサイズを調整
            self.adjustCanvasSize()
            
            # ウィンドウタイトルにファイル名を追記
            fileName = os.path.basename(filePath)
            self.root.title(f"Flow Editor - {fileName}")
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            errorMsg = f"読み込みに失敗しました: {str(e)}\n\nトラックバック:\n{tb}"
            messagebox.showerror("エラー", errorMsg)
    
    def createNodeFromData(self, nodeData):
        # ファイル選択をスキップしてノードを作成
        return NodeFactory.createNode(nodeData["type"], self.canvas, self, nodeData["x"], nodeData["y"], nonDialog=True)
    
    def clearFlow(self):
        # キャンバスをクリア
        self.canvas.delete("all")
        # ノードと接続をクリア
        self.nodes = []
        self.connectionLines = []
        self.selectedNode = None
        # 選択ハイライトをクリア
        if hasattr(self, 'selectedHighlight'):
            delattr(self, 'selectedHighlight')
    
    def deleteNode(self, node):
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
            if hasattr(self, 'selectedHighlight'):
                self.canvas.delete(self.selectedHighlight)
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
        for highlight in self.reprocessingHighlights:
            self.canvas.delete(highlight)
        self.reprocessingHighlights = []
        
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
    
    def showNodeResult(self, node):
        """ノードの処理結果を表示"""
        result_window = ResultWindow(self.root, node)
        result_window.show()
    
    def _updateResultWindow(self, node):
        """結果ウィンドウの内容を更新"""
        result_window = ResultWindow(self.root, node)
        result_window.update()
        
    def _updateOpenResultWindows(self, node):
        """開いている結果ウィンドウを更新"""
        if hasattr(node, '_result_window'):
            try:
                if node._result_window.winfo_exists():
                    self._updateResultWindow(node)
            except tk.TclError:
                # ウィンドウが既に閉じられている場合
                if hasattr(node, '_result_window'):
                    delattr(node, '_result_window')
                if hasattr(node, '_result_text_widget'):
                    delattr(node, '_result_text_widget')
    
    def updateCacheStats(self):
        """キャッシュ統計を更新"""
        from base.FlowData import FlowData
        cacheSize, diskSize = FlowData.getCacheStats()
        
        # キャッシュサイズを適切な単位で表示
        if cacheSize < 1024:
            cacheStr = f"{cacheSize}B"
        elif cacheSize < 1024*1024:
            cacheStr = f"{cacheSize/1024:.1f}KB"
        else:
            cacheStr = f"{cacheSize/(1024*1024):.1f}MB"
        
        # ディスクサイズを適切な単位で表示
        if diskSize < 1024:
            diskStr = f"{diskSize}B"
        elif diskSize < 1024*1024:
            diskStr = f"{diskSize/1024:.1f}KB"
        else:
            diskStr = f"{diskSize/(1024*1024):.1f}MB"
        
        # 使用量ラベルを更新
        self.usageLabel.config(text=f"Cache: {cacheStr} Disk: {diskStr}")
        
        # 5秒後に再度更新
        self.root.after(5000, self.updateCacheStats)

if __name__ == '__main__':
    root = tk.Tk()
    app = FlowEditor(root)
    root.mainloop()