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
from nodes import NodeFactory
from config import MAX_WORKERS

class FlowEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Flow Editor")
        self.nodes = []
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
        
        self.canvas.bind('<Button-1>', self.onCanvasClick)
        self.canvas.bind('<Button-3>', self.onCanvasRightClick)
        self.canvas.bind('<MouseWheel>', self.onMouseWheel)
        self.canvas.bind('<Shift-MouseWheel>', self.onShiftMouseWheel)
        
        # 右クリックメニュー
        self.contextMenu = tk.Menu(self.root, tearoff=0)
        for label, nodeType in NodeFactory.getMenuItems():
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
        
        # MAX_WORKERS数のプログレスバーを事前作成
        self.progressBars = []
        for i in range(MAX_WORKERS):
            frame = tk.Frame(self.progressFrame)
            frame.pack(fill=tk.X, pady=1)
            
            label = tk.Label(frame, text="待機中", anchor=tk.W, width=20)
            label.pack(side=tk.LEFT)
            
            bar = ttk.Progressbar(frame, mode='determinate')
            bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
            
            self.progressBars.append({'frame': frame, 'label': label, 'bar': bar})
        
        self.activeProgressBars = {}
        
        # ステータス表示（一番下段）
        self.statusLabel = tk.Label(self.root, text="状態: 待機中", bg='lightgray', relief=tk.SUNKEN, anchor=tk.W)
        self.statusLabel.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
    
    def onCanvasRightClick(self, event):
        # ノード以外の場所をクリックした場合のみメニューを表示
        isNodeClick = False

        clickedItems = self.canvas.find_overlapping(event.x, event.y,event.x, event.y)
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
            node = NodeFactory.createNode(nodeType, self.canvas, self, self.rightClickX, self.rightClickY)
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
    
    def updateConnections(self):
        """接続線の位置を更新"""
        for fromNode, toNode, line in self.connectionLines:
            self.canvas.coords(line, fromNode.x+50, fromNode.y, toNode.x-50, toNode.y)
    
    def selectNode(self, node):
        self.statusLabel.config(text=f"ノードクリック: {node.text}")
        
        # 前の選択をクリア
        if hasattr(self, 'selectedHighlight'):
            self.canvas.delete(self.selectedHighlight)
        
        if self.selectedNode and self.selectedNode != node:
            # 既存の接続をチェック
            if node in self.selectedNode.connections:
                # 接続を削除
                self.selectedNode.connections.remove(node)
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
            else:
                # 接続を作成
                self.selectedNode.connections.append(node)
                line = self.canvas.create_line(self.selectedNode.x+50, self.selectedNode.y, 
                                             node.x-50, node.y, arrow=tk.LAST, width=2, fill='red')
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
    
    def onCanvasClick(self, event):
        # ノード以外の場所をクリックした場合のみ選択をクリア
        isNodeClick = False

        clickedItems = self.canvas.find_overlapping(event.x, event.y,event.x, event.y)
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
            
            # レベル毎に並列処理
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for level, nodes in enumerate(processLevels):
                    if nodes:
                        # 同レベルのノードを並列実行
                        text=""
                        sep="実行: "
                        futures = []
                        for node in nodes:
                            # 接続元ノードを収集
                            inputNodes = [n for n in self.nodes if node in n.connections]
                            
                            # 再処理が必要かチェック
                            if node.needsReprocessing(inputNodes):
                                self.root.after(0, lambda: self.showProgress(id(node), node.text, "待機中"))
                                context = {
                                    'input_nodes': inputNodes,
                                    'result_callback': self.showResult,
                                    'progress_callback': lambda msg, current=None, total=None, n=node: self.showProgress(id(n), n.text, msg, current, total)
                                }
                                future = executor.submit(self._executeNodeWithTiming, node, context)
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
                            self.root.after(0, lambda: self._updateOpenResultWindows())
            
            if not self.autoExecute.get():
                self.root.after(0, lambda: self.resultText.insert(tk.END, f"実行完了\n"))
                self.root.after(0, lambda: self.resultText.see(tk.END))
            self.root.after(0, lambda: self.statusLabel.config(text="状態: 実行完了"))
            self.root.after(0, lambda: self._clearAllProgress())
            self.root.after(0, lambda: self.highlightReprocessingNodes())
            self.root.after(0, lambda: self._updateOpenResultWindows())
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            errorMsg = f"フロー実行エラー: {str(e)}\n\nトラックバック:\n{tb}"
            self.root.after(0, lambda: messagebox.showerror("エラー", errorMsg))
            self.root.after(0, lambda: self.statusLabel.config(text="状態: エラー"))
            self.root.after(0, lambda: self._clearAllProgress())
            self.root.after(0, lambda: self.highlightReprocessingNodes())
            self.root.after(0, lambda: self._updateOpenResultWindows())
    
    def getProcessLevels(self):
        """ノードを依存レベル別にグループ化"""
        # 入次数を計算
        inDegree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for connectedNode in node.connections:
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
                for connectedNode in node.connections:
                    if connectedNode in remaining:
                        inDegree[connectedNode] -= 1
        
        return levels
    
    def _executeNodeWithTiming(self, node, context):
        """ノード実行時間を測定"""
        try:
            startTime = time.time()
            node.process(context)
            # 実行後にハッシュを更新
            node.updateExecutionHashes(context['input_nodes'])
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
            for connectedNode in node.connections:
                flowData["connections"].append({
                    "from": nodeIds[node],
                    "to": nodeIds[connectedNode]
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
            
            # 接続を作成
            for connection in flowData["connections"]:
                fromNode = nodeMap[connection["from"]]
                toNode = nodeMap[connection["to"]]
                fromNode.connections.append(toNode)
                
                # 接続線を描画
                line = self.canvas.create_line(fromNode.x+50, fromNode.y, 
                                             toNode.x-50, toNode.y, arrow=tk.LAST, width=2, fill='red')
                self.connectionLines.append((fromNode, toNode, line))
            
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
        
        # ノードの接続をクリア
        for n in self.nodes:
            if node in n.connections:
                n.connections.remove(node)
        
        # 削除されるノードの接続もクリア
        node.connections.clear()
        
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
        if hasattr(self, 'reprocessingHighlights'):
            for highlight in self.reprocessingHighlights:
                self.canvas.delete(highlight)
            self.reprocessingHighlights = []
        
        # 再実行が必要なノードを特定してハイライト
        self.reprocessingHighlights = []
        for node in self.nodes:
            if self._needsReprocessingRecursive(node):
                highlight = self.canvas.create_rectangle(
                    node.x-55, node.y-25, node.x+55, node.y+25,
                    outline='orange', width=4, fill='', dash=(5, 5)
                )
                self.reprocessingHighlights.append(highlight)
    
    def _needsReprocessingRecursive(self, node):
        """上流を再帰的にチェックして再実行が必要か判定"""
        inputNodes = [n for n in self.nodes if node in n.connections]
        
        # 自分自身の設定が変更されたかチェック
        if node.needsReprocessing(inputNodes):
            return True
        
        # 上流ノードのいずれかが再実行必要かチェック
        for inputNode in inputNodes:
            if self._needsReprocessingRecursive(inputNode):
                return True
        
        return False
    
    def onNodeConfigChanged(self, changedNode):
        """ノードの設定変更時に呼び出される"""
        # 強調表示更新
        self.highlightReprocessingNodes()
        
        # 自動実行が有効な場合、自動で実行開始
        if self.autoExecute.get():
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
        # 既存の結果ウィンドウをチェック
        if hasattr(node, '_result_window') and node._result_window.winfo_exists():
            # 既存ウィンドウを更新
            self._updateResultWindow(node)
            node._result_window.lift()
            return
        
        # 新しいウィンドウで結果を表示
        resultWindow = tk.Toplevel(self.root)
        resultWindow.title(f"{node.text} - 処理結果")
        resultWindow.geometry("600x400")
        
        # ウィンドウ参照を保存
        node._result_window = resultWindow
        
        # スクロールバー付きテキストエリア
        frame = tk.Frame(resultWindow)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(frame, wrap=tk.WORD)
        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # テキストウィジェット参照を保存
        node._result_text_widget = text_widget
        
        # ウィンドウが閉じられたときのクリーンアップ
        def on_close():
            if hasattr(node, '_result_window'):
                delattr(node, '_result_window')
            if hasattr(node, '_result_text_widget'):
                delattr(node, '_result_text_widget')
            resultWindow.destroy()
        
        resultWindow.protocol("WM_DELETE_WINDOW", on_close)
        
        # 初回表示
        self._updateResultWindow(node)
    
    def _updateResultWindow(self, node):
        """結果ウィンドウの内容を更新"""
        if not hasattr(node, '_result_text_widget'):
            return
        
        text_widget = node._result_text_widget
        text_widget.config(state=tk.NORMAL)
        text_widget.delete(1.0, tk.END)
        
        # データを表示
        for dataIdx, flowData in enumerate(node.flowDatas):
            if len(node.flowDatas) > 1:
                text_widget.insert(tk.END, f"=== データ {dataIdx + 1} ===\n")
            
            self._displayFlowData(text_widget, flowData)
            text_widget.insert(tk.END, "\n")
        
        text_widget.config(state=tk.DISABLED)
    
    def _displayFlowData(self, text_widget, flowData):
        """フローデータをtypeに応じて表示"""
        headers = flowData.headers if flowData.headers else {}
        dataType = headers.get('type', 'unknown')
        width, height, planeCount = flowData.getDimensions()
        
        text_widget.insert(tk.END, f"Type: {dataType}\n")
        text_widget.insert(tk.END, f"Dimensions: {width} x {height} x {planeCount}\n")
        
        if   dataType == 'tensor': self._displayTensorData(text_widget, flowData, headers)
        elif dataType == 'matrix': self._displayMatrixData(text_widget, flowData, headers)
        elif dataType == 'image' : self._displayImageData(text_widget, flowData, headers)
        else:                      self._displayGenericData(text_widget, flowData)
    
    def _displayTensorData(self, text_widget, flowData, headers):
        """テンソルデータを表示"""
        text_widget.insert(tk.END, "\nテンソルデータ:\n")
        
        columns = headers.get('columns', [])
        lines = headers.get('lines', [])
        planes = headers.get('planes', [])
        
        for planeIdx, planeName in enumerate(planes):
            text_widget.insert(tk.END, f"\n[{planeName} プレーン]\n")
            
            # ヘッダー行
            if columns:
                text_widget.insert(tk.END, "\t" + "\t".join(columns) + "\n")
            
            # データ行
            width, height, _ = flowData.getDimensions()
            for y in range(height):
                lineLabel = lines[y] if y < len(lines) else f"row_{y}"
                text_widget.insert(tk.END, f"{lineLabel}\t")
                
                row_data = []
                for x in range(width):
                    block = flowData.getBlock(planeIdx, x, y)
                    if block and hasattr(block, 'data') and block.data is not None:
                        try:
                            value = block.data[y][x] if len(block.data) > y and len(block.data[y]) > x else 0
                            row_data.append(f"{value:.6f}")
                        except (IndexError, TypeError):
                            row_data.append("0.000000")
                    else:
                        row_data.append("0.000000")
                
                text_widget.insert(tk.END, "\t".join(row_data) + "\n")
    
    def _displayMatrixData(self, text_widget, flowData, headers):
        """マトリックスデータを表示"""
        text_widget.insert(tk.END, "\nマトリックスデータ:\n")
        
        columns = headers.get('columns', [])
        lines = headers.get('lines', [])
        
        # ヘッダー行
        if columns:
            text_widget.insert(tk.END, "\t" + "\t".join(columns) + "\n")
        
        # データ行 (最初の10行のみ表示)
        width, height, _ = flowData.getDimensions()
        displayRows = min(height, 10)
        
        for y in range(displayRows):
            lineLabel = lines[y] if y < len(lines) else f"row_{y}"
            text_widget.insert(tk.END, f"{lineLabel}\t")
            
            row_data = []
            for x in range(min(width, 10)):  # 最初の10列のみ
                block = flowData.getBlock(0, x, y)
                if block and hasattr(block, 'data') and block.data is not None:
                    try:
                        value = block.data[y][x] if len(block.data) > y and len(block.data[y]) > x else 0
                        row_data.append(str(value))
                    except (IndexError, TypeError):
                        row_data.append("0")
                else:
                    row_data.append("0")
            
            if width > 10:
                row_data.append("...")
            
            text_widget.insert(tk.END, "\t".join(row_data) + "\n")
        
        if height > 10:
            text_widget.insert(tk.END, "...\n")
    
    def _displayImageData(self, text_widget, flowData, headers):
        """画像データを表示"""
        import numpy as np
        from PIL import Image, ImageTk
        
        text_widget.insert(tk.END, "\n画像データ:\n")
        
        mode = headers.get('mode', 'unknown')
        planes = headers.get('planes', [])
        width, height, planeCount = flowData.getDimensions()
        
        text_widget.insert(tk.END, f"Mode: {mode}\n")
        text_widget.insert(tk.END, f"Planes: {', '.join(planes)}\n")
        text_widget.insert(tk.END, f"Size: {width} x {height}\n\n")
        
        try:
            # 画像データを再構成
            if mode == 'RGB' and planeCount >= 3:
                # RGB画像を作成
                imgArray = np.zeros((height, width, 3), dtype=np.uint8)
                
                for planeIdx in range(3):
                    for blockY in range(0, height, 256):
                        for blockX in range(0, width, 256):
                            block = flowData.getBlock(planeIdx, blockX, blockY)
                            if block and hasattr(block, 'data') and block.data is not None:
                                try:
                                    blockHeight = min(256, height - blockY)
                                    blockWidth = min(256, width - blockX)
                                    endY = blockY + blockHeight
                                    endX = blockX + blockWidth
                                    
                                    imgArray[blockY:endY, blockX:endX, planeIdx] = np.clip(
                                        block.data[:blockHeight, :blockWidth], 0, 255
                                    ).astype(np.uint8)
                                except (IndexError, TypeError, ValueError):
                                    pass
                
                img = Image.fromarray(imgArray, 'RGB')
            elif mode == 'L' and planeCount >= 1:
                # グレースケール画像を作成
                imgArray = np.zeros((height, width), dtype=np.uint8)
                
                for blockY in range(0, height, 256):
                    for blockX in range(0, width, 256):
                        block = flowData.getBlock(0, blockX, blockY)
                        if block and hasattr(block, 'data') and block.data is not None:
                            try:
                                blockHeight = min(256, height - blockY)
                                blockWidth = min(256, width - blockX)
                                endY = blockY + blockHeight
                                endX = blockX + blockWidth
                                
                                imgArray[blockY:endY, blockX:endX] = np.clip(
                                    block.data[:blockHeight, :blockWidth], 0, 255
                                ).astype(np.uint8)
                            except (IndexError, TypeError, ValueError):
                                pass
                
                img = Image.fromarray(imgArray, 'L')
            else:
                text_widget.insert(tk.END, f"サポートされていないモード: {mode}\n")
                return
            
            # 表示サイズを調整 (最大400x300)
            display_width, display_height = img.size
            if display_width > 400 or display_height > 300:
                ratio = min(400/display_width, 300/display_height)
                display_width = int(display_width * ratio)
                display_height = int(display_height * ratio)
                img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
            
            # Tkinterで表示するためにPhotoImageに変換
            photo = ImageTk.PhotoImage(img)
            
            # 画像をテキストウィジェットに挿入
            text_widget.image_create(tk.END, image=photo)
            text_widget.insert(tk.END, "\n")
            
            # 参照を保持してガベージコレクションを防ぐ
            if not hasattr(text_widget, 'images'):
                text_widget.images = []
            text_widget.images.append(photo)
            
        except Exception as e:
            text_widget.insert(tk.END, f"画像表示エラー: {str(e)}\n")
    
    def _displayGenericData(self, text_widget, flowData):
        """一般的なデータを表示"""
        text_widget.insert(tk.END, "\nデータ:\n")
        width, height, planeCount = flowData.getDimensions()
        
        for planeIdx in range(min(planeCount, 3)):
            if planeCount > 1:
                text_widget.insert(tk.END, f"\n[プレーン {planeIdx}]\n")
            
            for y in range(min(height, 5)):
                row_data = []
                for x in range(min(width, 10)):
                    block = flowData.getBlock(planeIdx, x, y)
                    if block and hasattr(block, 'data') and block.data is not None:
                        try:
                            value = block.data[y][x] if len(block.data) > y and len(block.data[y]) > x else 0
                            row_data.append(f"{value:.3f}")
                        except (IndexError, TypeError):
                            row_data.append("0.000")
                    else:
                        row_data.append("0.000")
                
                text_widget.insert(tk.END, "\t".join(row_data) + "\n")
    
    def _updateOpenResultWindows(self):
        """開いている結果ウィンドウを更新"""
        for node in self.nodes:
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

if __name__ == '__main__':
    root = tk.Tk()
    app = FlowEditor(root)
    root.mainloop()