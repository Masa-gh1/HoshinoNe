'''
FitsReaderNode class

@author: Masakazu Inoue
'''

import hashlib
import sys
import os
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import datetime
from concurrent.futures import as_completed
from base import FlowNode, FlowData, DataBlock
from config import BLOCK_SIZE
from utils.ThreadPool import ProcessExecutor

try:
    from astropy.io import fits
    ASTROPY_AVAILABLE = True
except ImportError:
    ASTROPY_AVAILABLE = False

class FitsReaderNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "fits_reader", "FITS読み込み")
        self.filePaths = []
        
        self.fileTypes = [("FITS files", "*.fits *.fit *.fts")]
        
        if not ASTROPY_AVAILABLE:
            messagebox.showerror("エラー", "astropyライブラリがインストールされていません。\npip install astropy でインストールしてください。")
            return
    
    def getColor(self):
        return self._color_io
    
    def setFilePaths(self, filePaths):
        self.filePaths = filePaths
    
    def updateNodeText(self):
        if self.filePaths:
            if len(self.filePaths) == 1:
                fileName = os.path.basename(self.filePaths[0])
                displayText = f"FITS読み込み\n{fileName}"
            else:
                displayText = f"FITS読み込み\n{len(self.filePaths)}ファイル"
        else:
            displayText = "FITS読み込み\n未選択"
        self.editor.updateNodeText(self, displayText)
    
    def onEdit(self):
        if hasattr(self, '_settings_dialog') and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
        else:
            self._settings_dialog = FitsSettingsDialog(self.editor.root, self)
    
    def store(self, nodeData):
        flowDir = os.path.dirname(self.editor.currentFlowPath)
        relativePaths = [os.path.relpath(path, flowDir) for path in self.filePaths]
        nodeData["filePaths"] = relativePaths
    
    def restore(self, nodeData):
        if "filePaths" in nodeData:
            flowDir = os.path.dirname(self.editor.currentFlowPath)
            self.filePaths = [os.path.abspath(os.path.join(flowDir, path)) for path in nodeData["filePaths"]]
        self.updateNodeText()
    
    def process(self, context):
        if not ASTROPY_AVAILABLE:
            raise Exception("astropyライブラリがインストールされていません\npip install astropy でインストールしてください。")
        
        self.reportProgress(context, "開始")
        
        resultFlowDatas = []
        futureToDatas = {}
        
        for fileIdx, filePath in enumerate(self.filePaths):
                with fits.open(filePath) as hdul:
                    # 各HDUを個別のFlowDataとして処理
                    for hduIndex, hdu in enumerate(hdul):
                        data = hdu.data
                        header = hdu.header
                        
                        # データがないHDUはスキップ
                        if data is None:
                            continue
                        
                        # 1Dデータはスキップ（テーブルデータなど）
                        if len(data.shape) < 2:
                            continue
                    
                    # 2D/3D画像データに対応
                    if len(data.shape) == 2:
                        # グレースケール画像
                        height, width = data.shape
                        channels = 1
                        plane_names = ['L']
                        mode = 'L'
                    elif len(data.shape) == 3:
                        # カラー画像 (channels, height, width) または (height, width, channels)
                        if data.shape[0] <= 4:  # (channels, height, width)
                            channels, height, width = data.shape
                        else:  # (height, width, channels)
                            height, width, channels = data.shape
                            data = np.transpose(data, (2, 0, 1))  # (height, width, channels) -> (channels, height, width)
                        
                        if channels == 3:
                            plane_names = ['R', 'G', 'B']
                            mode = 'RGB'
                        elif channels == 4:
                            plane_names = ['R', 'G', 'B', 'A']
                            mode = 'RGBA'
                        else:
                            plane_names = [f'C{i}' for i in range(channels)]
                            mode = f'FITS_{channels}C'
                    else:
                        raise Exception(f"2D/3D画像データのみ対応しています (現在: {len(data.shape)}D)")
                    
                    # データ型に応じてdisplay_levelsを設定
                    if data.dtype == np.uint8:
                        display_levels = {'min': 0, 'max': 255}
                    elif data.dtype == np.uint16:
                        display_levels = {'min': 0, 'max': 65535}
                    elif data.dtype == np.int16:
                        display_levels = {'min': -32768, 'max': 32767}
                    elif data.dtype == np.int32:
                        display_levels = {'min': int(data.min()), 'max': int(data.max())}
                    elif data.dtype in [np.float32, np.float64]:
                        display_levels = {'min': float(data.min()), 'max': float(data.max())}
                    else:
                        display_levels = {'min': float(data.min()), 'max': float(data.max())}
                    
                    # FITSヘッダー情報を抽出
                    fits_header = {}
                    for key, value in header.items():
                        if key and value is not None:
                            fits_header[key] = str(value)
                    
                    # 観測日時を取得
                    obs_date = None
                    for date_key in ['DATE-OBS', 'DATE', 'DATEOBS']:
                        if date_key in header:
                            try:
                                obs_date = str(header[date_key])
                                break
                            except:
                                continue
                    
                    headers = {
                        'type': 'image',
                        'mode': mode,
                        'planes': plane_names,
                        'display_levels': display_levels,
                        'source_file': filePath,
                        'hdu_index': hduIndex,
                        'data_type': str(data.dtype),
                        'channels': channels,
                        'fits_header': fits_header,
                    }
                    
                    if obs_date:
                        headers['obs_date'] = obs_date
                    
                    flowData = FlowData(headers)
                    flowData.setDimensions(width, height)
                    resultFlowDatas.append(flowData)
                    
                # ブロック単位で並列処理
                for blockY in range(0, height, BLOCK_SIZE):
                    for blockX in range(0, width, BLOCK_SIZE):
                        future = ProcessExecutor.submit(self._processBlock, data, channels, width, height, blockX, blockY)
                        futureToDatas[future] = flowData
        
        # 全ブロックの処理完了を待つ
        self.reportProgress(context, "処理中")
        totalBlocks = len(futureToDatas)
        for i, future in enumerate(as_completed(futureToDatas)):
            blocks = future.result()
            for block in blocks:
                futureToDatas[future].setBlock(block)
            self.reportProgress(context, "処理中", i + 1, totalBlocks)
        
        self.flowDatas = resultFlowDatas
        
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        config = f"{self.type}_{"|".join(self.filePaths)}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def _processBlock(self, data, channels, width, height, blockX, blockY):
        """FITSデータブロックの処理"""
        endY = min(blockY + BLOCK_SIZE, height)
        endX = min(blockX + BLOCK_SIZE, width)
        
        blocks = []
        for c in range(channels):
            if channels == 1:
                blockData = data[blockY:endY, blockX:endX].astype(np.float64)
            else:
                blockData = data[c, blockY:endY, blockX:endX].astype(np.float64)
            blocks.append(DataBlock(c, blockX, blockY, blockData))
        
        return blocks

class FitsSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        
        self.title("FITS読み込み設定")
        self.geometry("500x700")
        
        # メインフレーム
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(mainFrame, text="ファイル:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        # ファイルリスト表示用スクロールエリア
        fileListFrame = tk.Frame(mainFrame)
        fileListFrame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Treeviewで列表示
        columns = ('obs_date', 'hdu_count', 'dimensions', 'data_type')
        self.fileTreeview = ttk.Treeview(fileListFrame, columns=columns, show='tree headings', height=10)
        
        # 列ヘッダー設定
        self.fileTreeview.heading('#0', text='ファイル名')
        self.fileTreeview.heading('obs_date', text='観測日時')
        self.fileTreeview.heading('hdu_count', text='HDU数')
        self.fileTreeview.heading('dimensions', text='画像サイズ')
        self.fileTreeview.heading('data_type', text='データ型')
        
        # 列幅設定（ファイル名のみストレッチ）
        self.fileTreeview.column('#0', width=200, stretch=True)
        self.fileTreeview.column('obs_date', width=150, stretch=False)
        self.fileTreeview.column('hdu_count', width=60, stretch=False)
        self.fileTreeview.column('dimensions', width=100, stretch=False)
        self.fileTreeview.column('data_type', width=80, stretch=False)
        
        fileScrollbar = ttk.Scrollbar(fileListFrame, orient=tk.VERTICAL, command=self.fileTreeview.yview)
        self.fileTreeview.configure(yscrollcommand=fileScrollbar.set)
        
        self.fileTreeview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fileScrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ファイル操作ボタン
        buttonFrame = tk.Frame(mainFrame)
        buttonFrame.pack(anchor="w", pady=5)
        
        tk.Button(buttonFrame, text="追加", command=self.addFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="削除", command=self.removeFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="観測日時ソート", command=self.sortByObsDate).pack(side=tk.LEFT)
        
        # ファイルリストを更新
        self.updateFileList()
        
        # ボタン
        bottomButtonFrame = tk.Frame(self)
        bottomButtonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(bottomButtonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(bottomButtonFrame, text="閉じる", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def updateFileList(self):
        # 既存項目をクリア
        for item in self.fileTreeview.get_children():
            self.fileTreeview.delete(item)
        
        filePaths = getattr(self, 'selectedFilePaths', None) or self.node.filePaths
        if filePaths:
            for filePath in filePaths:
                fileName = os.path.basename(filePath)
                
                # FITS情報を取得して表示
                info = self._getFitsInfo(filePath)
                if info:
                    obs_date = info.get('obs_date', '日時不明')
                    hdu_count = info.get('hdu_count', 0)
                    dimensions = info.get('dimensions', '')
                    data_type = info.get('data_type', '')
                    
                    self.fileTreeview.insert('', 'end', text=fileName, values=(obs_date, hdu_count, dimensions, data_type))
                else:
                    self.fileTreeview.insert('', 'end', text=fileName, values=('情報取得失敗', '', '', ''))
        else:
            self.fileTreeview.insert('', 'end', text='未選択', values=('', '', '', ''))
    
    def addFiles(self):
        filePaths = filedialog.askopenfilenames(parent=self, title="FITSファイルを追加", filetypes=self.node.fileTypes)
        
        if filePaths:
            if not hasattr(self, 'selectedFilePaths'):
                self.selectedFilePaths = list(self.node.filePaths) if self.node.filePaths else []
            
            for filePath in filePaths:
                if filePath not in self.selectedFilePaths:
                    self.selectedFilePaths.append(filePath)
            
            self.updateFileList()
    
    def removeFiles(self):
        selected_items = self.fileTreeview.selection()
        if not selected_items:
            return
        
        if not hasattr(self, 'selectedFilePaths'):
            self.selectedFilePaths = list(self.node.filePaths) if self.node.filePaths else []
        
        # 選択されたアイテムのインデックスを取得
        indices_to_remove = []
        for item in selected_items:
            index = self.fileTreeview.index(item)
            indices_to_remove.append(index)
        
        # 逆順で削除
        for index in sorted(indices_to_remove, reverse=True):
            if 0 <= index < len(self.selectedFilePaths):
                del self.selectedFilePaths[index]
        
        self.updateFileList()
    
    def sortByObsDate(self):
        if not hasattr(self, 'selectedFilePaths'):
            self.selectedFilePaths = list(self.node.filePaths) if self.node.filePaths else []
        
        if len(self.selectedFilePaths) <= 1:
            return
        
        try:
            def get_obs_timestamp(filePath):
                info = self._getFitsInfo(filePath)
                if info and 'obs_timestamp' in info:
                    return info['obs_timestamp']
                return 0  # 日時不明の場合は0を返す
            
            self.selectedFilePaths.sort(key=get_obs_timestamp)
            self.updateFileList()
        except Exception as e:
            messagebox.showerror("エラー", f"ソートに失敗しました: {str(e)}")
    
    def _getFitsInfo(self, filePath):
        """指定されたFITSファイルの情報を取得"""
        try:
            with fits.open(filePath) as hdul:
                hdu_count = len(hdul)
                
                # 最初のデータありHDUの情報を取得
                obs_date = '日時不明'
                obs_timestamp = 0
                dimensions = 'データなし'
                data_type = ''
                
                for hdu in hdul:
                    if hdu.data is not None and len(hdu.data.shape) >= 2:
                        header = hdu.header
                        data = hdu.data
                        
                        # 観測日時を取得
                        for date_key in ['DATE-OBS', 'DATE', 'DATEOBS']:
                            if date_key in header:
                                try:
                                    obs_date = str(header[date_key])[:19]
                                    import datetime
                                    if 'T' in obs_date:
                                        dt = datetime.datetime.fromisoformat(obs_date.replace('T', ' '))
                                    else:
                                        dt = datetime.datetime.strptime(obs_date, '%Y-%m-%d')
                                    obs_timestamp = dt.timestamp()
                                    break
                                except:
                                    continue
                        
                        # データ形状と型を取得
                        if len(data.shape) == 2:
                            dimensions = f"{data.shape[1]}x{data.shape[0]}"
                        elif len(data.shape) == 3:
                            dimensions = f"{data.shape[2]}x{data.shape[1]}x{data.shape[0]}"
                        else:
                            dimensions = 'x'.join(map(str, reversed(data.shape)))
                        data_type = str(data.dtype)
                        break
                
                return {
                    'obs_date': obs_date,
                    'obs_timestamp': obs_timestamp,
                    'hdu_count': hdu_count,
                    'dimensions': dimensions,
                    'data_type': data_type
                }
        except Exception:
            return None
    
    def onApply(self):
        if hasattr(self, 'selectedFilePaths'):
            self.node.filePaths = self.selectedFilePaths
        
        self.node.updateNodeText()
        
        newHash = self.node.getConfigHash()
        if newHash != self.node._lastConfigHash:
            self.node.editor.onNodeConfigChanged(self.node)
    
    def onClose(self):
        if hasattr(self.node, '_settings_dialog'):
            delattr(self.node, '_settings_dialog')
        self.destroy()