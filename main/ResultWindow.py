'''
結果ウィンドウクラス

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import json
import sys
import traceback
import io
import tkinter as tk
from tkinter import ttk

from config import BLOCK_SIZE
from base.LazyFlowData import LazyHeadersDict
from utils import string_helper as sh
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
        self.geometry("600x400")
        
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
        self._data_combo = tk.ttk.Combobox(data_select_frame, textvariable=self._selected_data_var, state="readonly", width=30)
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
        
        # 表示レベル制御（画像データのみ）
        level_frame = tk.Frame(control_frame)
        level_frame._is_image_control = True
        
        tk.Label(level_frame, text="画像表示レベル:").pack(side=tk.LEFT)
        
        self._display_levels_var = tk.StringVar(value="display")
        tk.Radiobutton(level_frame, text="display", variable=self._display_levels_var, value="display", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="adaptive", variable=self._display_levels_var, value="adaptive", command=self.updateResult).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="all", variable=self._display_levels_var, value="all", command=self.updateResult).pack(side=tk.LEFT)
        
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
        
        if   dataType == 'polynomial': result = self._generatePolynomialContent(flowData)
        elif dataType == 'table': result = self._generateTableContent(flowData)
        elif dataType == 'image' : result = self._generateImageContent(flowData)
        else:                      result = self._generateGenericContent(flowData)
        
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

        width, height = flowData.getDimensions()
        planes = headers.get('planes', [])

        # データ行 (最初の10行,10列のみ表示)
        displayRows = min(height, 10)  # 最初の10行のみ
        displayCols = min(width , 10)  # 最初の10列のみ
        
        for planeIdx, planeName in enumerate(planes):
            content += f"\n[plane: {planeName}]\n"
        
            # ヘッダー行
            if width:
                content += "\t" + "\t".join([f"{x}" for x in range(width)]) + "\n"
            
            if 0 < displayRows and 0 < displayCols:
                block = flowData.getBlock(0, 0, 0)
                if block and block.data is not None:
                    h, w = block.data.shape
                    for dy in range(h):
                        row_data = [f"{dy}"]
                        for dx in range(w):
                            try:
                                value = block.data[dy][dx]
                                row_data.append(sh.dispL(value))
                            except (IndexError, TypeError):
                                row_data.append("_")

                        if width > displayCols:
                            row_data.append("...")
                    
                        content += "\t".join(row_data) + "\n"
            
                    if height > displayRows:
                        content += "...\n"
        
        return content
        
    def _generatePolynomialContent(self, flowData):
        """Polynomialデータの内容を生成"""
        headers = flowData.headers
        content = "\n"
        
        columns = headers.get('columns', [])
        lines = headers.get('lines', [])
        planes = headers.get('planes', [])
        
        for planeIdx, planeName in enumerate(planes):
            content += f"\n[plane: {planeName}]\n"
            
            # ヘッダー行
            if columns:
                content += "\t" + "\t".join(columns) + "\n"
            
            # データ行
            width, height = flowData.getDimensions()
            block = flowData.getBlock(planeIdx, 0, 0)
            for y in range(height):
                lineLabel = lines[y] if y < len(lines) else f"row_{y}"
                content += f"{lineLabel}\t"
                
                row_data = []
                for x in range(width):
                    try:
                        value = block.data[y][x]
                        row_data.append(sh.dispL(value))
                    except (IndexError, TypeError):
                        row_data.append("_")
                
                content += "\t".join(row_data) + "\n"
        
        return content
    
    def _generateTableContent(self, flowData):
        """マトリックスデータの内容を生成"""
        headers = flowData.headers
        content = "\n"
        
        columns = headers.get('columns', [])
        lines = headers.get('lines', [])
        
        # ヘッダー行
        if columns:
            length = max([len(label) for label in lines])
            content += "\t"*(length//8+1) + "\t".join(columns) + "\n"
        
        # データ行 (最初の10行,10列のみ表示)
        width, height = flowData.getDimensions()
        displayRows = min(height, 10)  # 最初の10行のみ
        displayCols = min(width , 10)  # 最初の10列のみ
        
        if 0 < displayRows and 0 < displayCols:
            block = flowData.getBlock(0, 0, 0)
            if block and block.data is not None:
                h, w = block.data.shape
                for dy in range(h):
                    row_data = [lines[dy] if dy < len(lines) else f"row_{dy}"]
                    for dx in range(w):
                        try:
                            value = block.data[dy][dx]
                            row_data.append(sh.dispL(value))
                        except (IndexError, TypeError):
                            row_data.append("_")

                    if width > displayCols:
                        row_data.append("...")
                
                    content += "\t".join(row_data) + "\n"
        
                if height > displayRows:
                    content += "...\n"
        
        return content
    
    def _generateImageContent(self, flowData):
        """画像データの内容を生成"""
        headers = flowData.headers
        
        mode = flowData.getMode()
        planes = headers.get('planes', [])
        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        displayLevels = headers['display_levels']
        displayLevelMin = displayLevels["min"]
        displayLevelEnd = displayLevels["exclusive_upper"]

        modeValue = flowData.getModeValue() # 最頻値

        # パーセンタイルベースの適応的スケーリング
        adpLevelMin = flowData.getPercentile(1)
        adpLevelEnd = flowData.getPercentile(99)
        
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
            text += f"Adaptive Levels: {adpLevelMin:.3f} - {adpLevelEnd:.3f}\n"
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
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            content.append(text + f"\nerror: {str(e)}\n")
        
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
                    
                    for planeIdx, plane_hist in enumerate(histogram_data['planes'][:4]):
                        bin_counts = plane_hist['counts']
                        bin_edges = plane_hist['bin_edges']
                        total_samples += plane_hist['total_samples']
                        
                        # オフセット適用
                        bin_centers = ((bin_edges[:-1] + bin_edges[1:]) / 2 + xOffset) * xScale

                        # グラフ表示
                        plane_name = planes[planeIdx] if planeIdx < len(planes) else f'Plane{planeIdx}'
                        ax.plot(bin_centers, np.array(bin_counts) + 1, color=colors[planeIdx], label=plane_name, linewidth=1)
                    
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

                    # 画像を2倍に拡大
                    img = Image.open(buf)
                    #enlarged_img = img.resize((int(img.width * 1.5), int(img.height * 1.5)), Image.Resampling.LANCZOS)
                    histogram_image = ImageTk.PhotoImage(img)

                    self._histogramImagesCahace[histogramImageKey] = (histogram_text,histogram_image)
                    content.append(histogram_text)
                    content.append(histogram_image)
                except Exception as e:
                    tb = traceback.format_exc()
                    print(tb,file=sys.stderr)
                    content.append(f"Histogram error: {str(e)}\n")
        
        if not PIL_AVAILABLE:
            content.append("\nImage is not available.\n\n")
        else:
            try:
                # 表示レベル設定を取得
                displayLevels = self._display_levels_var.get()

                # 表示レベルを設定
                if "display" == displayLevels:
                    scale = 255.0 / (displayLevelEnd - displayLevelMin)
                    offset = float(displayLevelMin)
                elif "adaptive" == displayLevels:
                    scale = 255.0 / (adpLevelEnd - adpLevelMin)
                    offset = float(adpLevelMin)
                elif "all" == displayLevels:
                    scale = 255.0 / (maxValue - minValue)
                    offset = float(minValue)
                else:
                    scale = 1.0
                    offset = 0.0
                
                # 画像データを再構成
                if 'RGB' == mode and 3 <= planeCount:
                    imgArray = np.zeros((height, width, 3), dtype=np.uint8)
                    
                    for planeIdx in range(3):
                        for y in range(0, height, BLOCK_SIZE):
                            for x in range(0, width, BLOCK_SIZE):
                                block = flowData.getBlock(planeIdx, x, y)
                                if block and block.data is not None:
                                    try:
                                        blockHeight = min(block.getHeight(), height - y)
                                        blockWidth = min(block.getWidth(), width - x)
                                        endY = y + blockHeight
                                        endX = x + blockWidth
                                        
                                        # レベル調整を適用（NaNは0に変換）
                                        data = block.data[:blockHeight, :blockWidth]
                                        normalized = np.nan_to_num((data - offset) * scale, nan=0.0)
                                        imgArray[y:endY, x:endX, planeIdx] = np.clip(normalized, 0, 255).astype(np.uint8)
                                    except (IndexError, TypeError, ValueError) as e:
                                        content.append(f"\n{str(e)}\n\n")
                    
                    img = Image.fromarray(imgArray, 'RGB')
                elif 'RGBG' == mode and 4 <= planeCount:
                    imgArray = np.zeros((height, width, 3), dtype=np.uint8)
                    
                    for y in range(0, height, BLOCK_SIZE):
                        for x in range(0, width, BLOCK_SIZE):
                            r_block = flowData.getBlock(0, x, y)
                            g1_block = flowData.getBlock(1, x, y)
                            b_block = flowData.getBlock(2, x, y)
                            g2_block = flowData.getBlock(3, x, y)
                            
                            if r_block and g1_block and b_block and g2_block:
                                if (   r_block.data is not None
                                   and g1_block.data is not None
                                   and b_block.data is not None
                                   and g2_block.data is not None
                                   ):
                                    try:
                                        blockHeight = min(r_block.getHeight(), height - y)
                                        blockWidth = min(r_block.getWidth(), width - x)
                                        endY = y + blockHeight
                                        endX = x + blockWidth
                                        
                                        g_avg = (g1_block.data[:blockHeight, :blockWidth] + g2_block.data[:blockHeight, :blockWidth]) / 2
                                        
                                        # レベル調整を適用（NaNは0に変換）
                                        r_norm = np.nan_to_num((r_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                                        g_norm = np.nan_to_num((g_avg - offset) * scale, nan=0.0)
                                        b_norm = np.nan_to_num((b_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                                        
                                        imgArray[y:endY, x:endX, 0] = np.clip(r_norm, 0, 255).astype(np.uint8)
                                        imgArray[y:endY, x:endX, 1] = np.clip(g_norm, 0, 255).astype(np.uint8)
                                        imgArray[y:endY, x:endX, 2] = np.clip(b_norm, 0, 255).astype(np.uint8)
                                    except (IndexError, TypeError, ValueError) as e:
                                        content.append(f"\n{str(e)}\n\n")
                    
                    img = Image.fromarray(imgArray, 'RGB')
                elif(  'L'     == mode and 1 <= planeCount
                    or 'BAYER' == mode and 1 <= planeCount
                    ):
                    imgArray = np.zeros((height, width), dtype=np.uint8)
                    
                    for y in range(0, height, BLOCK_SIZE):
                        for x in range(0, width, BLOCK_SIZE):
                            block = flowData.getBlock(0, x, y)
                            if block and block.data is not None:
                                try:
                                    blockHeight = min(block.getHeight(), height - y)
                                    blockWidth = min(block.getWidth(), width - x)
                                    endY = y + blockHeight
                                    endX = x + blockWidth
                                    
                                    # レベル調整を適用（NaNは0に変換）
                                    normalized = np.nan_to_num((block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                                    imgArray[y:endY, x:endX] = np.clip(normalized, 0, 255).astype(np.uint8)
                                except (IndexError, TypeError, ValueError) as e:
                                    content.append(f"\n{str(e)}\n\n")
                    
                    img = Image.fromarray(imgArray, 'L')
                else:
                    raise ValueError(f"サポートされていないモード: {mode}")
                
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
                tb = traceback.format_exc()
                print(tb,file=sys.stderr)
                content.append(f"\n画像表示エラー: {str(e)}\n\n")
        
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
            
            # EXIF情報からファイル名や時刻を取得
            display_name = f"データ {i + 1} ({data_type})"
            if 'exif' in headers:
                exif = headers['exif']
                if 'DateTime' in exif:
                    display_name += f" - {exif['DateTime']}"
            
            options.append(display_name)
        
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
        index = int(selected.split('データ ')[1].split(' ')[0]) - 1
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
