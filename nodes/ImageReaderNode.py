'''
ImageReaderNode class

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
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from utils.exif_helper import get_exif

class ImageReaderNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_reader", "画像読み込み")
        self.filePaths = []

        
        self.fileTypes = [("Image files", "*.jpg *.jpeg *.png *.bmp *.gif")]
        
        if not PIL_AVAILABLE:
            messagebox.showerror("PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
            return
    
    def getColor(self):
        return self._color_io
    
    def setFilePaths(self, filePaths):
        self.filePaths = filePaths
    
    def updateNodeText(self):
        if self.filePaths:
            if len(self.filePaths) == 1:
                fileName = os.path.basename(self.filePaths[0])
                displayText = f"画像読み込み\n{fileName}"
            else:
                displayText = f"画像読み込み\n{len(self.filePaths)}ファイル"
        else:
            displayText = "画像読み込み\n未選択"
        self.editor.updateNodeText(self, displayText)
    
    def onEdit(self):
        if hasattr(self, '_settings_dialog') and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
        else:
            self._settings_dialog = ImageSettingsDialog(self.editor.root, self)
    
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
        if not PIL_AVAILABLE:
            raise Exception("PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
        
        self.reportProgress(context, "開始")
        
        resultFlowDatas = []
        futureToDatas = {}
        
        for fileIdx, filePath in enumerate(self.filePaths):
            img = Image.open(filePath)
            width, height = img.size
            
            # plane_names を動的に設定
            if   'RGB'   == img.mode: plane_names = ['R', 'G', 'B']
            elif 'RGBA'  == img.mode: plane_names = ['R', 'G', 'B', 'A']
            elif 'L'     == img.mode: plane_names = ['L']
            elif 'LA'    == img.mode: plane_names = ['L', 'A']
            elif 'P'     == img.mode: plane_names = ['Index']
            elif 'CMYK'  == img.mode: plane_names = ['C', 'M', 'Y', 'K']
            elif 'YCbCr' == img.mode: plane_names = ['Y', 'Cb', 'Cr']
            elif 'HSV'   == img.mode: plane_names = ['H', 'S', 'V']
            elif 'LAB'   == img.mode: plane_names = ['L', 'A', 'B']
            elif 'I;16'  == img.mode: plane_names = ['L']
            elif 'I;16B' == img.mode: plane_names = ['L']
            elif 'I'     == img.mode: plane_names = ['L']
            elif 'F'     == img.mode: plane_names = ['L']
            else                    : plane_names = [f'{img.mode}_{i}' for i in range(len(img.getbands()))]
            
            # bit深度を検出してdisplay_levelsを設定
            if   img.mode in ['L', 'LA', 'RGB', 'RGBA', 'P', 'CMYK', 'YCbCr', 'HSV', 'LAB']: 
                                                display_levels = {'min': 0,   'max':        255}  # 8bit
            elif img.mode in ['I;16', 'I;16B']: display_levels = {'min': 0,   'max':      65535}  # 16bit
            elif 'F' == img.mode              : display_levels = {'min': 0.0, 'max':        1.0}  # 浮動小数点
            elif 'I' == img.mode              : display_levels = {'min': 0,   'max': 2147483647}  # 32bit int
            else                              : display_levels = {'min': 0,   'max':        255}  # デフォルト
            
            # EXIF情報を取得
            exif_info = self._getExif(filePath)
            
            # DateTimeを文字列化
            headers_exif = None
            if exif_info:
                headers_exif = dict(exif_info)
                if 'DateTime' in headers_exif:
                    dt = datetime.datetime.fromtimestamp(headers_exif['DateTime'])
                    headers_exif['DateTime'] = dt.strftime("%Y-%m-%d %H:%M:%S")
            
            headers = {
                'type': 'image',
                'mode': img.mode,
                'planes': plane_names,
                'display_levels': display_levels,
            }
            if headers_exif:
                headers['exif'] = headers_exif
            
            pixels = list(img.getdata())
            flowData = FlowData(headers)
            flowData.setDimensions(width, height)
            resultFlowDatas.append(flowData)
            
            # ブロック単位で並列処理
            for blockY in range(0, height, BLOCK_SIZE):
                for blockX in range(0, width, BLOCK_SIZE):
                    future = ProcessExecutor.submit(self._processBlock, pixels, len(plane_names), width, height, blockX, blockY)
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
    
    def _processBlock(self, pixels, planeCount, width, height, blockX, blockY):
        """プレーン毎ブロックの処理"""
        endY = min(blockY + BLOCK_SIZE, height)
        endX = min(blockX + BLOCK_SIZE, width)
        
        blockWidth = endX - blockX
        blockHeight = endY - blockY
        
        # 各プレーンのブロックをnumpy配列で作成
        blocks = []
        for planeIdx in range(planeCount):
            plane_block = np.zeros((blockHeight, blockWidth), dtype=np.float64)
            blocks.append(plane_block)
        
        for y in range(blockHeight):
            for x in range(blockWidth):
                pixelIdx = (blockY + y) * width + (blockX + x)
                pixel = pixels[pixelIdx]
                
                if planeCount == 1:
                    # グレースケールなど単一値の処理
                    blocks[0][y, x] = float(pixel)
                else:
                    for planeIdx in range(planeCount):
                        blocks[planeIdx][y, x] = float(pixel[planeIdx])
        
        # 各プレーンのブロック情報を返す
        dataBlocks = []
        for planeIdx, block in enumerate(blocks):
            dataBlocks.append(DataBlock(planeIdx, blockX, blockY, block))
        return dataBlocks
    
    def _getExif(self, filepath):
        """EXIFデータを取得"""
        return get_exif(filepath)

class ImageSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        
        self.title("画像読み込み設定")
        self.geometry("400x600")
        
        # メインフレーム
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(mainFrame, text="ファイル:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        # ファイルリスト表示用スクロールエリア
        fileListFrame = tk.Frame(mainFrame)
        fileListFrame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Treeviewで列表示
        columns = ('datetime', 'size', 'exposure', 'fnumber', 'iso')
        self.fileTreeview = ttk.Treeview(fileListFrame, columns=columns, show='tree headings', height=15)
        
        # 列ヘッダー設定
        self.fileTreeview.heading('#0', text='ファイル名')
        self.fileTreeview.heading('datetime', text='撮影日時')
        self.fileTreeview.heading('size', text='画像サイズ')
        self.fileTreeview.heading('exposure', text='露出')
        self.fileTreeview.heading('fnumber', text='F値')
        self.fileTreeview.heading('iso', text='ISO')
        
        # 列幅設定（ファイル名のみストレッチ）
        self.fileTreeview.column('#0', width=200, stretch=True)
        self.fileTreeview.column('datetime', width=150, stretch=False)
        self.fileTreeview.column('size', width=100, stretch=False, anchor='e')
        self.fileTreeview.column('exposure', width=80, stretch=False, anchor='e')
        self.fileTreeview.column('fnumber', width=60, stretch=False, anchor='e')
        self.fileTreeview.column('iso', width=60, stretch=False, anchor='e')
        
        fileScrollbar = ttk.Scrollbar(fileListFrame, orient=tk.VERTICAL, command=self.fileTreeview.yview)
        self.fileTreeview.configure(yscrollcommand=fileScrollbar.set)
        
        self.fileTreeview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fileScrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ファイルリストを更新
        self.updateFileList()
        
        # ファイル操作ボタン
        buttonFrame = tk.Frame(mainFrame)
        buttonFrame.pack(anchor="w", pady=5)
        
        tk.Button(buttonFrame, text="追加", command=self.addFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="削除", command=self.removeFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="撮影時刻ソート", command=self.sortByTimestamp).pack(side=tk.LEFT)
        
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
                
                # 画像情報を取得
                info = self._getImageInfo(filePath)
                datetime_str = info.get('datetime', '時刻不明')
                size_str = info.get('size', '')
                exposure_str = info.get('exposure', '')
                fnumber_str = info.get('fnumber', '')
                iso_str = info.get('iso', '')
                
                self.fileTreeview.insert('', 'end', text=fileName, values=(datetime_str, size_str, exposure_str, fnumber_str, iso_str))
        else:
            self.fileTreeview.insert('', 'end', text='未選択', values=('', '', '', '', ''))
    
    def addFiles(self):
        filePaths = filedialog.askopenfilenames(parent=self, title="画像ファイルを追加", filetypes=self.node.fileTypes)
        
        if filePaths:
            if not hasattr(self, 'selectedFilePaths'):
                self.selectedFilePaths = list(self.node.filePaths) if self.node.filePaths else []
            
            # 重複を除いて追加
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
    
    def sortByTimestamp(self):
        
        if not hasattr(self, 'selectedFilePaths'):
            self.selectedFilePaths = list(self.node.filePaths) if self.node.filePaths else []
        
        if len(self.selectedFilePaths) <= 1:
            return
        
        try:
            self.selectedFilePaths.sort(key=lambda x: self.node._getExif(x)["DateTime"] if self.node._getExif(x) and "DateTime" in self.node._getExif(x) else 0)
            self.updateFileList()
        except Exception as e:
            messagebox.showerror("エラー", f"ソートに失敗しました: {str(e)}")
    
    def onApply(self):
        # ファイルパスの更新
        if hasattr(self, 'selectedFilePaths'):
            self.node.filePaths = self.selectedFilePaths
        
        self.node.updateNodeText()
        
        newHash = self.node.getConfigHash()
        if newHash != self.node._lastConfigHash:
            self.node.editor.onNodeConfigChanged(self.node)
    
    def _getImageInfo(self, filePath):
        """指定された画像ファイルの情報を取得"""
        try:
            # EXIF情報を取得
            exif = self.node._getExif(filePath)
            
            # 撮影日時
            if exif and "DateTime" in exif:
                dt = datetime.datetime.fromtimestamp(exif["DateTime"])
                datetime_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                datetime_str = '時刻不明'
            
            # 画像サイズ（EXIFから取得）
            size_str = ''
            if exif:
                width = exif.get('ImageWidth')
                height = exif.get('ImageLength')
                if width and height:
                    size_str = f"{width}x{height}"
            
            # 露出時間
            exposure_str = ''
            if exif and 'ExposureTime' in exif:
                exposure = exif['ExposureTime']
                if exposure >= 1:
                    exposure_str = f"{exposure:.1f}"
                else:
                    # 1秒未満の場合は分数表示
                    exposure_str = f"1/{int(1/exposure)}"
            
            # F値
            fnumber_str = ''
            if exif and 'FNumber' in exif:
                fnumber = exif['FNumber']
                if fnumber >= 1:
                    fnumber_str = f"{fnumber:.1f}"
                else:
                    fnumber_str = f"{fnumber:.2f}"
            
            # ISO感度
            iso_str = ''
            if exif and 'ISOSpeedRatings' in exif:
                iso_str = f"{exif['ISOSpeedRatings']}"
            
            return {
                'datetime': datetime_str,
                'size': size_str,
                'exposure': exposure_str,
                'fnumber': fnumber_str,
                'iso': iso_str
            }
        except Exception:
            return {
                'datetime': '情報取得失敗',
                'size': '',
                'exposure': '',
                'fnumber': '',
                'iso': ''
            }
    
    def onClose(self):
        if hasattr(self.node, '_settings_dialog'):
            delattr(self.node, '_settings_dialog')
        self.destroy()
