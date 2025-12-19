'''
ImageReaderNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
import hashlib
import datetime
import os
from concurrent.futures import as_completed
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import BLOCK_SIZE
from base import FlowData, DataBlock
from nodes import BaseReaderSettingsDialog
from nodes import BaseReaderNode
from utils import numpy_helpers as nh
from utils.ThreadPool import ProcessExecutorInNode 
from utils.exif_helper import getExif

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ImageReaderNode(BaseReaderNode):
    # ノードタイプ
    #majorType = スーパークラスを継承
    minorType = 'image_reader'
    # ノード名
    name      = '画像読み込み'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

        self.fileTypes = [("Image files", "*.jpg *.jpeg *.png *.bmp *.gif")]
        
        if not PIL_AVAILABLE:
            messagebox.showerror(f"{self.name} エラー", "PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
            return
    
    def countFileBlocks(self, filePath):
        """画像ファイルのブロック数を事前計算"""
        try:
            img = Image.open(filePath)
            width, height = img.size
            img.close()
            
            blocksY = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
            blocksX = (width + BLOCK_SIZE - 1) // BLOCK_SIZE
            return blocksY * blocksX
        except:
            return 0
    
    def createSettingWindow(self):
        return ImageSettingsDialog(self.view.editor.root, self)
        
    def processFile(self, filePath, context=None):
        if not PIL_AVAILABLE:
            raise Exception("PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
        
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
        
        # bit深度を検出してdisplay_levelsを設定 - 半開区間 [min, exclusive_upper)
        if   img.mode in ['L', 'LA', 'RGB', 'RGBA', 'P', 'CMYK', 'YCbCr', 'HSV', 'LAB']:
                                            display_levels = {'min': 0,   'exclusive_upper':        256}  # 8bit
        elif img.mode in ['I;16', 'I;16B']: display_levels = {'min': 0,   'exclusive_upper':      65536}  # 16bit
        elif 'F' == img.mode              : display_levels = {'min': 0.0, 'exclusive_upper':        1.0}  # 浮動小数点
        elif 'I' == img.mode              : display_levels = {'min': 0,   'exclusive_upper': 2147483648}  # 32bit int
        else                              : display_levels = {'min': 0,   'exclusive_upper':        256}  # デフォルト
        
        # EXIF情報を取得
        exif_info = getExif(filePath)
        
        # DateTimeを文字列化
        headers_exif = None
        orgDateTime = None
        if exif_info:
            headers_exif = dict(exif_info)
            for tag in ['DateTime', 'DateTimeDigitized', 'DateTimeOriginal']:
                if tag in headers_exif:
                    orgDateTime = headers_exif[tag]
        
        headers = {
            'type': 'image',
            'mode': img.mode,
            'width': width,
            'height': height,
            'planes': plane_names,
            'datetime': orgDateTime,
            'display_levels': display_levels,
            'source_file': self.getRelativePath(filePath),
        }

        # EXIF 追加
        if headers_exif:
            headers['exif'] = headers_exif
        
        pixels = list(img.getdata())
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)
        
        futureToDatas = {}
        # ブロック単位で並列処理
        for y in range(0, height, BLOCK_SIZE):
            for x in range(0, width, BLOCK_SIZE):
                future = ProcessExecutorInNode .submit(self, self._processBlock, pixels, x, y, len(plane_names), width, height)
                futureToDatas[future] = flowData

        # 全ブロックの処理完了を待ちながら進捗報告
        for future in as_completed(futureToDatas):
            blocks = future.result()
            for block in blocks:
                flowData.setBlock(block)
            self.reportBlockProgress(context)
        
        return flowData
    
    def getFileInfo(self, filePath):
        """画像ファイルの情報を取得（生データ）"""
        try:
            exif = getExif(filePath)
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
        config = f"{self.minorType}_{'|'.join(self.filePaths)}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def _processBlock(self, pixels, x, y, planeCount, width, height):
        """プレーン毎ブロックの処理"""
        endY = min(y + BLOCK_SIZE, height)
        endX = min(x + BLOCK_SIZE, width)
        blockWidth = endX - x
        blockHeight = endY - y
        
        # 各プレーンのブロックをnumpy配列で作成
        blocks = []
        for planeIdx in range(planeCount):
            plane_block = nh.nans((blockHeight, blockWidth))
            blocks.append(plane_block)
        
        if 1 == planeCount:
            # グレースケールなど単一値の処理
            for dy in range(blockHeight):
                for dx in range(blockWidth):
                    pixelIdx = (y + dy) * width + (x + dx)
                    pixel = pixels[pixelIdx]
                    blocks[0][dy, dx] = float(pixel)
        else:
            for dy in range(blockHeight):
                for dx in range(blockWidth):
                    pixelIdx = (y + dy) * width + (x + dx)
                    pixel = pixels[pixelIdx]
                    for planeIdx in range(planeCount):
                        blocks[planeIdx][dy, dx] = float(pixel[planeIdx])
        
        # 各プレーンのブロック情報を返す
        dataBlocks = []
        for planeIdx, block in enumerate(blocks):
            dataBlocks.append(DataBlock(block, planeIdx, x, y))
        return dataBlocks
    
class ImageSettingsDialog(BaseReaderSettingsDialog):
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
            'filename': os.path.basename(fileInfo.get('filePath', filePath)),
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
