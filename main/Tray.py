import tkinter as tk

from nodes import NodeFactory

class Tray:
    def __init__(self, canvas, editor, x=30, y=30, width=200, height=150, title="トレイ", **kwargs):
        self.canvas = canvas
        self.editor = editor
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title

        self.isMoveing  = False
        self.isResizing = False
        self.startX = 0
        self.startY = 0
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
        canvas.tag_bind(self.rect , '<Button-1>', self.onPress)
        canvas.tag_bind(self.label, '<Button-1>', self.onPress)
        canvas.tag_bind(self.rect , '<B1-Motion>', self.onDrag)
        canvas.tag_bind(self.label, '<B1-Motion>', self.onDrag)
        canvas.tag_bind(self.rect , '<ButtonRelease-1>', self.onRelease)
        canvas.tag_bind(self.label, '<ButtonRelease-1>', self.onRelease)
        canvas.tag_bind(self.rect , '<Button-3>', self.onRightPress)
        canvas.tag_bind(self.label, '<Button-3>', self.onRightPress)

        # 右クリックメニュー
        self.contextMenu = tk.Menu(self.canvas, tearoff=0)
        for nodeType, label in NodeFactory.getMenuItems():
            if '---' in nodeType:
                self.contextMenu.add_separator()
            else:
                self.contextMenu.add_command(label=label, command=lambda nt=nodeType: self.editor.addNodeAtPosition(nt))
        
        self.contextMenu.add_separator()
        self.contextMenu.add_command(label="編集", command=self.editTray)
        self.contextMenu.add_command(label="最背面", command=self.lower)
        self.contextMenu.add_command(label="削除", command=self.deleteTray)

    def onPress(self, event):
        self.startX = event.x
        self.startY = event.y
        self.isDragging = False

    def onDrag(self, event):
        dx = event.x - self.startX
        dy = event.y - self.startY
        
        if not self.isDragging:
            # ドラッグ開始の判定
            dx = abs(event.x - self.startX)
            dy = abs(event.y - self.startY)
            if dx > 5 or dy > 5:
                self.isDragging = True
                
                # 開始位置
                canvasX = self.canvas.canvasx(self.startX)
                canvasY = self.canvas.canvasy(self.startY)

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
                    self.isMoveing = True
                    self.dragNodes = self.getVisuallyContainedNodes()  # 視覚的に上にあるノードのみを固定
                    self.dragTrays = self.getVisuallyContainedTrays()  # 視覚的に上にあるトレイを固定
                    # ドラッグ開始時にハイライトを消す
                    self.editor.clearSelectedHighlight()
                    self.editor.clearReprocessingHighlights()
                    # ドラッグ開始時にトレイと含まれるアイテムを前面に
                    groupItems = [self.rect, self.label]
                    for node in self.dragNodes:
                        groupItems.extend([node.view.rect, node.view.label])
                    for tray in self.dragTrays:
                        groupItems.extend([tray.rect, tray.label])
                    self.editor._placeItemBeforeConnections(*groupItems)
                    # ドラッグ開始時に外観を更新
                    self.editor.updateAllTrayAppearance()
        
        if self.isDragging:
            if self.isMoveing:
                # トレイを移動
                self.x += dx
                self.y += dy
                self.canvas.move(self.rect, dx, dy)
                self.canvas.move(self.label, dx, dy)

                # ドラッグ開始時に固定したノードを一緒に移動
                for node in self.dragNodes:
                    node.view.x += dx
                    node.view.y += dy
                    self.canvas.move(node.view.rect, dx, dy)
                    self.canvas.move(node.view.label, dx, dy)

                # ドラッグ開始時に固定したトレイを一緒に移動
                for tray in self.dragTrays:
                    tray.x += dx
                    tray.y += dy
                    self.canvas.move(tray.rect, dx, dy)
                    self.canvas.move(tray.label, dx, dy)

                # ドラッグ中はグループ全体を順序を維持して前面に保持
                groupItems = [self.rect, self.label]
                for node in self.dragNodes:
                    groupItems.extend([node.view.rect, node.view.label])
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

            self.startX = event.x
            self.startY = event.y
            
            # canvasの自動拡大/縮小
            self.editor.adjustCanvasSize()

    def onRelease(self, event):
        self.isDragging = False
        self.isMoveing  = False
        self.isResizing = False
        self.dragNodes = []  # ドラッグノードリストをクリア
        self.dragTrays = []  # ドラッグトレイリストをクリア
        # 全トレイの外観を更新
        self.editor.updateAllTrayAppearance()

        self.editor.unselectNode()

    def onRightPress(self, event):
        self.editor.rightClickX = event.x
        self.editor.rightClickY = event.y
        self.contextMenu.post(event.x_root, event.y_root)

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

    def updatePosition(self):
        """位置を更新"""
        self.canvas.coords(self.rect,
            self.x - self.width//2, self.y - self.height//2,
            self.x + self.width//2, self.y + self.height//2)
        self.canvas.coords(self.label,
            self.x - self.width//2 + 10, self.y - self.height//2 + 10)

    def updatePositionAndAppearance(self):
        """位置と外観を更新"""
        self.updatePosition()
        self.updateDepthAppearance()
        self.canvas.itemconfig(self.label, text=self.title)

    def getVisuallyContainedNodes(self):
        """視覚的にトレイの上にあるノードを取得"""
        contained = []
        for node in self.editor.nodes:
            if (self.x - self.width//2 <= node.view.x <= self.x + self.width//2 and
                self.y - self.height//2 <= node.view.y <= self.y + self.height//2):
                # ノードがトレイより前面にあるかチェック
                nodeItems = [node.view.rect, node.view.label]
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

    def lift(self):
        """トレイを前面に移動"""
        self.canvas.tag_raise(self.rect)
        self.canvas.tag_raise(self.label)

    def lower(self):
        """トレイを背面に移動"""
        self.canvas.tag_lower(self.rect)
        self.canvas.tag_lower(self.label)

    def serialize(self):
        return {
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'title': self.title,
        }

    def deserialize(self, data):
        self.x = data['x']
        self.y = data['y']
        self.width = data['width']
        self.height = data['height']
        self.title = data['title']
