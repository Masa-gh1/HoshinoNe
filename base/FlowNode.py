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
from utils.ThreadPool import ParallelExecutor

# 定数
_MAJOR_TYPE_FUNC  = 'func'             # 関数系
_MAJOR_TYPE_U_OP  = 'unary operation'  # 単項演算系
_MAJOR_TYPE_B_OP  = 'binary operation' # 演算系
_MAJOR_TYPE_AGG   = 'aggregate'        # 集計系
_MAJOR_TYPE_IO    = 'in/out'           # 入出系
_MAJOR_TYPE_CONST = 'constant'         # 定数系
_MAJOR_TYPE_UTIL  = 'utility'          # ユーティリティ

_IO_TYPE_0N = '0:N' # ファイル読み込みなど
_IO_TYPE_N0 = 'N:0' # ファイル書き込みなど(実行レポートなどの出力が在るノードはこちら)
_IO_TYPE_NN = 'N:N' # N入力:N出力
_IO_TYPE_N1 = 'N:1' # N入力:1出力

_OUT_CAT_PRI = 'primary'   # 主データを出力
_OUT_CAT_AUX = 'auxiliary' # 補正値を出力
_OUT_CAT_PAS = 'pass'      # 入力カテゴリを変えない
_OUT_CAT_ETC = 'etc'       # その他(実行レポートなどの出力が在るノードはこちら)
_OUT_CAT_NON = 'none'      # なし

class FlowNode(AbstractBaseClass):
    # ノードタイプ(サブクラスでオーバーライド)
    majorType = 'base'
    minorType = 'base'
    # ノード名
    name      = 'FlowNode'
    # 入出力タイプ(サブクラスでオーバーライド)
    ioType    = '0:0'
    outputCat = _OUT_CAT_PRI

    def __init__(self, canvas, editor, x, y, **kwargs):
        self.view = FlowNodeView( self.majorType, self.ioType, self.outputCat, self.name, canvas, editor, x, y, **kwargs)

        self.outputNodes = [] # 接続先ノードの一覧
        self.inputNodes  = [] # 入力元ノードの一覧
        self.flowDatas   = [] # 処理結果データ

        self._lastInputHash  = None
        self._lastConfigHash = None
        
        self.fileTypes = [("CSV files", "*.csv")]
        self.defaultOutputExtension = ".csv"

    def cleanUp(self):
        # 接続の初期化
        self.outputNodes = [] # 接続先ノードの一覧
        self.inputNodes  = []  # 入力元ノードの一覧

        # データの初期化
        self.flowDatas   = []   # 処理結果データ
        
        self.view.cleanUp()

    def getText(self):
        """ノードのテキストを取得（サブクラスでオーバーライド）"""
        return self.name
    
    def getOutputCategory(self):
        """ノードへの入力を考慮した出力カテゴリを取得"""
        return self._getOutputCategory()
    
    def _getOutputCategory(self, path=[]):
        catList = [_OUT_CAT_PRI, _OUT_CAT_AUX, _OUT_CAT_ETC, _OUT_CAT_NON]
        if _OUT_CAT_PAS in self.outputCat:
            path = path.copy()
            path.append(self) # 循環参照を除く
            inCats = [catList.index(x._getOutputCategory(path)) for x in self.inputNodes if x not in path]
            if inCats:
                return catList[min(inCats)]
            else:
                return _OUT_CAT_NON
        else:
            return self.outputCat
    
    def getOutputCount(self):
        """ノードへの入力を考慮した出力数を取得"""
        if   _IO_TYPE_N0 == self.ioType:
            return 0
        elif _IO_TYPE_N1 == self.ioType:
            return 1
        elif(  _IO_TYPE_0N == self.ioType
            or _IO_TYPE_NN == self.ioType
            ):
            return sum([x.getOutputCount() for x in self.inputNodes if _OUT_CAT_PRI == x.getOutputCategory()])
        else:
            return 0
    
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
        # 実行時設定ハッシュの更新
        self._lastInputHash = self.getInputHashe()
        self._lastConfigHash = self.getConfigHash()
        self.view.editor.root.after(0,self.view.updateResult)
    
    def reportProgress(self, context, message, current=None, total=None):
        """処理経過を報告"""
        if context and 'progress_callback' in context:
            context['progress_callback'](message, current, total)

    def preview(self):
        """プレビュー専用処理（ノード個別実行）"""
        self.view.editor.executeFlow(self)
    
    def needsReprocessing(self):
        """再処理が必要かどうかを判定"""
        # ハッシュを計算
        inputHash = self.getInputHashe()
        configHash = self.getConfigHash()
        
        # 初回実行または変更ありの場合は再処理
        return (self._lastInputHash != inputHash
                or self._lastConfigHash != configHash
               )
    
    def getInputHashe(self):
        inputHashes = []
        for node in self.inputNodes:
            inputHashes.append(str(id(node)))
            for flowData in node.flowDatas:
                inputHashes.append(str(id(flowData)))
        return hashlib.md5(':'.join(inputHashes).encode()).hexdigest()
    
    def getConfigHash(self):
        """ノード固有の設定ハッシュを取得（サブクラスでオーバーライド）"""
        return hashlib.md5(str(self.minorType).encode()).hexdigest()
    
    def serialize(self):
        """ノードをシリアライズ"""
        serial = {
            "type": self.minorType,
            "text": self.name,
            "x"   : self.view.x,
            "y"   : self.view.y,
        }
        self.store(serial)
        serial["connections"] = [id(node) for node in self.outputNodes]
        return serial
    
    def deserialize(self, serial):
        """ノードをデシリアライズ"""
        self.view.x = serial["x"]
        self.view.y = serial["y"]
        self.restore(serial)
        self.view.onNodeConfigChanged(self)

    def store(self, nodeData):
        """ノード固有の設定を nodeData に保存（サブクラスでオーバーライド）
        
        Args:
            nodeData: 保存先
        """
        pass
    
    def restore(self, nodeData):
        """ノード固有の設定を nodeData から復元（サブクラスでオーバーライド）
        
        Args:
            nodeData: 復元元
        """
        pass
    
class FlowNodeView():
    def __init__(self, majorType, ioType, outputCat, text, canvas, editor, x, y, **kwargs):
        self.majorType = majorType
        self.ioType    = ioType
        self.outputCat = outputCat
        self.text      = text

        self.canvas  = canvas
        self.editor  = editor
        self._binds  = []
        self._window = {}
        self.x, self.y = x, y
        
        # 形状の頂点座標を保持 (中心座標からの相対座標)
        self.shapePoints = self._getShapePoints()

        self.isDoubleClick = False
        self.dragging = False
        self.startX = 0
        self.startY = 0

        # 描画要素を作成
        points = []
        for dx, dy in self.shapePoints:
            points.extend([self.x + dx, self.y + dy])
        self.rect = self.canvas.create_polygon(*points, fill=self._getColor(), outline='black')
        self.label = self.canvas.create_text(self.x, self.y, text=self.text, font=('Arial', 8))

        # イベントバインディング
        self.canvasBind('<Button-1>'       , self.onClick      )
        self.canvasBind('<B1-Motion>'      , self.onDrag       )
        self.canvasBind('<ButtonRelease-1>', self.onRelease    )
        self.canvasBind('<Button-3>'       , self.onRightClick )
        self.canvasBind('<Double-Button-1>', self.onDoubleClick)
    
    def cleanUp(self):
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
    
    def _getShapePoints(self):
        """形状の頂点座標を返す (中心からの相対座標)"""
        if   _MAJOR_TYPE_U_OP == self.majorType and _IO_TYPE_NN == self.ioType:
            # 菱形
            return [(  0, -25), (25,   0), ( 0, 25), (-25,  0)]
        elif _MAJOR_TYPE_B_OP == self.majorType and _IO_TYPE_NN == self.ioType:
            # 正方形
            return [(-20, -20), (20, -20), (20, 20), (-20, 20)]
        elif _MAJOR_TYPE_AGG == self.majorType and _IO_TYPE_N1 == self.ioType:
            # 六角形
            return [(-30, -20), (-40, 0), (-30, 20), (30, 20), (40, 0), (30, -20)]
        elif _MAJOR_TYPE_UTIL == self.majorType:
            # 小さい長方形
            return [(-25, -15), (25, -15), (25, 15), (-25, 15)]
        elif _IO_TYPE_0N == self.ioType:
            # 左が尖った五角形
            return [(-40, -20), (-50, 0), (-40, 20), (50, 20), (50, -20)]
        elif _IO_TYPE_N0 == self.ioType:
            # 右が尖った五角形
            return [(-50, -20), (-50, 20), (40, 20), (50, 0), (40, -20)]
        elif _IO_TYPE_NN == self.ioType:
            # 長方形
            return [(-50, -20), (50, -20), (50, 20), (-50, 20)]
        elif _IO_TYPE_N1 == self.ioType:
            # 長い六角形
            return [(-40, -20), (-50, 0), (-40, 20), (40, 20), (50, 0), (40, -20)]
        else:  # default
            # 長方形
            return [(-50, -20), (50, -20), (50, 20), (-50, 20)]
    
    def _getColor(self):
        colorMap = {
            _MAJOR_TYPE_FUNC : 'plum'       , # 関数系 magenta
            _MAJOR_TYPE_U_OP : 'lightgrey'  , # 単項演算系 grey
            _MAJOR_TYPE_B_OP : 'pink'       , # 二項演算系 red
            _MAJOR_TYPE_AGG  : 'pink'       , # 集計系 red
            _MAJOR_TYPE_IO   : 'lightyellow', # 入出系 yellow
                             # 'lightgreen'   # 予約 green
            _MAJOR_TYPE_CONST: 'lightcyan'  , # 定数系 blue
                             # 'lightblue'    # 予約 cyan
            _MAJOR_TYPE_UTIL : 'lightgrey'  , # ユーティリティ grey
        }
        return colorMap.get(self.majorType, 'lightgreen')
    
    def getShapeBounds(self):
        """形状の境界を返す (ハイライト用)"""
        xs = [self.x + dx for dx, dy in self.shapePoints]
        ys = [self.y + dy for dx, dy in self.shapePoints]
        margin = 5
        return (min(xs)-margin, min(ys)-margin, max(xs)+margin, max(ys)+margin)
    
    def getConnectionPoint(self, dx, dy):
        """接続点を返す (dx, dy: 接続先への方向ベクトル)"""
        if dx == 0 and dy == 0:
            return (self.x, self.y)
        
        import math
        
        # 正規化
        length = math.sqrt(dx*dx + dy*dy)
        ndx, ndy = dx/length, dy/length
        
        # 各辺との交点を計算
        bestDist = 0
        bestPoint = (self.x, self.y)
        
        n = len(self.shapePoints)
        for i in range(n):
            p1x, p1y = self.shapePoints[i]
            p2x, p2y = self.shapePoints[(i+1) % n]
            
            # 線分 (0,0)-(ndx*1000, ndy*1000) と (p1x,p1y)-(p2x,p2y) の交点
            point = self._lineIntersection(0, 0, ndx*1000, ndy*1000, p1x, p1y, p2x, p2y)
            if point:
                px, py = point
                dist = px*ndx + py*ndy  # 方向ベクトル方向の距離
                if dist > bestDist:
                    bestDist = dist
                    bestPoint = (self.x + px, self.y + py)
        
        return bestPoint
    
    def _lineIntersection(self, x1, y1, x2, y2, x3, y3, x4, y4):
        """2線分の交点を計算"""
        denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(denom) < 1e-10:
            return None
        
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        u = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / denom
        
        if 0 <= t <= 1 and 0 <= u <= 1:
            return (x1 + t*(x2-x1), y1 + t*(y2-y1))
        return None
    
    def canvasBind(self, sequence, callback):
        fid1 = self.canvas.tag_bind( self.rect , sequence, callback)
        fid2 = self.canvas.tag_bind( self.label, sequence, callback)
        self._binds.append((sequence,fid1))
        self._binds.append((sequence,fid2))
    
    def updatePosition(self):
        points = []
        for dx, dy in self.shapePoints:
            points.extend([self.x + dx, self.y + dy])
        self.canvas.coords(self.rect, *points)
        self.canvas.coords(self.label, self.x, self.y)

    def updatePositionAndAppearance(self,node):
        """位置と外観を更新"""
        self.updatePosition()
        self.editor.onNodeConfigChanged(node)

    def onNodeConfigChanged(self, node):
        self.text = node.getText()
        newHash = node.getConfigHash()
        if newHash != node._lastConfigHash:
            self.editor.onNodeConfigChanged(node)

    def onClick(self, event):
        self.startX = event.x
        self.startY = event.y
        self.dragging = False
    
    def onDrag(self, event):
        if self.isDoubleClick:
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
            
            # canvasの自動拡大/縮小
            self.editor.adjustCanvasSize()
            
            self.editor.updateConnections()
    
    def onRelease(self, event):
        if self.isDoubleClick:
            self.isDoubleClick = False
            return
        
        if not self.dragging:
            # クリックとして処理
            self.editor.onNodeClick(self)
        self.dragging = False
    
    def onDoubleClick(self, event):
        self.isDoubleClick = True
        self.editor.onNodeDoubleClick(self)
    
    def onRightClick(self, event):
        self.editor.onNodeRightClick(self, event)
    
    def onEdit(self, node):
        """編集メニューから呼び出される編集処理"""
        if not hasattr(node, 'createSettingWindow'):
            pass
        elif not 'settings_dialog' in self._window:
            self._window["settings_dialog"] = node.createSettingWindow()
        elif not self._window["settings_dialog"].winfo_exists():
            self._window["settings_dialog"].destroy()
            self._window["settings_dialog"] = node.createSettingWindow()
        else:
            self._window["settings_dialog"].lift()
    
    def onResult(self, node):
        """ノードの処理結果を表示"""
        if not 'result_window' in self._window:
            self._window["result_window"] = ResultWindow(self.editor.root, node)
        elif not self._window["result_window"].winfo_exists():
            self._window["result_window"].destroy()
            self._window["result_window"] = ResultWindow(self.editor.root, node)
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
            if window.winfo_exists():
                window.lift()
                window.focus_force()

    def lift(self):
        """ノードを最前面に表示"""
        self.canvas.tag_raise(self.rect)
        self.canvas.tag_raise(self.label)
