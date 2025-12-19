'''
RawReaderNode class

@author: Masakazu Inoue

ref
https://campkougaku.com/2019/11/25/rawpy1/
https://letmaik.github.io/rawpy/api/index.html
https://www.libraw.org/docs/API-datastruct.html
'''

import hashlib
import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import datetime
from concurrent.futures import as_completed
from base import FlowNode, FlowData, DataBlock
from config import BLOCK_SIZE
from utils.ThreadPool import ProcessExecutor
from config import configRawParams
from utils.exif_helper import get_exif

try:
    import rawpy
    RAWPY_AVAILABLE = True
except ImportError:
    RAWPY_AVAILABLE = False

class RawReaderNode(FlowNode):
    def __init__(self, canvas, editor, x, y, nonDialog=False, **kwargs):
        super().__init__(canvas, editor, x, y, "raw_reader", "RAW読み込み")
        self.filePaths = []
        
        self.fileTypes = [
                ("RAW files", "*.cr2 *.cr3 *.nef *.arw *.dng *.raf *.orf *.rw2 *.pef *.srw *.x3f"),
                ("Canon RAW", "*.cr2 *.cr3"),
                ("Nikon RAW", "*.nef"),
                ("Sony RAW", "*.arw"),
                ("Adobe DNG", "*.dng"),
                ("Fujifilm RAW", "*.raf"),
                ("Olympus RAW", "*.orf"),
                ("Panasonic RAW", "*.rw2"),
                ("Pentax RAW", "*.pef"),
                ("Samsung RAW", "*.srw"),
                ("Sigma RAW", "*.x3f"),
                ("All files", "*.*")
            ]
        self.demosaicAlgorithm = "none"  # none, raw, AHD, VNG, PPG, AAHD
        self.outputColorspace = "raw"  # raw, sRGB, Adobe RGB, Wide Gamut RGB, ProPhoto RGB
        self.whiteBalance = "daylight"  # camera, auto, daylight, cloudy, shade, tungsten, fluorescent, flash
        self.gammaPower = 1.0  # gamma power
        self.gammaSlope = 1.0  # gamma slope
        
        if not RAWPY_AVAILABLE:
            messagebox.showerror("エラー", "rawpyライブラリがインストールされていません。\npip install rawpy でインストールしてください。")
            return
        
    def getColor(self):
        return self._color_io
    
    def setFilePaths(self, filePaths):
        self.filePaths = filePaths
    
    def updateNodeText(self):
        if self.filePaths:
            if len(self.filePaths) == 1:
                fileName = self.filePaths[0].split('/')[-1].split('\\')[-1]
                displayText = f"RAW読み込み\n{fileName}\n{self.demosaicAlgorithm}"
            else:
                displayText = f"RAW読み込み\n{len(self.filePaths)}ファイル\n{self.demosaicAlgorithm}"
        else:
            displayText = "RAW読み込み\n未選択"
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        nodeData["filePaths"] = self.filePaths
        nodeData["demosaicAlgorithm"] = self.demosaicAlgorithm
        nodeData["outputColorspace"] = self.outputColorspace
        nodeData["whiteBalance"] = self.whiteBalance
        nodeData["gammaPower"] = self.gammaPower
        nodeData["gammaSlope"] = self.gammaSlope
    
    def restore(self, nodeData):
        if "filePaths" in nodeData:
            self.filePaths = nodeData["filePaths"]
        if "demosaicAlgorithm" in nodeData:
            self.demosaicAlgorithm = nodeData["demosaicAlgorithm"]
        if "outputColorspace" in nodeData:
            self.outputColorspace = nodeData["outputColorspace"]
        if "whiteBalance" in nodeData:
            self.whiteBalance = nodeData["whiteBalance"]
        if "gammaPower" in nodeData:
            self.gammaPower = nodeData["gammaPower"]
        if "gammaSlope" in nodeData:
            self.gammaSlope = nodeData["gammaSlope"]
        self.updateNodeText()
    
    def onEdit(self):
        if hasattr(self, '_settings_dialog') and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
        else:
            self._settings_dialog = RawSettingsDialog(self.editor.root, self)
    
    def process(self, context):
        if not RAWPY_AVAILABLE:
            raise Exception("rawpyライブラリがインストールされていません\npip install rawpy でインストールしてください。")
        
        self.reportProgress(context, "開始")
        
        # RAW現像パラメータ設定
        params = rawpy.Params()
        
        configRawParams(params)
        
        # デモザイクアルゴリズム
        if self.demosaicAlgorithm == "none":
            params.half_size          = True
            params.four_color_rgb     = False
        elif self.demosaicAlgorithm == "raw":
            params.half_size          = True
            params.four_color_rgb     = True
        elif self.demosaicAlgorithm == "AHD":
            params.demosaic_algorithm = rawpy.DemosaicAlgorithm.AHD
        elif self.demosaicAlgorithm == "AAHD":
            params.demosaic_algorithm = rawpy.DemosaicAlgorithm.AAHD
        elif self.demosaicAlgorithm == "VNG":
            params.demosaic_algorithm = rawpy.DemosaicAlgorithm.VNG
        elif self.demosaicAlgorithm == "PPG":
            params.demosaic_algorithm = rawpy.DemosaicAlgorithm.PPG
        
        # 出力色空間
        if self.outputColorspace == "raw":
            params.output_color = rawpy.ColorSpace.raw.value
        elif self.outputColorspace == "sRGB":
            params.output_color = rawpy.ColorSpace.sRGB.value
        elif self.outputColorspace == "Adobe RGB":
            params.output_color = rawpy.ColorSpace.Adobe.value
        elif self.outputColorspace == "Wide Gamut RGB":
            params.output_color = rawpy.ColorSpace.Wide.value
        elif self.outputColorspace == "ProPhoto RGB":
            params.output_color = rawpy.ColorSpace.ProPhoto.value
        
        # ホワイトバランス
        if self.whiteBalance == "auto":
            params.use_auto_wb = True
        elif self.whiteBalance == "camera":
            params.use_camera_wb = True
        elif self.whiteBalance == "daylight":
            params.user_wb = [1.0, 1.0, 1.0, 1.0]  # 昼光の近似値
        elif self.whiteBalance == "cloudy":
            params.user_wb = [1.2, 1.0, 0.8, 1.0]  # 曇天の近似値
        elif self.whiteBalance == "shade":
            params.user_wb = [1.4, 1.0, 0.7, 1.0]  # 日陰の近似値
        elif self.whiteBalance == "tungsten":
            params.user_wb = [0.6, 1.0, 1.8, 1.0]  # タングステンの近似値
        elif self.whiteBalance == "fluorescent":
            params.user_wb = [0.8, 1.0, 1.4, 1.0]  # 蛍光灯の近似値
        elif self.whiteBalance == "flash":
            params.user_wb = [1.0, 1.0, 1.0, 1.0]  # フラッシュの近似値

        # ガンマ設定
        params.gamm = (float(self.gammaPower), float(self.gammaSlope))
        
        resultFlowDatas = []
        
        self.reportProgress(context, "RAW現像中")
        for fileIndex, filePath in enumerate(self.filePaths):
            
            # EXIF情報を取得
            exif_info = self._getExif(filePath)
            
            # DateTimeを文字列化
            headers_exif = None
            if exif_info:
                headers_exif = dict(exif_info)
                if 'DateTime' in headers_exif:
                    dt = datetime.datetime.fromtimestamp(headers_exif['DateTime'])
                    headers_exif['DateTime'] = dt.strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                with rawpy.imread(filePath) as raw:
                    # RAW現像実行
                    rgb = raw.postprocess(params)
                    
                    # RGB画像をFlowDataに変換
                    height, width, channels = rgb.shape
                    
                    # mode と plane_names を動的に設定
                    if self.demosaicAlgorithm == "raw" and channels == 4:
                        mode = 'RGGB'
                        plane_names = ['R', 'G1', 'B', 'G2']
                    else:
                        mode = 'RGB'
                        plane_names = ['R', 'G', 'B'][:channels]
                    
                    # 元RAWファイルのbit深度を使用してdisplay_levelsを設定
                    black_level = min(raw.black_level_per_channel) if raw.black_level_per_channel else 0
                    white_level = raw.white_level
                    display_levels = {'min': black_level, 'max': white_level}
                    
                    headers = {
                        'type': 'image',
                        'mode': mode,
                        'width': width,
                        'height': height,
                        'channels': channels,
                        'planes': plane_names,
                        'display_levels': display_levels,
                        'source_file': filePath,
                        'demosaic': self.demosaicAlgorithm,
                        'colorspace': self.outputColorspace,
                        'white_balance': self.whiteBalance,
                    }
                    if headers_exif:
                        headers['exif'] = headers_exif
                    
                    outputFlowData = FlowData(headers)
                    outputFlowData.setDimensions(width, height)
                    
                    # RGB各チャンネルをBLOCK_SIZEで分割してDataBlockとして設定
                    futures = []
                    
                    # ブロック単位で並列処理
                    for c in range(channels):
                        channelData = rgb[:, :, c].astype(np.float64)
                        
                        for y in range(0, height, BLOCK_SIZE):
                            for x in range(0, width, BLOCK_SIZE):
                                future = ProcessExecutor.submit(self._processBlock, channelData, c, x, y, height, width)
                                futures.append(future)
                    
                    # 全ブロックの処理完了を待つ
                    for future in as_completed(futures):
                        block = future.result()
                        if block:
                            outputFlowData.setBlock(block)
                    
                    resultFlowDatas.append(outputFlowData)
            except Exception as e:
                raise Exception(f"RAWファイル処理エラー ({filePath}): {str(e)}")
            
            self.reportProgress(context, "RAW現像中", fileIndex + 1, len(self.filePaths))
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def _processBlock(self, channelData, c, x, y, height, width):
        """単一ブロックの処理"""
        endY = min(y + BLOCK_SIZE, height)
        endX = min(x + BLOCK_SIZE, width)
        
        blockData = channelData[y:endY, x:endX].tolist()
        return DataBlock(c, x, y, blockData)
    
    def getConfigHash(self):
        config = f"{self.type}_{"|".join(self.filePaths)}_{self.demosaicAlgorithm}_{self.outputColorspace}_{self.whiteBalance}_{self.gammaPower}_{self.gammaSlope}"
        return hashlib.md5(config.encode()).hexdigest()

    def _getExif(self, filepath):
        """EXIFデータを取得"""
        return get_exif(filepath)
    
class RawSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        
        self.title("RAW読み込み設定")
        self.geometry("700x600")
        
        # メインフレーム（左右分割）
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左側：ファイル名表示
        leftFrame = tk.Frame(mainFrame)
        leftFrame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        tk.Label(leftFrame, text="ファイル:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        # ファイルリスト表示用スクロールエリア
        fileListFrame = tk.Frame(leftFrame)
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
        buttonFrame = tk.Frame(leftFrame)
        buttonFrame.pack(anchor="w", pady=5)
        
        tk.Button(buttonFrame, text="追加", command=self.addFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="削除", command=self.removeFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="撮影時刻ソート", command=self.sortByTimestamp).pack(side=tk.LEFT)
        
        # 右側：設定項目
        rightFrame = tk.Frame(mainFrame)
        rightFrame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # デモザイクアルゴリズム
        demosaicFrame = tk.Frame(rightFrame)
        demosaicFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(demosaicFrame, text="ベイヤー変換アルゴリズム:").pack(anchor="w")
        self.demosaicVar = tk.StringVar()
        algoOptions = ["none - ベイヤー変換せずに2x2を1ピクセルにする(Greenを平均)",
                       "raw - ベイヤー変換せずに2x2を4プレーンにする(Greenが2枚)", 
                       "AHD - 適応的同質性指向アルゴリズム。高品質だが処理時間が長い", 
                       "AAHD - 適応的AHD。AHDの改良版",
                       "VNG - 可変勾配数アルゴリズム。バランスの取れた品質と速度",
                       "PPG - パターン化ピクセルグループ化。高速だが品質は劣る",
                      ]
        # 現在の値に対応する選択肢を設定
        for option in algoOptions:
            if option.startswith(node.demosaicAlgorithm):
                self.demosaicVar.set(option)
                break
        self.demosaicCombo = ttk.Combobox(demosaicFrame, textvariable=self.demosaicVar, values=algoOptions, state="readonly")
        self.demosaicCombo.pack(fill=tk.X, pady=2)
        
        # 出力色空間
        colorspaceFrame = tk.Frame(rightFrame)
        colorspaceFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(colorspaceFrame, text="出力色空間:").pack(anchor="w")
        self.colorspaceVar = tk.StringVar()
        csOptions = ["raw - 変換しない", 
                     "sRGB - 標準的なモニター用色空間。最も一般的", 
                     "Adobe RGB - より幅広い色域を持つ印刷用色空間", 
                     "Wide Gamut RGB - さらに幅広い色域を持つ色空間", 
                     "ProPhoto RGB - 最も幅広い色域を持つプロ用色空間"]
        # 現在の値に対応する選択肢を設定
        for option in csOptions:
            if option.startswith(node.outputColorspace):
                self.colorspaceVar.set(option)
                break
        self.colorspaceCombo = ttk.Combobox(colorspaceFrame, textvariable=self.colorspaceVar, values=csOptions, state="readonly")
        self.colorspaceCombo.pack(fill=tk.X, pady=2)
        
        # ホワイトバランス
        wbFrame = tk.Frame(rightFrame)
        wbFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(wbFrame, text="ホワイトバランス:").pack(anchor="w")
        self.wbVar = tk.StringVar()
        wbOptions = ["camera - カメラが記録した設定を使用", 
                     "auto - 自動ホワイトバランス", 
                     "daylight - 昼光（5500K) (1.0, 1.0, 1.0）", 
                     "cloudy - 曇天（6500K) (1.2, 1.0, 0.8）", 
                     "shade - 日陰（7500K) (1.4, 1.0, 0.7）", 
                     "tungsten - タングステン電球（3200K) (0.6, 1.0, 1.8）", 
                     "fluorescent - 蛍光灯（4000K) (0.8, 1.0, 1.4）", 
                     "flash - フラッシュ（5500K) (1.0, 1.0, 1.0）"]
        # 現在の値に対応する選択肢を設定
        for option in wbOptions:
            if option.startswith(node.whiteBalance):
                self.wbVar.set(option)
                break
        self.wbCombo = ttk.Combobox(wbFrame, textvariable=self.wbVar, values=wbOptions, state="readonly")
        self.wbCombo.pack(fill=tk.X, pady=2)

        # ガンマ
        gammaFrame = tk.Frame(rightFrame)
        gammaFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(gammaFrame, text="ガンマパワー:").pack(anchor="w")
        tk.Label(gammaFrame, text="ガンマパワー値を指定 (0.0〜3.0, デフォルト:1.0, BT.709:0.45, sRGB:0.42)", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.gammaPowerVar = tk.DoubleVar(value=node.gammaPower)
        tk.Scale(gammaFrame, from_=0.0, to=3.0, resolution=0.01, orient=tk.HORIZONTAL, variable=self.gammaPowerVar).pack(fill=tk.X)
        
        tk.Label(gammaFrame, text="ガンマスロープ:").pack(anchor="w", pady=(10,0))
        tk.Label(gammaFrame, text="ガンマスロープ値を指定 (0.0〜20.0, デフォルト:1.0, BT.709:4.5, sRGB:12.9)", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.gammaSlopeVar = tk.DoubleVar(value=node.gammaSlope)
        tk.Scale(gammaFrame, from_=1.0, to=20.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.gammaSlopeVar).pack(fill=tk.X)
        
        # ボタン
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def updateFileList(self):
        # 既存項目をクリア
        for item in self.fileTreeview.get_children():
            self.fileTreeview.delete(item)
        
        filePaths = getattr(self, 'selectedFilePaths', None) or self.node.filePaths
        if filePaths:
            for filePath in filePaths:
                fileName = os.path.basename(filePath)
                
                # RAW情報を取得
                info = self._getRawInfo(filePath)
                datetime_str = info.get('datetime', '時刻不明')
                size_str = info.get('size', '')
                exposure_str = info.get('exposure', '')
                fnumber_str = info.get('fnumber', '')
                iso_str = info.get('iso', '')
                
                self.fileTreeview.insert('', 'end', text=fileName, values=(datetime_str, size_str, exposure_str, fnumber_str, iso_str))
        else:
            self.fileTreeview.insert('', 'end', text='未選択', values=('', '', '', '', ''))
    
    def addFiles(self):
        filePaths = filedialog.askopenfilenames(parent=self, title="RAWファイルを追加", filetypes=self.node.fileTypes)
        
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
        
        self.node.demosaicAlgorithm = self.demosaicVar.get().split(' - ')[0]
        self.node.outputColorspace = self.colorspaceVar.get().split(' - ')[0]
        self.node.whiteBalance = self.wbVar.get().split(' - ')[0]
        self.node.gammaPower = self.gammaPowerVar.get()
        self.node.gammaSlope = self.gammaSlopeVar.get()
        
        self.node.updateNodeText()
        
        newHash = self.node.getConfigHash()
        if newHash != self.node._lastConfigHash:
            self.node.editor.onNodeConfigChanged(self.node)
    
    def _getRawInfo(self, filePath):
        """指定されたRAWファイルの情報を取得"""
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
