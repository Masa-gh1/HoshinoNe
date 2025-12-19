'''
RawReaderNode class

@author: Masakazu Inoue

ref
https://campkougaku.com/2019/11/25/rawpy1/
https://letmaik.github.io/rawpy/api/index.html
https://www.libraw.org/docs/API-datastruct.html
'''

import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
from base import FlowNode, FlowData, DataBlock
from config import BLOCK_SIZE
from config import configRawParams

try:
    import rawpy
    RAWPY_AVAILABLE = True
except ImportError:
    RAWPY_AVAILABLE = False

class RawReaderNode(FlowNode):
    def __init__(self, canvas, editor, x, y, nonDialog=False, **kwargs):
        super().__init__(canvas, editor, x, y, "raw_reader", "RAW読み込み")
        self.filePaths = []
        self.fileTypes=[
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
        return 'lightcoral'
    
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
            raise Exception("rawpyライブラリがインストールされていません")
        
        if not self.filePaths:
            raise Exception("RAWファイルが選択されていません")
        
        self.reportProgress(context, "RAWファイル読み込み中")
        
        self.flowDatas = []
        
        self.reportProgress(context, "RAW現像中")
        for fileIndex, filePath in enumerate(self.filePaths):
            try:
                with rawpy.imread(filePath) as raw:
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
                    elif self.demosaicAlgorithm == "VNG":
                        params.demosaic_algorithm = rawpy.DemosaicAlgorithm.VNG
                    elif self.demosaicAlgorithm == "PPG":
                        params.demosaic_algorithm = rawpy.DemosaicAlgorithm.PPG
                    elif self.demosaicAlgorithm == "AAHD":
                        params.demosaic_algorithm = rawpy.DemosaicAlgorithm.AAHD
                    
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
                    
                    # RAW現像実行
                    rgb = raw.postprocess(params)
                    
                    # RGB画像をFlowDataに変換
                    height, width, channels = rgb.shape
                    
                    # 元RAWファイルのbit深度を使用してdisplay_levelsを設定
                    black_level = min(raw.black_level_per_channel) if raw.black_level_per_channel else 0
                    white_level = raw.white_level
                    display_levels = {'min': black_level, 'max': white_level}
                    
                    # plane名を動的に設定
                    if self.demosaicAlgorithm == "raw" and channels == 4:
                        plane_names = ['R', 'G1', 'B', 'G2']
                        mode = 'RGGB'
                    else:
                        plane_names = ['R', 'G', 'B'][:channels]
                        mode = 'RGB'
                    
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
                        'white_balance': self.whiteBalance
                    }
                    
                    outputFlowData = FlowData(headers)
                    outputFlowData.setDimensions(width, height)
                    
                    # RGB各チャンネルをBLOCK_SIZEで分割してDataBlockとして設定
                    for c in range(channels):
                        channelData = rgb[:, :, c].astype(np.float64)
                        
                        # BLOCK_SIZEで分割して処理
                        for y in range(0, height, BLOCK_SIZE):
                            for x in range(0, width, BLOCK_SIZE):
                                endY = min(y + BLOCK_SIZE, height)
                                endX = min(x + BLOCK_SIZE, width)
                                
                                blockData = channelData[y:endY, x:endX].tolist()
                                block = DataBlock(c, x, y, blockData)
                                outputFlowData.setBlock(block)
                    
                    self.flowDatas.append(outputFlowData)
                
            except Exception as e:
                raise Exception(f"RAWファイル処理エラー ({filePath}): {str(e)}")
            
            self.reportProgress(context, "RAW現像中", fileIndex + 1, len(self.filePaths))
        
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        filePathsStr = "|".join(self.filePaths)
        config = f"{self.type}_{filePathsStr}_{self.demosaicAlgorithm}_{self.outputColorspace}_{self.whiteBalance}_{self.gammaPower}_{self.gammaSlope}"
        return hashlib.md5(config.encode()).hexdigest()

class RawSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        
        self.title("RAW読み込み設定")
        self.geometry("600x600")
        
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
        
        self.fileListbox = tk.Listbox(fileListFrame, height=15)
        fileScrollbar = tk.Scrollbar(fileListFrame, orient=tk.VERTICAL, command=self.fileListbox.yview)
        self.fileListbox.configure(yscrollcommand=fileScrollbar.set)
        
        self.fileListbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fileScrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ファイルリストを更新
        self.updateFileList()
        
        tk.Button(leftFrame, text="ファイル選択", command=self.selectFiles).pack(anchor="w", pady=5)
        
        # 右側：設定項目
        rightFrame = tk.Frame(mainFrame)
        rightFrame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # デモザイクアルゴリズム
        demosaicFrame = tk.Frame(rightFrame)
        demosaicFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(demosaicFrame, text="ベイヤー変換アルゴリズム:").pack(anchor="w")
        self.demosaicVar = tk.StringVar()
        algoOptions = ["none - ベイヤー変換せずに2x2を1ピクセルにする", 
                       "raw - ベイヤー変換せずに2x2を4プレーンにする(Greenが2枚)", 
                       "AHD - 適応的同質性指向アルゴリズム。高品質だが処理時間が長い", 
                       "VNG - 可変勾配数アルゴリズム。バランスの取れた品質と速度", 
                       "PPG - パターン化ピクセルグループ化。高速だが品質は劣る", 
                       "AAHD - 適応的AHD。AHDの改良版"]
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
        self.fileListbox.delete(0, tk.END)
        filePaths = getattr(self, 'selectedFilePaths', None) or self.node.filePaths
        if filePaths:
            for filePath in filePaths:
                fileName = filePath.split('/')[-1].split('\\')[-1]
                self.fileListbox.insert(tk.END, fileName)
        else:
            self.fileListbox.insert(tk.END, "未選択")
    
    def selectFiles(self):
        filePaths = filedialog.askopenfilenames( parent=self, title="RAWファイルを選択", filetypes=self.node.fileTypes)
        
        if filePaths:
            self.selectedFilePaths = list(filePaths)
            self.updateFileList()
    
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
    
    def onClose(self):
        if hasattr(self.node, '_settings_dialog'):
            delattr(self.node, '_settings_dialog')
        self.destroy()