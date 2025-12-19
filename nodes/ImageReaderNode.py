'''
ImageReaderNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

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
from base import BaseReaderNode, FlowData, DataBlock
from base.BaseReaderNode import BaseReaderSettingsDialog
from config import BLOCK_SIZE
from utils.ThreadPool import ProcessExecutor
from utils.exif_helper import getExif

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ImageReaderNode(BaseReaderNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_reader", "画像読み込み")
        self.fileTypes = [("Image files", "*.jpg *.jpeg *.png *.bmp *.gif")]
        
        if not PIL_AVAILABLE:
            messagebox.showerror(f"{self.text} エラー", "PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
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
    
    def onEdit(self):
        return ImageSettingsDialog(self.editor.root, self)
        
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
        
        futureToDatas = {}
        # ブロック単位で並列処理
        for blockY in range(0, height, BLOCK_SIZE):
            for blockX in range(0, width, BLOCK_SIZE):
                future = ProcessExecutor.submit(self._processBlock, pixels, len(plane_names), width, height, blockX, blockY)
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
        config = f"{self.type}_{'|'.join(self.filePaths)}"
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
            dt = datetime.datetime.fromtimestamp(fileInfo['datetime'])
            datetime_str = dt.strftime("%Y-%m-%d %H:%M:%S")
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

