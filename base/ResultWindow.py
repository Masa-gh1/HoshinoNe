'''
結果ウィンドウクラス

@author: Masakazu Inoue
'''

import sys
import threading
import traceback
import io
import tkinter as tk
from tkinter import ttk
from utils.interval_helper import createHalfOpenEnd

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

class ResultWindow:
    def __init__(self, root, node):
        self.root = root
        self.node = node
        
    def show(self):
        """結果ウィンドウを表示"""
        # 既存の結果ウィンドウをチェック
        if hasattr(self.node, '_result_window') and self.node._result_window.winfo_exists():
            # 既存ウィンドウを更新
            self._updateResultWindow()
            self.node._result_window.lift()
            return
        
        # 新しいウィンドウで結果を表示
        resultWindow = tk.Toplevel(self.root)
        resultWindow.title(f"{self.node.text} - 処理結果")
        resultWindow.geometry("600x400")
        
        # ウィンドウ参照を保存
        self.node._result_window = resultWindow
        
        # 制御フレーム
        control_frame = tk.Frame(resultWindow)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        self.node._control_frame = control_frame
        
        # データ選択フレーム（常に表示）
        data_select_frame = tk.Frame(control_frame)
        data_select_frame.pack(fill=tk.X)
        self.node._data_select_frame = data_select_frame
        
        tk.Label(data_select_frame, text="表示データ:").pack(side=tk.LEFT)
        self.node._selected_data_var = tk.StringVar()
        self.node._data_combo = tk.ttk.Combobox(data_select_frame, textvariable=self.node._selected_data_var, state="readonly", width=30)
        self.node._data_combo.pack(side=tk.LEFT, padx=(5,0))
        self.node._data_combo.bind('<<ComboboxSelected>>', lambda e: self._updateResultWindow())
        self.node._data_combo.bind('<Key>', self._onComboKeyPress)
        
        # ヒストグラム軸制御（画像データのみ）
        axis_frame = tk.Frame(control_frame)
        axis_frame._is_image_control = True
        
        tk.Label(axis_frame, text="ヒストグラム軸:").pack(side=tk.LEFT)
        
        # X軸制御
        self.node._x_scale_var = tk.StringVar(value="log")
        tk.Label(axis_frame, text="X軸:").pack(side=tk.LEFT, padx=(10,0))
        tk.Radiobutton(axis_frame, text="Log", variable=self.node._x_scale_var, value="log", command=self._updateResultWindow).pack(side=tk.LEFT)
        tk.Radiobutton(axis_frame, text="Linear", variable=self.node._x_scale_var, value="linear", command=self._updateResultWindow).pack(side=tk.LEFT)
        
        # Y軸制御
        self.node._y_scale_var = tk.StringVar(value="log")
        tk.Label(axis_frame, text="Y軸:").pack(side=tk.LEFT, padx=(10,0))
        tk.Radiobutton(axis_frame, text="Log", variable=self.node._y_scale_var, value="log", command=self._updateResultWindow).pack(side=tk.LEFT)
        tk.Radiobutton(axis_frame, text="Linear", variable=self.node._y_scale_var, value="linear", command=self._updateResultWindow).pack(side=tk.LEFT)
        
        # 表示レベル制御（画像データのみ）
        level_frame = tk.Frame(control_frame)
        level_frame._is_image_control = True
        
        tk.Label(level_frame, text="画像表示レベル:").pack(side=tk.LEFT)
        
        self.node._display_levels_var = tk.StringVar(value="display")
        tk.Radiobutton(level_frame, text="display", variable=self.node._display_levels_var, value="display", command=self._updateResultWindow).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="adaptive", variable=self.node._display_levels_var, value="adaptive", command=self._updateResultWindow).pack(side=tk.LEFT)
        tk.Radiobutton(level_frame, text="all", variable=self.node._display_levels_var, value="all", command=self._updateResultWindow).pack(side=tk.LEFT)
        
        # スクロールバー付きテキストエリア
        frame = tk.Frame(resultWindow)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(frame, wrap=tk.WORD)
        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # テキストウィジェット参照を保存
        self.node._result_text_widget = text_widget
        
        # ウィンドウが閉じられたときのクリーンアップ
        def on_close():
            if hasattr(self.node, '_result_window'):
                delattr(self.node, '_result_window')
            if hasattr(self.node, '_result_text_widget'):
                delattr(self.node, '_result_text_widget')
            if hasattr(self.node, '_control_frame'):
                delattr(self.node, '_control_frame')
            resultWindow.destroy()
        
        resultWindow.protocol("WM_DELETE_WINDOW", on_close)
        
        # ウィンドウの幅変更時のみ画像を再描画（300ms毎）
        self._resize_timer = None
        self._last_width = resultWindow.winfo_width()
        
        def on_configure(event):
            if event.widget == resultWindow and not self._resize_timer:
                current_width = resultWindow.winfo_width()
                if current_width != self._last_width:
                    self._last_width = current_width
                    def update():
                        self._resize_timer = None
                        self._updateResultWindow()
                    self._resize_timer = self.root.after(300, update)
        
        resultWindow.bind('<Configure>', on_configure)
        
        # データ選択コンボボックスを更新
        self._updateDataCombo()
        
        # 初回表示（別スレッドで実行）
        thread = threading.Thread(target=self._updateResultWindowAsync)
        thread.daemon = True
        thread.start()
        
        # コントロールフレームの表示状態を更新
        self._updateControlVisibility()
    
    def update(self):
        """結果ウィンドウの内容を更新"""
        self._updateResultWindow()
    
    def _updateResultWindow(self):
        """結果ウィンドウの内容を更新（別スレッドで実行）"""
        thread = threading.Thread(target=self._updateResultWindowAsync)
        thread.daemon = True
        thread.start()
    
    def _updateResultWindowAsync(self):
        """結果ウィンドウの内容を非同期で更新"""
        if not hasattr(self.node, '_result_text_widget'):
            return
        
        # タイトルを更新してデータ読み込み中を表示
        def update_title_loading():
            if hasattr(self.node, '_result_window'):
                self.node._result_window.title(f"{self.node.text} - データ読み込み中...")
        
        self.root.after(0, update_title_loading)
        
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
            if hasattr(self.node, '_result_window'):
                self.node._result_window.title(f"{self.node.text} - 処理結果")
            if hasattr(self.node, '_result_text_widget'):
                text_widget = self.node._result_text_widget
                
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
        
        self.root.after(0, display_result)
        
        # コントロールフレームの表示状態を更新
        self.root.after(0, self._updateControlVisibility)
        self.root.after(0, self._updateDataCombo)
    
    def _generateFlowDataContent(self, flowData):
        """フローデータの内容を文字列として生成（非同期処理用）"""
        headers = flowData.headers if flowData.headers else {}
        dataType = headers.get('type', 'unknown')
        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        
        content = []
        text = f"Type: {dataType}\n"
        text += f"PlaneCount: {planeCount}\n"
        text += f"Dimensions: {width} x {height}\n"
        content.append(text)
        
        if   dataType == 'tensor': result = self._generateTensorContent(flowData, headers)
        elif dataType == 'matrix': result = self._generateMatrixContent(flowData, headers)
        elif dataType == 'image' : result = self._generateImageContent(flowData, headers)
        else:                      result = self._generateGenericContent(flowData, headers)
        
        if isinstance(result, list):
            content.extend(result)
        else:
            content.append(result)
        return content
    
    def _generateTensorContent(self, flowData, headers):
        """テンソルデータの内容を生成"""
        content = "\n"
        
        columns = headers.get('columns', [])
        lines = headers.get('lines', [])
        planes = headers.get('planes', [])
        
        for planeIdx, planeName in enumerate(planes):
            content += f"\n[{planeName} プレーン]\n"
            
            # ヘッダー行
            if columns:
                content += "\t" + "\t".join(columns) + "\n"
            
            # データ行
            width, height = flowData.getDimensions()
            for y in range(height):
                lineLabel = lines[y] if y < len(lines) else f"row_{y}"
                content += f"{lineLabel}\t"
                
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
                
                content += "\t".join(row_data) + "\n"
        
        return content
    
    def _generateMatrixContent(self, flowData, headers):
        """マトリックスデータの内容を生成"""
        content = "\n"
        
        columns = headers.get('columns', [])
        lines = headers.get('lines', [])
        
        # ヘッダー行
        if columns:
            content += "\t" + "\t".join(columns) + "\n"
        
        # データ行 (最初の10行のみ表示)
        width, height = flowData.getDimensions()
        displayRows = min(height, 10)
        
        for y in range(displayRows):
            lineLabel = lines[y] if y < len(lines) else f"row_{y}"
            content += f"{lineLabel}\t"
            
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
            
            content += "\t".join(row_data) + "\n"
        
        if height > 10:
            content += "...\n"
        
        return content
    
    def _generateImageContent(self, flowData, headers):
        """画像データの内容を生成"""
        mode = flowData.getMode()
        planes = headers.get('planes', [])
        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        displayLevels = headers.get('display_levels')
        displayLevelMin = displayLevels["min"]
        displayLevelEnd = displayLevels["exclusive_upper"]
        
        # パーセンタイルベースの適応的スケーリング
        minValue = flowData.getMinValue()
        maxValue = flowData.getMaxValue()
        # 半開区間用の終端値を作成
        allLevelEnd = createHalfOpenEnd(minValue, maxValue)
        adpLevelMin = flowData.getPercentile(1)
        adpLevelEnd = flowData.getPercentile(99)
        
        content = []
        
        text = "\n"
        text += f"Mode: {mode}\n"
        text += f"Planes: {', '.join(planes)}\n"
        text += f"Display Levels: {displayLevelMin} - {displayLevelEnd}\n"
        text += f"Adaptive Levels: {adpLevelMin:.3f} - {adpLevelEnd:.3f}\n"
        text += f"All levels: [{minValue:.3f}, {allLevelEnd:.3f})\n"
        content.append(text)
        
        # ヒストグラムグラフを作成
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
                colors = ['red', 'green', 'blue', 'cyan']
                plane_names = planes[:min(planeCount, 4)]
                
                # 軸スケール設定を取得
                ax_xScale = self.node._x_scale_var.get()
                ax_yScale = self.node._y_scale_var.get()
                
                histogram_data = flowData.getHistogram(log_scale=("log"==ax_xScale))
                total_samples = 0
                
                if "log" == ax_xScale and adpLevelEnd > adpLevelMin:
                    # 正規化パラメータ
                    xScale = 0.9 / (maxValue - minValue)
                    xOffset = -minValue + 0.1 / xScale
                else:
                    # 無変換
                    xScale = 1.0
                    xOffset = 0.0
                
                for planeIdx, plane_hist in enumerate(histogram_data['planes'][:4]):
                    bin_counts = plane_hist['counts']
                    bin_edges = plane_hist['bin_edges']
                    total_samples += plane_hist['total_samples']
                    
                    # オフセット適用
                    bin_centers = [((bin_edges[i] + bin_edges[i+1]) / 2 + xOffset) * xScale for i in range(len(bin_counts))]
                    
                    # ステップグラフで表示
                    plane_name = plane_names[planeIdx] if planeIdx < len(plane_names) else f'Plane{planeIdx}'
                    ax.step(bin_centers, np.array(bin_counts) + 1, where='mid', color=colors[planeIdx], label=plane_name, linewidth=1.5)
                
                content += f"Histogram per plane ({len(bin_counts)} bins, {total_samples} total samples)\n"
                ax.set_xlabel(f'Value ({ax_xScale})' if "log" == ax_xScale else f'Value ({ax_xScale}, normalized adjusted)')
                ax.set_ylabel(f'Count ({ax_yScale})')
                ax.set_yscale(ax_yScale)
                ax.set_xscale(ax_xScale)
                ax.set_title('Histogram by Plane')
                ax.legend()
                ax.grid(True, alpha=0.3)
                
                if "log"==ax_xScale:
                    # log用カスタム目盛り
                    custom_ticks = [0.1, 0.2, 0.3, 0.6, 1.0]
                    ax.set_xticks(custom_ticks)
                    ax.set_xticklabels([f'{tick / xScale - xOffset:.0f}' for tick in custom_ticks])
                
                # グラフを画像に変換
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
                buf.seek(0)
    
                histogram_image = ImageTk.PhotoImage(Image.open(buf))
                plt.close(fig)
                
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
                displayLevels = self.node._display_levels_var.get()

                # 表示レベルを設定
                if "display" == displayLevels:
                    scale = 255.0 / (displayLevelEnd - displayLevelMin)
                    offset = displayLevelMin
                elif "adaptive" == displayLevels:
                    scale = 255.0 / (adpLevelEnd - adpLevelMin)
                    offset = adpLevelMin
                elif "all" == displayLevels:
                    scale = 255.0 / (maxValue - minValue)
                    offset = minValue
                else:
                    scale = 1.0
                    offset = 0.0
                
                # 画像データを再構成
                if mode == 'RGB' and planeCount >= 3:
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
                                        
                                        # 適応的スケーリングで補正
                                        data = block.data[:blockHeight, :blockWidth]
                                        normalized = (data - offset) * scale
                                        imgArray[blockY:endY, blockX:endX, planeIdx] = np.clip(normalized, 0, 255).astype(np.uint8)
                                    except (IndexError, TypeError, ValueError):
                                        pass
                    
                    img = Image.fromarray(imgArray, 'RGB')
                elif mode == 'RGGB' and planeCount >= 4:
                    imgArray = np.zeros((height, width, 3), dtype=np.uint8)
                    
                    for blockY in range(0, height, 256):
                        for blockX in range(0, width, 256):
                            r_block = flowData.getBlock(0, blockX, blockY)
                            g1_block = flowData.getBlock(1, blockX, blockY)
                            b_block = flowData.getBlock(2, blockX, blockY)
                            g2_block = flowData.getBlock(3, blockX, blockY)
                            
                            if r_block and g1_block and b_block and g2_block:
                                if (hasattr(r_block, 'data') and r_block.data is not None and
                                    hasattr(g1_block, 'data') and g1_block.data is not None and
                                    hasattr(b_block, 'data') and b_block.data is not None and
                                    hasattr(g2_block, 'data') and g2_block.data is not None):
                                    try:
                                        blockHeight = min(256, height - blockY)
                                        blockWidth = min(256, width - blockX)
                                        endY = blockY + blockHeight
                                        endX = blockX + blockWidth
                                        
                                        g_avg = (g1_block.data[:blockHeight, :blockWidth] + g2_block.data[:blockHeight, :blockWidth]) / 2
                                        
                                        # 適応的スケーリングで補正
                                        r_norm = (r_block.data[:blockHeight, :blockWidth] - offset) * scale
                                        g_norm = (g_avg - offset) * scale
                                        b_norm = (b_block.data[:blockHeight, :blockWidth] - offset) * scale
                                        
                                        imgArray[blockY:endY, blockX:endX, 0] = np.clip(r_norm, 0, 255).astype(np.uint8)
                                        imgArray[blockY:endY, blockX:endX, 1] = np.clip(g_norm, 0, 255).astype(np.uint8)
                                        imgArray[blockY:endY, blockX:endX, 2] = np.clip(b_norm, 0, 255).astype(np.uint8)
                                    except (IndexError, TypeError, ValueError):
                                        pass
                    
                    img = Image.fromarray(imgArray, 'RGB')
                elif mode == 'L' and planeCount >= 1:
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
                                    
                                    # 適応的スケーリングで補正
                                    normalized = (block.data[:blockHeight, :blockWidth] - offset) * scale
                                    imgArray[blockY:endY, blockX:endX] = np.clip(normalized, 0, 255).astype(np.uint8)
                                except (IndexError, TypeError, ValueError):
                                    pass
                    
                    img = Image.fromarray(imgArray, 'L')
                else:
                    return content.append(f"サポートされていないモード: {mode}\n")
                
                # ウィンドウ横幅に合わせて表示サイズを調整
                window_width = self.node._result_window.winfo_width() if hasattr(self.node, '_result_window') else 600
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
        if hasattr(self.node, '_control_frame'):
            # 画像制御部分のみ画像データがある場合に表示
            has_image_data = any(data.headers and data.headers.get('type') == 'image' for data in self.node.flowDatas)
            
            # ヒストグラム軸制御と表示レベル制御の表示/非表示
            for child in self.node._control_frame.winfo_children():
                if hasattr(child, '_is_image_control'):
                    if has_image_data:
                        child.pack(fill=tk.X, pady=(5,0))
                    else:
                        child.pack_forget()
        

    
    def _updateDataCombo(self):
        """データ選択コンボボックスを更新"""
        if not hasattr(self.node, '_data_combo'):
            return
        
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
                if 'Model' in exif:
                    display_name += f" [{exif['Model']}]"
            
            options.append(display_name)
        
        self.node._data_combo['values'] = options
        
        # 初期選択を設定
        if options and not self.node._selected_data_var.get():
            self.node._selected_data_var.set(options[0])
    
    def _getSelectedFlowData(self):
        """選択されたフローデータを取得"""
        if not hasattr(self.node, '_selected_data_var') or not self.node.flowDatas:
            return self.node.flowDatas[0] if self.node.flowDatas else None
        
        selected = self.node._selected_data_var.get()
        if not selected:
            return self.node.flowDatas[0] if self.node.flowDatas else None
        
        # 選択されたインデックスを取得
        try:
            index = int(selected.split('データ ')[1].split(' ')[0]) - 1
            if 0 <= index < len(self.node.flowDatas):
                return self.node.flowDatas[index]
        except (ValueError, IndexError):
            pass
        
        return self.node.flowDatas[0] if self.node.flowDatas else None
    
    def _onComboKeyPress(self, event):
        """コンボボックスのキーイベント処理"""
        if event.keysym in ['Up', 'Down']:
            current_values = self.node._data_combo['values']
            if not current_values:
                return 'break'
            
            current_selection = self.node._selected_data_var.get()
            try:
                current_index = list(current_values).index(current_selection)
            except ValueError:
                current_index = 0
            
            if event.keysym == 'Up':
                new_index = (current_index - 1) % len(current_values)
            else:  # Down
                new_index = (current_index + 1) % len(current_values)
            
            self.node._selected_data_var.set(current_values[new_index])
            self._updateResultWindow()
            return 'break'  # デフォルト動作を無効化
    
    def _generateGenericContent(self, flowData, headers):
        """一般的なデータの内容を生成"""
        content = "\n"
        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        
        for planeIdx in range(min(planeCount, 3)):
            if planeCount > 1:
                content += f"\n[プレーン {planeIdx}]\n"
            
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
                
                content += "\t".join(row_data) + "\n"
        
        return content