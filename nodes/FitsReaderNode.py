'''
FitsReaderNode class

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

try:
    from astropy.io import fits
    ASTROPY_AVAILABLE = True
except ImportError:
    ASTROPY_AVAILABLE = False

class FitsReaderNode(BaseReaderNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "fits_reader", "FITS読み込み")
        self.fileTypes = [("FITS files", "*.fits *.fit *.fts")]
        
        if not ASTROPY_AVAILABLE:
            messagebox.showerror(f"{self.text} エラー", "astropyライブラリがインストールされていません。\npip install astropy でインストールしてください。")
            return
    
    def countFileBlocks(self, filePath):
        """FITSファイルのブロック数を事前計算"""
        try:
            with fits.open(filePath) as hdul:
                totalBlocks = 0
                for hdu in hdul:
                    if hdu.data is None or len(hdu.data.shape) < 2:
                        continue
                    
                    if len(hdu.data.shape) == 2:
                        height, width = hdu.data.shape
                    else:
                        height, width = hdu.data.shape[-2:]
                    
                    blocksY = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
                    blocksX = (width + BLOCK_SIZE - 1) // BLOCK_SIZE
                    totalBlocks += blocksY * blocksX
                
                return totalBlocks
        except:
            return 0
    
    def onEdit(self):
        return FitsSettingsDialog(self.editor.root, self)
    
    def processFile(self, filePath, context=None):
        """単一FITSファイルの処理"""
        if not ASTROPY_AVAILABLE:
            raise Exception("astropyライブラリがインストールされていません\npip install astropy でインストールしてください。")
        
        resultFlowDatas = []
        futureToDatas = {}
        
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
                
                # データ型に応じてdisplay_levelsを設定 - 半開区間 [min, exclusive_upper)
                if data.dtype == np.uint8:
                    display_levels = {'min': 0, 'exclusive_upper': 256}
                elif data.dtype == np.uint16:
                    display_levels = {'min': 0, 'exclusive_upper': 65536}
                elif data.dtype == np.int16:
                    display_levels = {'min': -32768, 'exclusive_upper': 32768}
                elif data.dtype == np.int32:
                    display_levels = {'min': int(data.min()), 'exclusive_upper': int(data.max()) + 1}
                elif data.dtype in [np.float32, np.float64]:
                    display_levels = {'min': float(data.min()), 'exclusive_upper': float(data.max())}
                else:
                    display_levels = {'min': float(data.min()), 'exclusive_upper': float(data.max())}
                
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
        
        # 全ブロックの処理完了を待ちながら進捗報告
        for future in as_completed(futureToDatas):
            blocks = future.result()
            for block in blocks:
                futureToDatas[future].setBlock(block)
            self.reportBlockProgress(context)
        
        return resultFlowDatas
    
    def getFileInfo(self, filePath):
        """FITSファイルの情報を取得"""
        try:
            with fits.open(filePath) as hdul:
                hdu_count = len(hdul)
                
                # 最初のデータありHDUの情報を取得
                obs_date = None
                obs_timestamp = None
                dimensions = None
                data_type = None
                
                for hdu in hdul:
                    if hdu.data is not None and len(hdu.data.shape) >= 2:
                        header = hdu.header
                        data = hdu.data
                        
                        # 観測日時を取得
                        for date_key in ['DATE-OBS', 'DATE', 'DATEOBS']:
                            if date_key in header:
                                try:
                                    obs_date_str = str(header[date_key])[:19]
                                    if 'T' in obs_date_str:
                                        dt = datetime.datetime.fromisoformat(obs_date_str.replace('T', ' '))
                                    else:
                                        dt = datetime.datetime.strptime(obs_date_str, '%Y-%m-%d')
                                    obs_timestamp = dt.timestamp()
                                    obs_date = obs_date_str
                                    break
                                except:
                                    continue
                        
                        # データ形状を取得
                        if len(data.shape) == 2:
                            dimensions = f"{data.shape[1]}x{data.shape[0]}"
                        elif len(data.shape) == 3:
                            dimensions = f"{data.shape[2]}x{data.shape[1]}x{data.shape[0]}"
                        else:
                            dimensions = 'x'.join(map(str, reversed(data.shape)))
                        data_type = str(data.dtype)
                        break
                
                return {
                    'filePath': filePath,
                    'obs_date': obs_date,
                    'obs_timestamp': obs_timestamp,
                    'hdu_count': hdu_count,
                    'dimensions': dimensions,
                    'data_type': data_type
                }
        except Exception:
            return {
                'filePath': filePath,
                'obs_date': None,
                'obs_timestamp': None,
                'hdu_count': None,
                'dimensions': None,
                'data_type': None
            }
    
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
                blockData = data[blockY:endY, blockX:endX]
            else:
                blockData = data[c, blockY:endY, blockX:endX]
            blocks.append(DataBlock(c, blockX, blockY, blockData))
        
        return blocks

class FitsSettingsDialog(BaseReaderSettingsDialog):
    def getColumns(self):
        return ('filename', 'obs_date', 'hdu_count', 'dimensions', 'data_type')
    
    def getColumnHeaders(self):
        return {
            'filename': 'ファイル名',
            'obs_date': '観測日時',
            'hdu_count': 'HDU数',
            'dimensions': '画像サイズ',
            'data_type': 'データ型'
        }
    
    def getColumnWidths(self):
        return {
            'filename': {'width': 40, 'stretch': True},
            'obs_date': {'width': 120, 'stretch': False},
            'hdu_count': {'width': 60, 'stretch': False, 'anchor': 'e'},
            'dimensions': {'width': 80, 'stretch': False, 'anchor': 'e'},
            'data_type': {'width': 60, 'stretch': False, 'anchor': 'e'}
        }
    
    def createSortButton(self, parent):
        return tk.Button(parent, text="観測日時ソート", command=self.sortByObsDate)
    
    def getFormalFileInfo(self, filePath):
        """ファイルの表示用文字列を取得"""
        fileInfo = self.node.getFileInfo(filePath)
        
        return {
            'filename': os.path.basename(filePath),
            'obs_date': fileInfo.get('obs_date', '日時不明') if fileInfo.get('obs_date') else '日時不明',
            'hdu_count': str(fileInfo.get('hdu_count', 0)) if fileInfo.get('hdu_count') is not None else '',
            'dimensions': fileInfo.get('dimensions', '') if fileInfo.get('dimensions') else '',
            'data_type': fileInfo.get('data_type', '') if fileInfo.get('data_type') else ''
        }
    
    def sortByObsDate(self):
        if len(self.selectedFilePaths) <= 1:
            return
        
        try:
            def get_obs_timestamp(filePath):
                fileInfo = self.node.getFileInfo(filePath)
                if fileInfo and fileInfo.get('obs_timestamp'):
                    return fileInfo['obs_timestamp']
                return 0  # 日時不明の場合は0を返す
            
            self.selectedFilePaths.sort(key=get_obs_timestamp)
            self.updateFileList()
        except Exception as e:
            messagebox.showerror(f"{self.node.text} エラー", f"ソートに失敗しました: {str(e)}")
    
