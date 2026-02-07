'''
FitsReaderNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from fractions import Fraction
import hashlib
import datetime
import os
from concurrent.futures import as_completed
import tkinter as tk
from tkinter import messagebox, ttk

from nodes import BaseReaderSettingsDialog
from nodes import BaseReaderNode

class FitsReaderNode(BaseReaderNode):
    # ノードタイプ
    #majorType = スーパークラスを継承
    minorType = 'fits_reader'
    # ノード名
    name      = 'FITS読み込み'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

        self.fileTypes = [("FITS files", "*.fits *.fit *.fts")]
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("astropy"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ astropy がインストールされていません。\npip install astropy でインストールしてください。")
            return
    
    def countFileBlocks(self, filePath):
        """FITSファイルのブロック数を事前計算"""
        from astropy.io import fits
        from config import BLOCK_SIZE
        
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
    
    def createSettingWindow(self):
        return FitsSettingsDialog(self.view.editor.root, self)
    
    def processFile(self, filePath, context=None):
        """単一FITSファイルの処理"""
        import numpy as np
        from astropy.io import fits
        from config import BLOCK_SIZE
        from utils.interval_helper import createHalfOpenEnd
        from utils.ThreadPool import ParallelExecutor
        from base import FlowData
        
        resultFlowDatas = []
        futureToDatas = {}
        
        with fits.open(filePath) as hdul:
            # 各HDUを個別のFlowDataとして処理
            for hduIndex, hdu in enumerate(hdul):
                data = hdu.data
                hduHeader = hdu.header
                
                # データがないHDUはスキップ
                if data is None:
                    continue
                
                # 1Dデータはスキップ（テーブルデータなど）
                if len(data.shape) < 2:
                    continue
            
                # ベイヤー配列の判別
                bayer_pattern = None
                
                # FITSヘッダーからベイヤー情報を取得
                if 'BAYERPAT' in hduHeader:
                    bayer_pattern = str(hduHeader['BAYERPAT']).upper()
                elif 'COLORTYP' in hduHeader:
                    colortyp = str(hduHeader['COLORTYP']).upper()
                    if colortyp in ['RGGB', 'GRBG', 'GBRG', 'BGGR']:
                        bayer_pattern = colortyp
                    elif 'BAYER' in colortyp:
                        # ベイヤーパターンを推定
                        if 'PATTERN' in hduHeader:
                            bayer_pattern = str(hduHeader['PATTERN']).upper()
                        elif 'CFATYPE' in hduHeader:
                            bayer_pattern = str(hduHeader['CFATYPE']).upper()
                        elif 'XBAYROFF' in hduHeader and 'YBAYROFF' in hduHeader:
                            x_off = int(hduHeader['XBAYROFF'])
                            y_off = int(hduHeader['YBAYROFF'])
                            patterns = {(0,0): 'RGGB', (1,0): 'GRBG', (0,1): 'GBRG', (1,1): 'BGGR'}
                            bayer_pattern = patterns.get((x_off, y_off), 'RGGB')
                        else:
                            bayer_pattern = 'RGGB'  # デフォルト
                
                # 2D/3D画像データに対応
                if len(data.shape) == 2:
                    height, width = data.shape
                    planeCount = 1
                    
                    if bayer_pattern:
                        # ベイヤー配列データ
                        plane_names = ['Bayer']
                        mode = 'BAYER'
                    else:
                        # モノクロ画像
                        plane_names = ['L']
                        mode = 'L'
                elif len(data.shape) == 3:
                    # カラー画像 (channels, height, width) または (height, width, channels)
                    if data.shape[0] <= 4:  # (channels, height, width)
                        planeCount, height, width = data.shape
                    else:  # (height, width, channels)
                        height, width, planeCount = data.shape
                        data = np.transpose(data, (2, 0, 1))  # (height, width, channels) -> (channels, height, width)
                    
                    if planeCount == 3:
                        plane_names = ['R', 'G', 'B']
                        mode = 'RGB'
                    elif planeCount == 4:
                        plane_names = ['R', 'G', 'B', 'A']
                        mode = 'RGBA'
                    else:
                        plane_names = [f'C{i}' for i in range(planeCount)]
                        mode = f'FITS_{planeCount}C'
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
                    display_levels = {'min': int(np.nanmin(data)), 'exclusive_upper': int(createHalfOpenEnd(np.nanmin(data),np.nanmax(data)))}
                elif data.dtype in [np.float32, np.float64]:
                    display_levels = {'min': float(np.nanmin(data)), 'exclusive_upper': float(createHalfOpenEnd(np.nanmin(data),np.nanmax(data)))}
                else:
                    display_levels = {'min': float(np.nanmin(data)), 'exclusive_upper': float(createHalfOpenEnd(np.nanmin(data),np.nanmax(data)))}
                
                # FITSヘッダー情報を抽出
                fits_header = {}
                for key, value in hduHeader.items():
                    if key and value is not None:
                        fits_header[key] = str(value)

                # 観測日時を取得
                date_obs = None
                dateTime = '    :  :     :  :  '
                subsec   = ''
                for date_key in ['DATE-OBS', 'DATEOBS', 'DATE']:
                    if date_key in hduHeader:
                        try:
                            obs_date_str = str(hduHeader[date_key])
                            dt = datetime.datetime.fromisoformat(obs_date_str)
                            date_obs = dt.strftime('%Y-%m-%d %H:%M:%S.%f')
                            dateTime = dt.strftime('%Y:%m:%d %H:%M:%S')
                            subsec   = obs_date_str[obs_date_str.index('.')+1:] if '.' in obs_date_str else ''
                            break
                        except:
                            continue
                
                headers = {
                    'type'          : 'image',
                    'mode'          : mode,
                    'width'         : width,
                    'height'        : height,
                    'planes'        : plane_names,
                    'datetime'      : date_obs,
                    'display_levels': display_levels,
                    'source_file'   : self.getRelativePath(filePath),
                    'context_index' : hduIndex,
                }

                # bayer 情報を追加
                if bayer_pattern:
                    headers['bayer_pattern'] = bayer_pattern
                    headers['is_bayer'] = True
                
                # FITS 情報追加
                headers['fits'] = fits_header

                # EXIF 追加
                headers['exif'] = {
                    'ImageWidth'               : int(         hduHeader.get('NAXIS1'  ,  0)             ), #   256 0100h 画像の幅
                    'ImageLength'              : int(         hduHeader.get('NAXIS2'  ,  0)             ), #   257 0101h 画像の高さ
                    'BitsPerSample'            : int(         hduHeader.get('BITPIX'  ,  0)             ), #   258 0102h 画像のビットの深さ
                    'Make'                     : str(         hduHeader.get('ORIGIN'  , '')             ), #   271 010Fh 画像入力機器のメーカ名
                    'Model'                    : str(         hduHeader.get('TELESCOP', '')             ), #   272 0110h 画像入力機器のモデル名
                   #'Orientation'              : int(                                                   ), #   274 0112h 画像方向
                    'XResolution'              : Fraction(                                     72,     1), #   282 011Ah 画像の幅の解像度
                    'YResolution'              : Fraction(                                     72,     1), #   283 011Bh 画像の高さの解像度
                    'ResolutionUnit'           : 2                                                       , #   296 0128h 画像の幅と高さの解像度の単位
                    'DateTime'                 : dateTime                                                , #   306 0132h ファイル変更日時
                   #'Artist'                   : str(                                                   ), #   315 013Bh アーティスト
                   #'Copyright'                : str(                                                   ), # 33432 8298h 撮影著作権者/編集著作権者
                    'ExposureTime'             : Fraction(int(hduHeader.get('EXPTIME' ,  0)*1000),  1000), # 33434 829Ah 露出時間
                   #'FNumber'                  : Fraction(                                              ), # 33437 829Dh F ナンバー
                   #'PhotographicSensitivity'  : int(                                                   ), # 34855 8827h 撮影感度
                   #'SensitivityType'          : int(                                                   ), # 34864 8830h 感度種別
                   #'StandardOutputSensitivity': int(                                                   ), # 34865 8831h 標準出力感度
                   #'RecommendedExposureIndex' : int(                                                   ), # 34866 8832h 推奨露光指数
                   #'ISOSpeed'                 : int(                                                   ), # 34867 8833h ISO スピード
                    'DateTimeOriginal'         : dateTime                                                , # 36867 9003h 原画像データの生成日時
                    'DateTimeDigitized'        : dateTime                                                , # 36868 9004h デジタルデータの作成日時
                    'FocalLength'              : Fraction(int(hduHeader.get('FOCALLEN',  0))             ,     1), # 37386 920Ah レンズ焦点距離
                    'SubSecTime'               : subsec                                                  , # 37520 9290h DateTime のサブセック
                    'SubSecTimeOriginal'       : subsec                                                  , # 37521 9291h DateTimeOriginal のサブセック
                    'SubSecTimeDigitized'      : subsec                                                  , # 37522 9292h DateTimeDigitized のサブセック
                    'PixelXDimension'          : int(         hduHeader.get('NAXIS1'  ,  0)             ), # 40962 A002h 実効画像幅
                    'PixelYDimension'          : int(         hduHeader.get('NAXIS2'  ,  0)             ), # 40963 A003h 実効画像高さ
                    'FocalPlaneXResolution'    : Fraction(int(hduHeader.get('XPIXSZ'  ,  0))     , 10000), # 41486 A20Eh 焦点面の幅の解像度
                    'FocalPlaneYResolution'    : Fraction(int(hduHeader.get('YPIXSZ'  ,  0))     , 10000), # 41487 A20Fh 焦点面の高さの解像度
                    'FocalPlaneResolutionUnit' : 3                                                       , # 41488 A210h 焦点面解像度単位
                    'LensMake'                 : str(         hduHeader.get('ORIGIN'  , '')             ), # 42035 A433h レンズのメーカ名
                    'LensModel'                : str(         hduHeader.get('CAMERA'  , '')             ), # 42036 A434h レンズのモデル名
                }
                
                flowData = FlowData(headers)
                flowData.setDimensions(width, height)
                resultFlowDatas.append(flowData)
                
                # ブロック単位で並列処理
                for y in range(0, height, BLOCK_SIZE):
                    for x in range(0, width, BLOCK_SIZE):
                        future = ParallelExecutor .submit(self, self._processBlock, data, x, y, planeCount, width, height)
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
        from astropy.io import fits

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
                                    if 13<=len(obs_date_str):
                                        dt = datetime.datetime.fromisoformat(obs_date_str)
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
                    'filePath'     : filePath,
                    'obs_date'     : obs_date,
                    'obs_timestamp': obs_timestamp,
                    'hdu_count'    : hdu_count,
                    'dimensions'   : dimensions,
                    'data_type'    : data_type
                }
        except Exception:
            return {
                'filePath'     : filePath,
                'obs_date'     : None,
                'obs_timestamp': None,
                'hdu_count'    : None,
                'dimensions'   : None,
                'data_type'    : None
            }
    
    def getConfigHash(self):
        config = f"{self.minorType}_{"|".join(self.filePaths)}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def _processBlock(self, data, x, y, planeCount, width, height):
        """FITSデータブロックの処理"""
        from config import BLOCK_SIZE
        from base import DataBlock
        
        endY = min(y + BLOCK_SIZE, height)
        endX = min(x + BLOCK_SIZE, width)
        
        # 各プレーンのブロックの切り出し
        dataBlocks = []
        for planeIndex in range(planeCount):
            if data.ndim == 2:
                block = data[y:endY, x:endX]
            else:
                block = data[planeIndex, y:endY, x:endX]
            dataBlocks.append(DataBlock(block, planeIndex, x, y))
        return dataBlocks

class FitsSettingsDialog(BaseReaderSettingsDialog):
    def getColumns(self):
        return ('filename', 'obs_date', 'hdu_count', 'dimensions', 'data_type')
    
    def getColumnHeaders(self):
        return {
            'filename'  : 'ファイル名',
            'obs_date'  : '観測日時',
            'hdu_count' : 'HDU数',
            'dimensions': '画像サイズ',
            'data_type' : 'データ型'
        }
    
    def getColumnWidths(self):
        return {
            'filename'  : {'width':  40, 'stretch': True                },
            'obs_date'  : {'width': 120, 'stretch': False               },
            'hdu_count' : {'width':  60, 'stretch': False, 'anchor': 'e'},
            'dimensions': {'width':  80, 'stretch': False, 'anchor': 'e'},
            'data_type' : {'width':  60, 'stretch': False, 'anchor': 'e'}
        }
    
    def getFormalFileInfo(self, filePath):
        """ファイルの表示用文字列を取得"""
        fileInfo = self.node.getFileInfo(filePath)
        
        return {
            'filename'  : os.path.basename(filePath),
            'obs_date'  : fileInfo.get('obs_date', '日時不明') if fileInfo.get('obs_date') else '日時不明',
            'hdu_count' : str(fileInfo.get('hdu_count', 0))   if fileInfo.get('hdu_count') is not None else '',
            'dimensions': fileInfo.get('dimensions', '')      if fileInfo.get('dimensions') else '',
            'data_type' : fileInfo.get('data_type', '')       if fileInfo.get('data_type') else ''
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
            messagebox.showerror(f"{self.node.name} エラー", f"ソートに失敗しました: {str(e)}")
    
    def createSortButton(self, parent):
        return tk.Button(parent, text="観測日時ソート", command=self.sortByObsDate)
