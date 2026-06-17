'''
結果ウィンドウクラス

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from fractions import Fraction
import json
import io
import tkinter as tk
from tkinter import ttk

from config import BLOCK_SIZE
from base.LazyFlowData import LazyHeadersDict
from utils import string_helper as sh
from utils import numpy_helpers as nh
from utils.interval_helper import createHalfOpenEnd
from utils.ThreadPool import CoalescingExecutor
from utils.Debug import Debug

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')  # GUIバックエンドを使わない
    import matplotlib.pyplot as plt
    PYPLOT_AVAILABLE = True
except ImportError:
    PYPLOT_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ResultWindow(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
    
        self.title(f"{self.node.name} - 処理結果")
        self.geometry("600x600")
        
        # 制御フレーム
        control_frame = tk.Frame(self)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        self._control_frame = control_frame
        
        # データ選択フレーム（常に表示）
        data_select_frame = tk.Frame(control_frame)
        data_select_frame.pack(fill=tk.X)
        self._data_select_frame = data_select_frame
        
        tk.Label(data_select_frame, text="表示データ:").pack(side=tk.LEFT)
        self._selected_data_var = tk.StringVar()
        self._data_combo = tk.ttk.Combobox(data_select_frame, textvariable=self._selected_data_var, state="readonly", width=180)
        self._data_combo.pack(side=tk.LEFT, padx=(5,0))
        self._data_combo.bind('<<ComboboxSelected>>', lambda e: self.updateResult())
        self._data_combo.bind('<Key>', self._onComboKeyPress)
        
        # ヒストグラム軸制御（画像データのみ）
        axis_frame = tk.Frame(control_frame)
        axis_frame._is_image_control = True
        
        tk.Label(axis_frame, text="ヒストグラム軸:").pack(side=tk.LEFT)
        
        # X軸制御
        self._x_scale_var = tk.StringVar(value="log")
        tk.Label(axis_frame, text="X軸:").pack(side=tk.LEFT, padx=(10,0))
        tk.Radiobutton(axis_frame, text="Log", variable=self._x_scale_var, value="log", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(axis_frame, text="Linear", variable=self._x_scale_var, value="linear", command=self.updateResult).pack(side=tk.LEFT)
        
        # Y軸制御
        self._y_scale_var = tk.StringVar(value="log")
        tk.Label(axis_frame, text="Y軸:").pack(side=tk.LEFT, padx=(10,0))
        tk.Radiobutton(axis_frame, text="Log", variable=self._y_scale_var, value="log", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(axis_frame, text="Linear", variable=self._y_scale_var, value="linear", command=self.updateResult).pack(side=tk.LEFT)
        
        # 画像レベル制御（画像データのみ）
        level_frame = tk.Frame(control_frame)
        level_frame._is_image_control = True
        
        tk.Label(level_frame, text="画像表示レベル:").pack(side=tk.LEFT)
        
        self._display_levels_var = tk.StringVar(value="display")
        tk.Radiobutton(level_frame, text="display", variable=self._display_levels_var, value="display", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="adaptive", variable=self._display_levels_var, value="adaptive", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="all", variable=self._display_levels_var, value="all", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="isoline", variable=self._display_levels_var, value="isoline", command=self.updateResult).pack(side=tk.LEFT)
        
        # 画像グリッド制御（画像データのみ）
        grid_frame = tk.Frame(control_frame)
        grid_frame._is_image_control = True
        
        tk.Label(grid_frame, text="四隅拡大:").pack(side=tk.LEFT)
        
        self._display_corner_var = tk.StringVar(value="full")
        tk.Radiobutton(grid_frame, text="full", variable=self._display_corner_var, value="full", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(grid_frame, text="3x3 grid", variable=self._display_corner_var, value="3x3 grid", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(grid_frame, text="5x5 grid", variable=self._display_corner_var, value="5x5 grid", command=self.updateResult).pack(side=tk.LEFT)
        
        # 画像ズーム制御（画像データのみ）
        zoom_frame = tk.Frame(control_frame)
        zoom_frame._is_image_control = True
        
        tk.Label(zoom_frame, text="画像ズーム:").pack(side=tk.LEFT)
        
        self._display_zoom_var = tk.StringVar(value="fit")
        tk.Radiobutton(zoom_frame, text="fit", variable=self._display_zoom_var, value="fit", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(zoom_frame, text="x1", variable=self._display_zoom_var, value="x1", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(zoom_frame, text="x2", variable=self._display_zoom_var, value="x2", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(zoom_frame, text="x3", variable=self._display_zoom_var, value="x3", command=self.updateResult).pack(side=tk.LEFT)
        
        # スクロールバー付きテキストエリア
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(frame, wrap=tk.WORD)
        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # テキストウィジェット参照を保存
        self._result_text_widget = text_widget
        
        # ウィンドウが閉じられたときのクリーンアップ
        def on_close():
            self.destroy()
        
        self.protocol("WM_DELETE_WINDOW", on_close)
        
        # ウィンドウの幅変更時のみ画像を再描画（300ms毎）
        self._resize_timer = None
        self._last_width = self.winfo_width()
        
        # データ選択コンボボックスを更新
        self._updateDataCombo()
        
        # 初回表示（別スレッドで実行）
        CoalescingExecutor.submit( self, self._updateResultWindowAsync)
        
        # コントロールフレームの表示状態を更新
        self._updateControlVisibility()
        
        def on_configure(event):
            width = self.winfo_width()
            if self._resize_timer:
                pass
            elif event.widget != self:
                pass
            elif self._last_width < 10 or width < 10:
                self._last_width = width
            elif self._last_width != width:
                self._last_width = width
                def update():
                    self._resize_timer = None
                    self.updateResult()
                self._resize_timer = self.node.view.editor.root.after(300, update)
        
        self.bind('<Configure>', on_configure)
    
    def updateResult(self):
        """結果ウィンドウの内容を更新（別スレッドで実行）"""
        CoalescingExecutor.submit(self, self._updateResultWindowAsync)
    
    def _updateResultWindowAsync(self):
        """結果ウィンドウの内容を非同期で更新"""
        if not hasattr(self, '_result_text_widget'):
            return
        
        # タイトルを更新してデータ読み込み中を表示
        def update_title_loading():
            self.title(f"{self.node.name} - データ読み込み中...")
        
        self.node.view.editor.root.after(0, update_title_loading)
        
        # 選択されたデータのみ処理
        content_parts = []
        selected_data = self._getSelectedFlowData()
        if selected_data:
            result = self._generateFlowDataContent(selected_data)
            if isinstance(result, list):
                content_parts.extend(result)
            else:
                content_parts.append(result)
        
        # 結果をメインスレッドで表示
        def display_result():
            self.title(f"{self.node.name} - 処理結果")
            
            if hasattr(self, '_result_text_widget'):
                text_widget = self._result_text_widget
                
                # スクロール位置を保存（比率）
                scroll_pos = text_widget.yview()[0]
                
                text_widget.config(state=tk.NORMAL)
                text_widget.delete(1.0, tk.END)
                for part in content_parts:
                    if isinstance(part, str):
                        text_widget.insert(tk.END, part)
                    else:
                        # 画像の場合
                        text_widget.image_create(tk.END, image=part)
                        text_widget.insert(tk.END, "\n")
                        if not hasattr(text_widget, 'images'):
                            text_widget.images = []
                        text_widget.images.append(part)
                text_widget.config(state=tk.DISABLED)
                
                # スクロール位置を復元
                text_widget.yview_moveto(scroll_pos)
        
        self.node.view.editor.root.after(0, display_result)
        
        # コントロールフレームの表示状態を更新
        def safe_update():
            try:
                if self.winfo_exists():
                    self._updateControlVisibility()
                    self._updateDataCombo()
            except tk.TclError:
                pass
        
        self.node.view.editor.root.after(0, safe_update)
    
    def _generateFlowDataContent(self, flowData):
        """フローデータの内容を文字列として生成（非同期処理用）"""
        headers = flowData.headers
        
        dataType = headers.get('type', 'unknown')
        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        
        content = []
        text = f"Type: {dataType}\n"
        text += f"PlaneCount: {planeCount}\n"
        text += f"Dimensions: {width} x {height}\n"
        content.append(text)
        
        if   dataType == 'image'     : result = self._generateImageContent(flowData)
        elif dataType == 'polynomial': result = self._generatePolynomialContent(flowData)
        elif dataType == 'table'     : result = self._generateTableContent(flowData)
        else:                          result = self._generateGenericContent(flowData)
        
        if isinstance(result, list):
            content.extend(result)
        else:
            content.append(result)
        
        if Debug.LEVEL_NONE < Debug.LEVEL:
            class JSONEncoder(json.JSONEncoder):
                def default( self, obj):
                    if isinstance( obj, np.floating):
                        return float(obj)
                    elif isinstance( obj, LazyHeadersDict):
                        return dict(obj)
                    elif isinstance( obj, Fraction):
                        return str(obj)
                    else:
                        return json.JSONEncoder.default(self, obj)
            
            jsonStr = json.dumps( headers, ensure_ascii=False, indent=2, cls=JSONEncoder)
            content.append("\n\n")
            content.append("headers:\n" + jsonStr + "\n")
            
        return content
    
    def _generateGenericContent(self, flowData):
        """一般的なデータの内容を生成"""
        headers = flowData.headers
        content = "\n"
        
        planes = headers.get('planes', [])
        
        width, height = flowData.getDimensions()
        displayRows = min(height, 100)  # 最初の100行のみ
        displayCols = min(width ,  10)  # 最初の10列のみ
        
        for planeIndex, planeName in enumerate(planes):
            content += f"\n[plane: {planeName}]\n"
            
            block = None
            blockX = 0
            blockY = 0
            blockW = 0
            blockH = 0
            cols = []
            for x in range(displayCols):
                cells = []
                for y in range(displayRows):
                    if(  x < blockX or blockX + blockW <= x
                    or y < blockY or blockY + blockH <= y
                    ):
                        block = flowData.getBlock(planeIndex, x//BLOCK_SIZE*BLOCK_SIZE, y//BLOCK_SIZE*BLOCK_SIZE)
                        if block and not block.data is None:
                            blockX = x//BLOCK_SIZE*BLOCK_SIZE
                            blockY = y//BLOCK_SIZE*BLOCK_SIZE
                            blockH, blockW = block.data.shape
                        else:
                            blockX = 0
                            blockY = 0
                            blockW = 0
                            blockH = 0
                    value = block.data[y-blockY][x-blockX]
                    cells.append(value)
                cols.append(sh.dispL(cells))
            
            # ヘッダー行
            if width:
                for x in  range(width):
                    content += "\t"
                    content += f"x:{x}".ljust(max([len(t) for t in cols[x]]))
                content += "\n"
            
            # データ行
            for y in range(displayRows):
                row = [f"y:{y}"]
                for x in range(displayCols):
                    row.append(cols[x][y])
                if width > displayCols:
                    row.append("...")
                content += "\t".join(row) + "\n"
            if height > displayRows:
                content += "...\n"
        
        return content
        
    def _generateTableContent(self, flowData):
        """マトリックスデータの内容を生成"""
        headers = flowData.headers
        content = "\n"
        
        planes  = headers.get('planes', [])
        lines   = headers.get('lines', [])
        columns = headers.get('columns', [])
        
        width, height = flowData.getDimensions()
        displayRows = min(height, 1000)  # 最初の1000行のみ表示
        displayCols = min(width ,   10)  # 最初の10列のみ表示
        
        for planeIndex, planeName in enumerate(planes):
            content += f"\n[plane: {planeName}]\n"
        
            block = None
            blockX = 0
            blockY = 0
            blockW = 0
            blockH = 0
            cols = []
            for x in range(displayCols):
                cells = []
                for y in range(displayRows):
                    if(  x < blockX or blockX + blockW <= x
                      or y < blockY or blockY + blockH <= y
                      ):
                        block = flowData.getBlock(planeIndex, x//BLOCK_SIZE*BLOCK_SIZE, y//BLOCK_SIZE*BLOCK_SIZE)
                        if block and not block.data is None:
                            blockX = x//BLOCK_SIZE*BLOCK_SIZE
                            blockY = y//BLOCK_SIZE*BLOCK_SIZE
                            blockH, blockW = block.data.shape
                        else:
                            blockX = 0
                            blockY = 0
                            blockW = 0
                            blockH = 0
                    value = block.data[y-blockY][x-blockX]
                    cells.append(value)
                cols.append(sh.dispL(cells))
            
            # ヘッダー行
            if columns:
                length = max([len(label) for label in lines])
                content += "\t"*(length//8)
                for x, column in enumerate(columns):
                    content += "\t"
                    content += column.ljust(max([len(t) for t in cols[x]]))
                content += "\n"
            
            # データ行
            for y in range(displayRows):
                row = [lines[y] if y < len(lines) else f"row_{y}"]
                for x in range(displayCols):
                    row.append(cols[x][y])
                if width > displayCols:
                    row.append("...")
                content += "\t".join(row) + "\n"
            if height > displayRows:
                content += "...\n"
            
        return content
    
    def _generatePolynomialContent(self, flowData):
        """Polynomialデータの内容を生成"""
        headers = flowData.headers
        content = "\n"
        
        planes  = headers.get('planes', [])
        lines   = headers.get('lines', [])
        columns = headers.get('columns', [])
        
        width, height = flowData.getDimensions()
        
        for planeIndex, planeName in enumerate(planes):
            content += f"\n[plane: {planeName}]\n"
            
            median = flowData.getQuantile(0.5)
            
            block = None
            blockX = 0
            blockY = 0
            blockW = 0
            blockH = 0
            cols = []
            for x in range(width):
                cells = []
                for y in range(height):
                    if(  x < blockX or blockX + blockW <= x
                    or y < blockY or blockY + blockH <= y
                    ):
                        block = flowData.getBlock(planeIndex, x//BLOCK_SIZE*BLOCK_SIZE, y//BLOCK_SIZE*BLOCK_SIZE)
                        if block and not block.data is None:
                            blockX = x//BLOCK_SIZE*BLOCK_SIZE
                            blockY = y//BLOCK_SIZE*BLOCK_SIZE
                            blockH, blockW = block.data.shape
                        else:
                            blockX = 0
                            blockY = 0
                            blockW = 0
                            blockH = 0
                    value = block.data[y-blockY][x-blockX]
                    cells.append(value)
                cols.append(sh.dispL(cells, representative=median))
            
            # ヘッダー行
            if columns:
                length = max([len(label) for label in lines])
                content += "\t"*(length//8)
                for x, column in enumerate(columns):
                    content += "\t"
                    content += column.ljust(max([len(t) for t in cols[x]]))
                content += "\n"
            
            # データ行
            for y in range(height):
                row = [lines[y] if y < len(lines) else f"row_{y}"]
                for x in range(width):
                    row.append(cols[x][y])
                if width > width:
                    row.append("...")
                content += "\t".join(row) + "\n"
            if height > height:
                content += "...\n"
        
        return content
    
    def _generateImageContent(self, flowData):
        """画像データの内容を生成"""
        headers = flowData.headers
        
        mode            = flowData.getMode()
        planes          = headers.get('planes', [])
        width, height   = flowData.getDimensions()
        planeCount      = flowData.getPlaneCount()
        displayLevels   = headers['display_levels']
        displayLevelMin = displayLevels["min"]
        displayLevelEnd = displayLevels["exclusive_upper"]
        
        modeValue = flowData.getModeValue() # 最頻値
        
        # パーセンタイルベースの適応的スケーリング
        adpLevelMin = flowData.getQuantile(0.01)
        adpLevelEnd = flowData.getQuantile(0.99)
        
        # All levels
        minValue = flowData.getMinValue()
        maxValue = flowData.getMaxValue()
        endValue = createHalfOpenEnd(minValue, maxValue) # 半開区間用の終端値を作成
        
        content = []
        
        # ヘッダ情報を作成
        try:
            text = "\n"
            text += f"Mode: {mode}\n"
            text += f"Planes: {', '.join(planes)}\n"
            text += f"Display Levels: {displayLevelMin:.3f} - {displayLevelEnd:.3f}\n"
            text += f"Adaptive Levels (1-99%): {adpLevelMin:.3f} - {adpLevelEnd:.3f}\n"
            text += f"All levels: {minValue:.3f} - {endValue:.3f}\n"
            text += f"Mode (Peak): {modeValue:.3f}\n"
            
            if 'reference_image_movement' in headers:
                movement = headers['reference_image_movement']
                movement_dx = movement["dx"]
                movement_dy = movement["dy"]
                movement_rot = movement["rotation"]
                text += f"ref image movement: {movement_dx:.1f} px, {movement_dy:.1f} px, {movement_rot:.3f} degree\n"
            
            content.append(text)
        except Exception as e:
            content.append(text + f"\nerror: {str(e)}\n")
            Debug.log(type(self).__name__, "error", e)
        
        # ヒストグラムグラフを作成
        histogramImageKey = (flowData, self._x_scale_var.get(), self._y_scale_var.get())
        if not hasattr(self,'_histogramImagesCahace'):
            self._histogramImagesCahace = {}
        if histogramImageKey in self._histogramImagesCahace:
            # キャッシュに在るのでそれを使う
            histogram_text, histogram_image = self._histogramImagesCahace[histogramImageKey]
            content.append(histogram_text)
            content.append(histogram_image)
        else:
            if not PIL_AVAILABLE:
                content.append("\nImage is not available.\n\n")
            elif not PYPLOT_AVAILABLE:
                content.append("\nmatplotlib is not available.\n\n")
            elif not NUMPY_AVAILABLE:
                content.append("\nNumpy is not available.\n\n")
            else:
                try:
                    # FlowData.getHistogramを使用してプレーン別ヒストグラムを取得
                    fig, ax = plt.subplots(figsize=(6, 3))
                    if planeCount <= 1:
                        colors = ['black']
                    else:
                        colors = ['red', 'green', 'blue', 'darkcyan']
                    
                    # 軸スケール設定を取得
                    ax_xScale = self._x_scale_var.get()
                    ax_yScale = self._y_scale_var.get()
                    
                    histogram_data = flowData.getHistogram(log_scale=("log"==ax_xScale))
                    edgeMin = histogram_data['planes'][0]['bin_edges'][0]
                    edgeMax = histogram_data['planes'][0]['bin_edges'][-1]
                    for data in histogram_data['planes']:
                        edgeMin = min(edgeMin, data['bin_edges'][0])
                        edgeMax = max(edgeMax, data['bin_edges'][-1])
                    
                    total_samples = 0
                    
                    if "log" == ax_xScale and adpLevelEnd > adpLevelMin:
                        # 正規化パラメータ
                        xScale = 0.9 / (edgeMax - edgeMin)
                        xOffset = -edgeMin + 0.1 / xScale
                    else:
                        # 無変換
                        xScale = 1.0
                        xOffset = 0.0
                    
                    for planeIndex, plane_hist in enumerate(histogram_data['planes'][:4]):
                        bin_counts = plane_hist['bin_counts']
                        bin_edges = plane_hist['bin_edges']
                        total_samples += plane_hist['total_samples']
                        
                        # オフセット適用
                        bin_centers = ((bin_edges[:-1] + bin_edges[1:]) / 2 + xOffset) * xScale
                        
                        # ヒストグラム作成
                        # グラフ表示
                        plane_name = planes[planeIndex] if planeIndex < len(planes) else f'Plane{planeIndex}'
                        ax.plot(bin_centers, nh.array(bin_counts) + 1, color=colors[planeIndex], label=plane_name, linewidth=1)
                    
                    histogram_text = f"Histogram per plane ({len(bin_counts)} bins, {total_samples} total samples)\n"
                    ax.set_xlabel(f'Value ({ax_xScale})' if "log" == ax_xScale else f'Value ({ax_xScale}, normalized adjusted)')
                    ax.set_ylabel(f'Count ({ax_yScale})')
                    ax.set_yscale(ax_yScale)
                    ax.set_xscale(ax_xScale)
                    ax.set_title('Histogram by Plane')
                    ax.legend()
                    ax.grid(True, alpha=0.3)
                    
                    if "log"==ax_xScale:
                        # log用カスタム目盛り
                        custom_ticks = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0]
                        ax.set_xticks(custom_ticks)
                        custom_ticks = [0.10, 0.15, 0.20, None, 0.30, None, None, None, 0.50, None, None, None, 0.70, None, None, None, None, None, 1.0]
                        ax.set_xticklabels([sh.dispS(tick / xScale - xOffset) if None!=tick else '' for tick in custom_ticks])
                    
                    # グラフを画像に変換
                    buf = io.BytesIO()
                    plt.rcParams['path.simplify'] = True
                    plt.rcParams['path.simplify_threshold'] = 0.1
                    plt.savefig(buf, format='png', dpi=90)
                    
                    img = Image.open(buf)
                    histogram_image = ImageTk.PhotoImage(img)
                    
                    self._histogramImagesCahace[histogramImageKey] = (histogram_text,histogram_image)
                    content.append(histogram_text)
                    content.append(histogram_image)
                except Exception as e:
                    Debug.log(type(self).__name__, "Histogram error", e)
                    content.append(f"Histogram error: {str(e)}\n")
        
        if not PIL_AVAILABLE:
            content.append("\nImage is not available.\n\n")
        else:
            try:
                # 表示レベルを設定
                displayLevels = self._display_levels_var.get()
                if "display" == displayLevels:
                    scale = 256.0 / (displayLevelEnd - displayLevelMin)
                    offset = float(displayLevelMin)
                    scaleFunc = lambda v: (v - offset) * scale
                elif "adaptive" == displayLevels:
                    scale = 256.0 / (adpLevelEnd - adpLevelMin)
                    offset = float(adpLevelMin)
                    scaleFunc = lambda v: (v - offset) * scale
                elif "all" == displayLevels:
                    scale = 256.0 / (maxValue - minValue)
                    offset = float(minValue)
                    scaleFunc = lambda v: (v - offset) * scale
                elif "isoline" == displayLevels:
                    band  = 10
                    isolineMin = flowData.getQuantile(0.05)
                    isolineEnd = flowData.getQuantile(0.95)
                    scale = float(band) / (isolineEnd - isolineMin)
                    offset = float(isolineMin)
                    _2r = 1+2*band
                    k = nh.zeros((_2r,_2r))
                    for y in range(_2r):
                        for x in range(_2r):
                            if (y-band)**2 + (x-band)**2 <= band**2:
                                k[y,x] = 1.0
                    k /= k.sum()
                    import scipy.ndimage
                    def isoline(v):
                        result = scipy.ndimage.convolve(v, k, mode="reflect")
                        np.add(     result, -offset  , out=result)
                        np.multiply(result, scale    , out=result)
                        np.clip(    result, 0.0, band, out=result)
                        np.mod(     result, 1        , out=result) # 0.0～1.0 の繰り返しに
                        np.add(     result, -0.6     , out=result) # 0.6 以下を0以下に
                        np.multiply(result, 256.0/0.3, out=result) # 0.9 以上を256以上に
                        return result
                    scaleFunc = isoline
                else:
                    scale = 1.0
                    offset = 0.0
                    scaleFunc = lambda v: (v - offset) * scale
                
                if mode.endswith('(DWT)'):
                    # 離散ウェーブレット変換結果かので、分解データをタイル状に表示
                    gridLline = True
                    gridSize  = max(width, height)
                    d_plane  = 3
                    dwtLevel = headers["DWT level"]
                    dwtSize  = headers["DWT size"]
                    src = []
                    dst = []
                    for p in range(d_plane):
                        src.append((p*(1+(dwtLevel)*3),0,0,dwtSize[0],dwtSize[1]))
                        dst.append((p                 ,0,0))
                    x = dwtSize[0]
                    y = dwtSize[1]
                    for l in range(dwtLevel):
                        w = dwtSize[2*l]
                        h = dwtSize[2*l+1]
                        for p in range(d_plane):
                            src.append((p*(1+3*dwtLevel)+3*l+1,0,0,w,h))
                            dst.append((p                     ,x,0))
                            src.append((p*(1+3*dwtLevel)+3*l+2,0,0,w,h))
                            dst.append((p                     ,0,y))
                            src.append((p*(1+3*dwtLevel)+3*l+3,0,0,w,h))
                            dst.append((p                     ,x,y))
                        x += w
                        y += h
                    d_width  = x
                    d_height = y
                else:
                    # 四隅拡大を設定
                    displayCorners = self._display_corner_var.get()
                    if "full" == displayCorners:
                        gridLline = False
                        gridSize  = max(width, height)
                        d_plane   = planeCount
                        d_width   = width
                        d_height  = height
                        src = []
                        dst = []
                        for p in range(planeCount):
                            src.append((p,0,0,width,height))
                            dst.append((p,0,0))
                    elif "3x3 grid" == displayCorners:
                        gridLline = True
                        gridSize  = 160
                        d_plane   = planeCount
                        d_width   = 3*gridSize
                        d_height  = 3*gridSize
                        src = []
                        dst = []
                        for p in range(planeCount):
                            for y in range(3):
                                for x in range(3):
                                    src.append((p, (width -gridSize)*x//2, (height-gridSize)*y//2, gridSize, gridSize))
                                    dst.append((p, x*gridSize, y*gridSize))
                    elif "5x5 grid" == displayCorners:
                        gridLline = True
                        gridSize  = 96
                        d_plane   = planeCount
                        d_width   = 5*gridSize
                        d_height  = 5*gridSize
                        src = []
                        dst = []
                        for p in range(planeCount):
                            for y in range(5):
                                for x in range(5):
                                    src.append((p, (width -gridSize)*x//4, (height-gridSize)*y//4, gridSize, gridSize))
                                    dst.append((p, x*gridSize, y*gridSize))
                    else:
                        gridLline = False
                        gridSize  = max(width, height)
                        d_plane   = planeCount
                        d_width   = width
                        d_height  = height
                        src = []
                        dst = []
                        for p in range(planeCount):
                            src.append((p,0,0,width,height))
                            dst.append((p,0,0))
                
                # ズームを設定
                displayzooms = self._display_zoom_var.get()
                if "fit" == displayzooms:
                    fit = True
                    zoom = 1
                elif "x1" == displayzooms:
                    fit = False
                    zoom = 1
                elif "x2" == displayzooms:
                    fit = False
                    zoom = 2
                elif "x3" == displayzooms:
                    fit = False
                    zoom = 3
                else:
                    fit = True
                    zoom = 1
                
                # 画像構築
                dataImageKey = (flowData, displayLevels, displayCorners)
                if not hasattr(self,'_dataImagesCahace'):
                    self._dataImagesCahace = {}
                if dataImageKey in self._dataImagesCahace:
                    # キャッシュに在るのでそれを使う
                    img, cont = self._dataImagesCahace[dataImageKey]
                else:
                    img, cont = self.createImage(flowData, scaleFunc, d_plane, d_width, d_height, src, dst, gridLline)
                    self._dataImagesCahace[dataImageKey] = (img, cont)
                content.extend(cont)
                
                # 画像を拡縮
                if 1 != zoom:
                    img = img.resize((int(img.width * zoom), int(img.height * zoom)), Image.Resampling.LANCZOS)
                
                if fit:
                    window_width = self.winfo_width()
                    max_width = window_width - 40  # 最小余白
                    
                    display_width, display_height = img.size
                    if display_width > max_width:
                        ratio = max_width / display_width
                        display_width = int(display_width * ratio)
                        display_height = int(display_height * ratio)
                        img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
                
                # Tkinterで表示するためにPhotoImageに変換
                photo = ImageTk.PhotoImage(img)
                content.append(photo)
            except Exception as e:
                Debug.log( type(self).__name__, "error", e)
                content.append(f"\nerror: {str(e)}\n\n")
        
        # EXIF情報を表示
        exif = headers.get('exif', {})
        if exif:
            text = f"\nEXIF:\n"
            for key, value in exif.items():
                text += f"{key}: {value}\n"
            content.append(text)
        
        return content
    
    def _updateControlVisibility(self):
        """コントロールフレームの表示/非表示を制御"""
        # 画像制御部分のみ画像データがある場合に表示
        has_image_data = any(data.headers and data.headers.get('type') == 'image' for data in self.node.flowDatas)
        
        # ヒストグラム軸制御と表示レベル制御の表示/非表示
        for child in self._control_frame.winfo_children():
            if hasattr(child, '_is_image_control'):
                if has_image_data:
                    child.pack(fill=tk.X, pady=(5,0))
                else:
                    child.pack_forget()
    
    def _updateDataCombo(self):
        """データ選択コンボボックスを更新"""
        # コンボボックスの選択肢を更新
        options = []
        for i, flowData in enumerate(self.node.flowDatas):
            headers = flowData.headers if flowData.headers else {}
            data_type = headers.get('type', 'unknown')
            
            # header からファイル名や時刻を取得
            name = f"{i + 1}: ({data_type})"
            if 'source_file' in headers:
                name += f" {headers['source_file']}"
            if 'datetime' in headers:
                name += f" - {headers['datetime']}"
            
            options.append(name)
        
        self._data_combo['values'] = options
        
        # 初期選択を設定
        if options and not self._selected_data_var.get():
            self._selected_data_var.set(options[0])
    
    def _getSelectedFlowData(self):
        """選択されたフローデータを取得"""
        selected = self._selected_data_var.get()
        if not selected:
            return self.node.flowDatas[0] if self.node.flowDatas else None
        
        # 選択されたインデックスを取得
        index = int(selected.split(':')[0]) - 1
        if 0 <= index < len(self.node.flowDatas):
            return self.node.flowDatas[index]
        
        return self.node.flowDatas[0] if self.node.flowDatas else None
    
    def _onComboKeyPress(self, event):
        """コンボボックスのキーイベント処理"""
        if event.keysym in ['Up', 'Down']:
            current_values = self._data_combo['values']
            if not current_values:
                return 'break'
            
            current_selection = self._selected_data_var.get()
            current_index = list(current_values).index(current_selection)
            
            if event.keysym == 'Up':
                new_index = (current_index - 1) % len(current_values)
            else:  # Down
                new_index = (current_index + 1) % len(current_values)
            
            self._selected_data_var.set(current_values[new_index])
            self.updateResult()
            return 'break'  # デフォルト動作を無効化
    
    def createImage(self, flowData, scaleFunc, d_plane, d_width, d_height, src, dst, gridLline=False):
        """
        画像データを構築
        
        Args:
            flowData (FlowData): FlowDataオブジェクト
            scaleFunc (float): レベル調整関数
            d_plane (int): 出力プレーン数
            d_width (int): 出力画像の幅
            d_height (int): 出力画像の高さ
            src (list): コピー元座標 (plane, x, y, width, height)
            dst (list): コピー先座標 (plane, x, y)
            gridLline (bool): グリッド線を表示するかどうか
        
        Returns:
            Image: 画像
            list: 代用内容
        """
        # 画像データを構築
        imgArray = np.zeros((d_height, d_width, d_plane), dtype=np.uint8)
        content = []
        
        gridW = max( w for p,x,y,w,h in src)
        gridH = max( h for p,x,y,w,h in src)
        
        if d_height <= gridW and d_width <= gridH:
            tmpImg = imgArray # グリッドの方が大きいので作業領域は同じ
        else:
            tmpImg = np.empty((gridH, gridW, d_plane), dtype=np.uint8) # 作業領域は使いまわす
        
        for (sp,sx1,sy1,sw,sh),(dp,dx,dy) in zip(src, dst):
            sx2 = sx1+sw
            sy2 = sy1+sh
            x1  = nh.floor(sx1, BLOCK_SIZE).astype(int) # コピー元を包含するブロック座標
            y1  = nh.floor(sy1, BLOCK_SIZE).astype(int)
            x2  = nh.ceil( sx2, BLOCK_SIZE).astype(int)
            y2  = nh.ceil( sy2, BLOCK_SIZE).astype(int)
            
            try:
                # Z階数曲線でブロックを収集
                from utils.order import zOrderGenerator
                for bx1, by1 in zOrderGenerator(x1, y1, x2, y2, BLOCK_SIZE, BLOCK_SIZE): # コピー元を含むブロックの座標
                    block = flowData.getBlock(sp, bx1, by1)
                    data  = block.data if block else None
                    if not data is None:
                        try:
                            cx1 = max(sx1, bx1) # コピー元座標とブロック座標 の積集合
                            cy1 = max(sy1, by1)
                            cx2 = min(sx2, bx1+data.shape[1])
                            cy2 = min(sy2, by1+data.shape[0])
                            trimed  = data[cy1-by1:cy2-by1, cx1-bx1:cx2-bx1] # 切り出し
                            if np.iscomplexobj(trimed):
                                trimed = np.abs(trimed) # 複素数なので、絶対値を取る
                            leveled = scaleFunc(trimed)                      # レベル調整を適用
                            norm    = np.nan_to_num( leveled, nan=0.0)       # NaN を 0 に変換
                            cliped  = np.clip(norm, 0, 255).astype(np.uint8) # [0,256) にクリップ
                            tmpImg[cy1-sy1:cy2-sy1, cx1-sx1:cx2-sx1, dp] = cliped
                        except (IndexError, TypeError, ValueError) as e:
                            Debug.log(type(self).__name__, "error", e)
                            content.append(f"\nerror: {str(e)}\n\n")
                
                if gridLline:
                    if 0 < dy:
                        tmpImg[0      , 0:gridW, dp] = 128
                    if 0 < dx:
                        tmpImg[0:gridH, 0      , dp] = 128
                
                if imgArray is not tmpImg:
                    # 作業領域が別なのでコピー
                    w = min(sw, d_width  - dx)
                    h = min(sh, d_height - dy)
                    imgArray[dy:dy+h, dx:dx+w, dp] = tmpImg[0:h, 0:w, dp]
            
            except (IndexError, TypeError, ValueError) as e:
                Debug.log(type(self).__name__, "error", e)
                content.append(f"\nerror: {str(e)}\n\n")
        
        if 4 == d_plane:
            # 4 プレーンあるので RGBG として、1,3 プレーンを平均する
            imgArray[:, :, 1] = imgArray[:, :, 1] // 2 + imgArray[:, :, 3] // 2
            img = Image.fromarray(imgArray[0:d_height, 0:d_width, 0:3], 'RGB')
        elif 3 == d_plane:
            img = Image.fromarray(imgArray[0:d_height, 0:d_width, 0:3], 'RGB')
        elif 1 == d_plane:
            img = Image.fromarray(imgArray[0:d_height, 0:d_width, 0].squeeze(), 'L')
        
        return(img, content)
