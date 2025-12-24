'''
RawReaderNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue

ref
https://campkougaku.com/2019/11/25/rawpy1/
https://letmaik.github.io/rawpy/api/index.html
https://www.libraw.org/docs/API-datastruct.html
'''

import hashlib
import datetime
import os
from concurrent.futures import as_completed
import tkinter as tk
from tkinter import messagebox, ttk

from nodes import BaseReaderSettingsDialog
from nodes import BaseReaderNode

class RawReaderNode(BaseReaderNode):
    # ノードタイプ
    #majorType = スーパークラスを継承
    minorType = 'raw_reader'
    # ノード名
    name      = 'RAW読み込み'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
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
        self.demosaicAlgorithm = "unpack"  # bayer, bayer crop, unpack, raw, ...
        self.outputColorspace = "raw"  # raw, sRGB, Adobe RGB, Wide Gamut RGB, ProPhoto RGB
        self.whiteBalance = "daylight"  # camera, auto, daylight, cloudy, shade, tungsten, fluorescent, flash
        self.gammaPower = 1.0  # gamma power
        self.gammaSlope = 1.0  # gamma slope

        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("rawpy"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ rawpy がインストールされていません。\npip install rawpy でインストールしてください。")
            return
        
    def getText(self):
        """ノードのテキストを取得"""
        if self.filePaths:
            if len(self.filePaths) == 1:
                displayText = f"{self.name}\n{os.path.basename(self.filePaths[0])}\nproc: {self.demosaicAlgorithm}"
            else:
                dirname = os.path.dirname(self.filePaths[0])
                displayText = f"{self.name}\n{os.path.basename(dirname)} ... 計{len(self.filePaths)}\nproc: {self.demosaicAlgorithm}"
        else:
            displayText = "{self.name}\n未選択"
        return displayText
    
    def store(self, nodeData):
        super().store(nodeData)
        nodeData["demosaicAlgorithm"] = self.demosaicAlgorithm
        nodeData["outputColorspace"] = self.outputColorspace
        nodeData["whiteBalance"] = self.whiteBalance
        nodeData["gammaPower"] = self.gammaPower
        nodeData["gammaSlope"] = self.gammaSlope
    
    def restore(self, nodeData):
        super().restore(nodeData)
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
    
    def countFileBlocks(self, filePath):
        """RAWファイルのブロック数を事前計算"""
        import rawpy
        from config import BLOCK_SIZE
        
        try:
            with rawpy.imread(filePath) as raw:
                height, width = raw.sizes.raw_height, raw.sizes.raw_width
                # デモザイクアルゴリズムによってサイズが変わる
                if self.demosaicAlgorithm in ["unpack", "raw"]:
                    height //= 2
                    width //= 2
                
                blocksY = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
                blocksX = (width + BLOCK_SIZE - 1) // BLOCK_SIZE
                
                # チャンネル数を考慮
                if self.demosaicAlgorithm == "bayer":
                    planeCount = 1
                elif self.demosaicAlgorithm == "unpack":
                    planeCount = 4
                else:
                    planeCount = 3
                return blocksY * blocksX * planeCount
        except:
            return 1
    
    def createSettingWindow(self):
        return RawSettingsDialog(self.view.editor.root, self)
    
    def processFile(self, filePath, context=None):
        """単一RAWファイルの処理"""
        import rawpy
        from config import RAW_DEMOSAIC_ALGORITHMS
        from config import configRawParams
        from utils import exif_helper as exif
        from utils.ThreadPool import ProcessExecutorInNode
        from config import BLOCK_SIZE
        from base import FlowData
        
        # RAW現像パラメータ設定
        params = rawpy.Params()
        configRawParams(params)
        
        # デモザイクアルゴリズム
        if   self.demosaicAlgorithm in "bayer":
            pass
        elif self.demosaicAlgorithm in "bayer crop":
            pass
        elif self.demosaicAlgorithm == "unpack":
            params.half_size          = True
            params.four_color_rgb     = True
        elif self.demosaicAlgorithm == "raw":
            params.half_size          = True
            params.four_color_rgb     = False
        elif self.demosaicAlgorithm in RAW_DEMOSAIC_ALGORITHMS:
            params.demosaic_algorithm = getattr(rawpy.DemosaicAlgorithm,self.demosaicAlgorithm)
        else:
            # デフォルト
            self.demosaicAlgorithm    = "unpack"
            params.half_size          = True
            params.four_color_rgb     = True

        
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
        else:
            # デフォルト
            self.outputColorspace = "raw"
            params.output_color = rawpy.ColorSpace.raw.value
        
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
        else:
            # デフォルト
            self.whiteBalance = "daylight"
            params.user_wb = [1.0, 1.0, 1.0, 1.0]  # 昼光の近似値

        # ガンマ設定
        params.gamm = (float(self.gammaPower), float(self.gammaSlope))
        
        with rawpy.imread(filePath) as raw:
            # ベイヤーパターン情報を取得
            raw_pattern = raw.raw_pattern
            color_desc = raw.color_desc
            if raw_pattern is None or color_desc is None:
                bayer_pattern = "<unkown>"
            else:
                colorDesc = color_desc.decode('ascii')
                bayer_pattern = ""
                for x in raw_pattern.flatten():
                    bayer_pattern += colorDesc[x]
            
            # raw情報を構築(raw.postprocess 後だと値が変化物がある)
            raw_headers = {
                'raw_pattern'                   : raw_pattern.tolist(),
                'color_desc'                    : color_desc.decode('ascii'),
                'bayer_pattern'                 : bayer_pattern,
                'crop_left_margin'              : raw.sizes.crop_left_margin,
                'crop_top_margin'               : raw.sizes.crop_top_margin,
                'crop_width'                    : raw.sizes.crop_width,
                'crop_height'                   : raw.sizes.crop_height,
                'raw_height'                    : raw.sizes.raw_height,
                'raw_width'                     : raw.sizes.raw_width,
                'black_level_per_channel'       : raw.black_level_per_channel,
                'white_level'                   : raw.white_level,
                'camera_white_level_per_channel': raw.camera_white_level_per_channel,
                'camera_whitebalance'           : raw.camera_whitebalance,
            }

            # 元RAWファイルのbit深度を使用してdisplay_levelsを設定
            black_level = min(raw.black_level_per_channel) if raw.black_level_per_channel else 0
            white_level = raw.white_level
            # 半開区間 [black_level, white_level) で量子化範囲を設定
            display_levels = {'min': black_level, 'exclusive_upper': white_level}
            
            # ベイヤー配列の生データを取得
            if self.demosaicAlgorithm == "bayer":
                # ベイヤー配列のまま1プレーンで取得
                bayer_data = raw.raw_image
                height, width = bayer_data.shape
                planeCount = 1
                mode = 'BAYER'
                plane_names = ['Bayer']
                rgb = bayer_data.reshape(height, width, 1)  # 3次元配列に変換
            elif self.demosaicAlgorithm == "bayer crop":
                # ベイヤー配列のまま1プレーンで取得(クロップ)
                bayer_data = raw.raw_image_visible
                height, width = bayer_data.shape
                planeCount = 1
                mode = 'BAYER'
                plane_names = ['Bayer']
                rgb = bayer_data.reshape(height, width, 1)  # 3次元配列に変換
            else:
                # RAW 後処理
                rgb = raw.postprocess(params)
                height, width, planeCount = rgb.shape
                bayer_pattern = None
                
                # mode と plane_names を動的に設定
                if self.demosaicAlgorithm == "unpack" and planeCount == 4:
                    mode = 'RGBG'
                    plane_names = ['R', 'G1', 'B', 'G2']
                else:
                    mode = 'RGB'
                    plane_names = ['R', 'G', 'B'][:planeCount]
            
            # EXIF情報を取得
            exif_info = exif.getExif(filePath)
            
            # DateTimeを文字列化
            headers_exif = None
            orgDateTime = None
            if exif_info:
                headers_exif = dict(exif_info)
                for tag in ['DateTime', 'DateTimeDigitized', 'DateTimeOriginal']:
                    if tag in headers_exif:
                        orgDateTime = exif.toDatetime(headers_exif[tag])
                        orgDateTime = orgDateTime.strftime("%Y-%m-%d %H:%M:%S") if orgDateTime else None
                
                if not 'DateTimeOriginal'  in headers_exif:
                    headers_exif['DateTimeOriginal'] = orgDateTime
                if not 'DateTimeDigitized' in headers_exif:
                    headers_exif['DateTimeDigitized'] = orgDateTime
            
            headers = {
                'type': 'image',
                'mode': mode,
                'width': width,
                'height': height,
                'planes': plane_names,
                'datetime': orgDateTime,
                'display_levels': display_levels,
                'source_file': self.getRelativePath(filePath),
                'demosaic': self.demosaicAlgorithm,
                'colorspace': self.outputColorspace,
                'white_balance': self.whiteBalance,
            }
            
            # bayer 情報を追加
            if bayer_pattern:
                headers['bayer_pattern'] = bayer_pattern
                headers['is_bayer'] = True
            
            # raw 情報追加
            headers['raw'] = raw_headers
            
            # EXIF 追加
            if headers_exif:
                headers['exif'] = headers_exif
            
            outputFlowData = FlowData(headers)
            outputFlowData.setDimensions(width, height)
            
            # RGB各チャンネルをBLOCK_SIZEで分割してDataBlockとして設定
            futures = []
            
            # ブロック単位で並列処理
            for planeIndex in range(planeCount):
                channelData = rgb[:, :, planeIndex]
                
                for y in range(0, height, BLOCK_SIZE):
                    for x in range(0, width, BLOCK_SIZE):
                        future = ProcessExecutorInNode .submit(self, self._processBlock, channelData, planeIndex, x, y, height, width)
                        futures.append(future)
            
            # 全ブロックの処理完了を待ちながら進捗報告
            for future in as_completed(futures):
                block = future.result()
                if block:
                    outputFlowData.setBlock(block)
                self.reportBlockProgress(context)
            
            return outputFlowData
    
    def _processBlock(self, channelData, planeIndex, x, y, height, width):
        """単一ブロックの処理"""
        from config import BLOCK_SIZE
        from base import DataBlock
        
        endY = min(y + BLOCK_SIZE, height)
        endX = min(x + BLOCK_SIZE, width)
        
        blockData = channelData[y:endY, x:endX]
        return DataBlock(blockData, planeIndex, x, y)
    
    def getFileInfo(self, filePath):
        """RAWファイルの情報を取得（生データ）"""
        from utils import exif_helper as exif

        try:
            exif = exif.getExif(filePath)
            return {
                'filePath': filePath,
                'datetime': exif.get('DateTime') if exif else None,
                'width': exif.get('ImageWidth') if exif else None,
                'height': exif.get('ImageLength') if exif else None,
                'exposure': exif.get('ExposureTime') if exif else None,
                'fnumber': exif.get('FNumber') if exif else None,
                'iso': exif.get('ISOSpeedRatings') if exif else None
            }
        except Exception:
            return {
                'filePath': filePath,
                'datetime': None,
                'width': None,
                'height': None,
                'exposure': None,
                'fnumber': None,
                'iso': None
            }
    
    def getConfigHash(self):
        config = f"{self.minorType}_{"|".join(self.filePaths)}_{self.demosaicAlgorithm}_{self.outputColorspace}_{self.whiteBalance}_{self.gammaPower}_{self.gammaSlope}"
        return hashlib.md5(config.encode()).hexdigest()
    
class RawSettingsDialog(BaseReaderSettingsDialog):
    def __init__(self, parent, node):
        super().__init__(parent, node)
        self.geometry("700x500")
    
    def getColumns(self):
        return ('filename', 'datetime', 'size', 'exposure', 'fnumber', 'iso')
    
    def getColumnHeaders(self):
        return {
            'filename': 'ファイル名',
            'datetime': '撮影日時',
            'size': '画像サイズ',
            'exposure': '露出',
            'fnumber': 'F値',
            'iso': 'ISO'
        }
    
    def getColumnWidths(self):
        return {
            'filename': {'width': 40, 'stretch': True},
            'datetime': {'width': 120, 'stretch': False},
            'size': {'width': 80, 'stretch': False, 'anchor': 'e'},
            'exposure': {'width': 40, 'stretch': False, 'anchor': 'e'},
            'fnumber': {'width': 40, 'stretch': False, 'anchor': 'e'},
            'iso': {'width': 40, 'stretch': False, 'anchor': 'e'}
        }
    
    def createSortButton(self, parent):
        return tk.Button(parent, text="撮影時刻ソート", command=self.sortByTimestamp)
    
    def createCustomSettings(self, parent):
        from config import RAW_DEMOSAIC_ALGORITHMS
        
        if not parent:
            return tk.Frame()  # テスト用ダミー
        
        customFrame = tk.Frame(parent)
        
        # デモザイクアルゴリズム
        demosaicFrame = tk.Frame(customFrame)
        demosaicFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(demosaicFrame, text="ベイヤー変換アルゴリズム:").pack(anchor="w")
        self.demosaicVar = tk.StringVar()
        algoOptions = ["bayer - ベイヤー配列の生データを1プレーンで取得(以下の後処理設定も無効)",
                       "bayer crop - ベイヤー配列の生データを1プレーンで取得(クロップのみ実施)",
                       "unpack - ベイヤー変換せずに2x2を4プレーンにする(Greenが2枚)",
                       "raw - ベイヤー変換せずに2x2を1ピクセルにする(Greenを平均)",
                      ]
        for name,text in RAW_DEMOSAIC_ALGORITHMS.items():
            algoOptions.append(f"{name} - {text}")
        
        # 現在の値に対応する選択肢を設定
        for option in algoOptions:
            if option.startswith(self.node.demosaicAlgorithm):
                self.demosaicVar.set(option)
                break
        self.demosaicCombo = ttk.Combobox(demosaicFrame, textvariable=self.demosaicVar, values=algoOptions, state="readonly")
        self.demosaicCombo.pack(fill=tk.X, pady=2)
        
        # 出力色空間
        colorspaceFrame = tk.Frame(customFrame)
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
            if option.startswith(self.node.outputColorspace):
                self.colorspaceVar.set(option)
                break
        self.colorspaceCombo = ttk.Combobox(colorspaceFrame, textvariable=self.colorspaceVar, values=csOptions, state="readonly")
        self.colorspaceCombo.pack(fill=tk.X, pady=2)
        
        # ホワイトバランス
        wbFrame = tk.Frame(customFrame)
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
            if option.startswith(self.node.whiteBalance):
                self.wbVar.set(option)
                break
        self.wbCombo = ttk.Combobox(wbFrame, textvariable=self.wbVar, values=wbOptions, state="readonly")
        self.wbCombo.pack(fill=tk.X, pady=2)

        # ガンマ
        gammaFrame = tk.Frame(customFrame)
        gammaFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(gammaFrame, text="ガンマパワー:").pack(anchor="w")
        tk.Label(gammaFrame, text="ガンマパワー値を指定 (0.0〜3.0, デフォルト:1.0, BT.709:0.45, sRGB:0.42)", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.gammaPowerVar = tk.DoubleVar(value=self.node.gammaPower)
        tk.Scale(gammaFrame, from_=0.0, to=3.0, resolution=0.01, orient=tk.HORIZONTAL, variable=self.gammaPowerVar).pack(fill=tk.X)
        
        tk.Label(gammaFrame, text="ガンマスロープ:").pack(anchor="w", pady=(10,0))
        tk.Label(gammaFrame, text="ガンマスロープ値を指定 (0.0〜20.0, デフォルト:1.0, BT.709:4.5, sRGB:12.9)", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.gammaSlopeVar = tk.DoubleVar(value=self.node.gammaSlope)
        tk.Scale(gammaFrame, from_=1.0, to=20.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.gammaSlopeVar).pack(fill=tk.X)
        
        return customFrame
    
    def customOnApply(self):
        """カスタム設定の適用"""
        self.node.demosaicAlgorithm = self.demosaicVar.get().split(' - ')[0]
        self.node.outputColorspace = self.colorspaceVar.get().split(' - ')[0]
        self.node.whiteBalance = self.wbVar.get().split(' - ')[0]
        self.node.gammaPower = self.gammaPowerVar.get()
        self.node.gammaSlope = self.gammaSlopeVar.get()
    
    def getFormalFileInfo(self, filePath):
        """ファイルの表示用文字列を取得"""
        fileInfo = self.node.getFileInfo(filePath)
        
        # 撮影日時
        if fileInfo.get('datetime'):
            datetime_str = fileInfo['datetime']
        else:
            datetime_str = '時刻不明'
        
        # 画像サイズ
        width = fileInfo.get('width')
        height = fileInfo.get('height')
        if width and height:
            size_str = f"{width}x{height}"
        else:
            size_str = ''
        
        # 露出時間
        exposure = fileInfo.get('exposure')
        if exposure:
            if exposure >= 1:
                exposure_str = f"{exposure:.1f}"
            else:
                exposure_str = f"1/{int(1/exposure)}"
        else:
            exposure_str = ''
        
        # F値
        fnumber = fileInfo.get('fnumber')
        if fnumber:
            if fnumber >= 1:
                fnumber_str = f"{fnumber:.1f}"
            else:
                fnumber_str = f"{fnumber:.2f}"
        else:
            fnumber_str = ''
        
        # ISO感度
        iso = fileInfo.get('iso')
        iso_str = f"{iso}" if iso else ''
        
        return {
            'filename': os.path.basename(filePath),
            'datetime': datetime_str,
            'size': size_str,
            'exposure': exposure_str,
            'fnumber': fnumber_str,
            'iso': iso_str
        }
    
    def sortByTimestamp(self):
        if len(self.selectedFilePaths) <= 1:
            return
        
        try:
            def get_timestamp(filePath):
                fileInfo = self.node.getFileInfo(filePath)
                if fileInfo and fileInfo.get('datetime'):
                    dt = datetime.datetime.fromisoformat(fileInfo['datetime'])
                    return dt.timestamp()
                return 0
            
            self.selectedFilePaths.sort(key=get_timestamp)
            self.updateFileList()
        except Exception as e:
            messagebox.showerror(f"{self.node.name} エラー", f"ソートに失敗しました: {str(e)}")
