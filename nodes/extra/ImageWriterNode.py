'''
ImageWriterNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from fractions import Fraction
import datetime
import os
from nodes import BaseWriterNode
from config import BLOCK_SIZE, HEADERS_EXIF, HEADERS_EXIF_OPT

class ImageWriterNode(BaseWriterNode):
    # ノードタイプ
    #majorType = スーパークラスを継承
    minorType = 'image_writer'
    # ノード名
    name      = '画像書き出し'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

        self.outputFileTypes = [("JPEG files", "*.jpg"), ("PNG files", "*.png"), ("TIFF files", "*.tiff"), ("All files", "*.*")]
        self.defaultOutputExtension = ".jpg"
    
    def processFile(self, filePath, flowData, context=None):
        """単一ファイル出力処理"""
        import numpy as np

        # 拡張子に応じたbit深度のデータ型と最大値を決定
        _, ext = os.path.splitext(filePath)
        
        if ext.lower() in ['.tiff', '.tif']:
            import importlib.util
            import sys
            if not getattr(sys, 'frozen', False) and not importlib.util.find_spec('tifffile'):
                raise Exception("ライブラリ tifffile がインストールされていません\npip install tifffile でインストールしてください。")
        else:
            import importlib.util
            import sys
            if not getattr(sys, 'frozen', False) and not importlib.util.find_spec('PIL'):
                raise Exception("ライブラリ PIL がインストールされていません\npip install pillow でインストールしてください。")

        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        dtype, max_out = self._getBitDepthForFormat(ext.lower())
        
        if width == 0 or height == 0:
            return None
        
        type = flowData.getType()
        mode = flowData.getMode()
        
        # display_levelsを使用したスケーリング
        display_levels = flowData.headers.get('display_levels', {}) if flowData.headers else {}
        min_val = display_levels.get('min', 0.0)
        end_val = display_levels.get('exclusive_upper', 1.0)
        
        if None != max_out:
            scale = (max_out + 1) / (end_val - min_val) if end_val != min_val else (max_out + 1)
            offset = min_val
        else:
            scale = 1.0
            offset = 0.0

        if(  type == 'image'  and mode == 'RGB' and 3 <= planeCount
            or type == 'table' and mode == '2D'  and 3 <= planeCount
            ):
            # RGBカラー画像
            imgMode = 'RGB'
            imgArray = np.zeros((height, width, 3), dtype=dtype)
            
            for y in range(0, height, BLOCK_SIZE):
                for x in range(0, width, BLOCK_SIZE):
                    
                    r_block = flowData.getBlock(0, x, y)
                    g_block = flowData.getBlock(1, x, y)
                    b_block = flowData.getBlock(2, x, y)
                    
                    if r_block and g_block and b_block:
                        blockHeight = min(r_block.getHeight(), height - y)
                        blockWidth = min(r_block.getWidth(), width - x)
                        endY = y + blockHeight
                        endX = x + blockWidth
                        
                        r_data = np.nan_to_num((r_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                        g_data = np.nan_to_num((g_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                        b_data = np.nan_to_num((b_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                    
                        if None != max_out:
                            r_data = np.clip(np.round(r_data), 0, max_out)
                            g_data = np.clip(np.round(g_data), 0, max_out)
                            b_data = np.clip(np.round(b_data), 0, max_out)
                        
                        imgArray[y:endY, x:endX, 0] = r_data.astype(dtype)
                        imgArray[y:endY, x:endX, 1] = g_data.astype(dtype)
                        imgArray[y:endY, x:endX, 2] = b_data.astype(dtype)
                    
                    self.reportBlockProgress(context)
            
        elif(  type == 'image'  and mode == 'RGBG' and 4 <= planeCount
            or type == 'table' and mode == '2D'   and 4 <= planeCount
            ):
            # RGBG 4チャンネル画像をRGBに変換
            imgMode = 'RGB'
            imgArray = np.zeros((height, width, 3), dtype=dtype)
            
            for y in range(0, height, BLOCK_SIZE):
                for x in range(0, width, BLOCK_SIZE):
                    
                    r_block = flowData.getBlock(0, x, y)   # R
                    g1_block = flowData.getBlock(1, x, y)  # G1
                    b_block = flowData.getBlock(2, x, y)   # B
                    g2_block = flowData.getBlock(3, x, y)  # G2
                    
                    if r_block and g1_block and b_block and g2_block:
                        blockHeight = min(r_block.getHeight(), height - y)
                        blockWidth = min(r_block.getWidth(), width - x)
                        endY = y + blockHeight
                        endX = x + blockWidth
                        
                        # G1とG2の平均をGチャンネルとして使用
                        g_avg = (g1_block.data[:blockHeight, :blockWidth] + g2_block.data[:blockHeight, :blockWidth]) / 2
                        
                        # 指定bit深度に変換
                        r_data = np.nan_to_num((r_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                        g_data = np.nan_to_num((g_avg                                   - offset) * scale, nan=0.0)
                        b_data = np.nan_to_num((b_block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)
                        
                        if None != max_out:
                            r_data = np.clip(np.round(r_data), 0, max_out)
                            g_data = np.clip(np.round(g_data), 0, max_out)
                            b_data = np.clip(np.round(b_data), 0, max_out)
                        
                        imgArray[y:endY, x:endX, 0] = r_data.astype(dtype)
                        imgArray[y:endY, x:endX, 1] = g_data.astype(dtype)
                        imgArray[y:endY, x:endX, 2] = b_data.astype(dtype)
                    
                    self.reportBlockProgress(context)
            
        elif(  type == 'image'  and mode == 'L'  and 1 <= planeCount
            or type == 'table' and mode == '2D' and 1 <= planeCount
            ):
            # グレースケール画像
            imgMode = 'L'
            imgArray = np.zeros((height, width), dtype=dtype)
            
            for y in range(0, height, BLOCK_SIZE):
                for x in range(0, width, BLOCK_SIZE):
                    block = flowData.getBlock(0, x, y)
                    
                    if block:
                        blockHeight = min(block.getHeight(), height - y)
                        blockWidth = min(block.getWidth(), width - x)
                        endY = y + blockHeight
                        endX = x + blockWidth
                        
                        data = np.nan_to_num((block.data[:blockHeight, :blockWidth] - offset) * scale, nan=0.0)

                        if None != max_out:
                            data = np.clip(np.round(data), 0, max_out)
                        
                        imgArray[y:endY, x:endX] = data.astype(dtype)
                    
                    self.reportBlockProgress(context)
            
        else:
            raise Exception(f"サポートされていないタイプ: {type} {mode}")
        
        # 保存オプションを構築
        save_kwargs = {}
        if ext.lower() in ['.jpg', '.jpeg']:
            save_kwargs.update({'quality': 100, 'optimize': True})
        elif ext.lower() in ['.png']:
            save_kwargs['optimize'] = True
        elif ext.lower() in ['.tiff', '.tif']:
            save_kwargs.update({'compression': 'zlib'})
        
        # EXIF辞書構築
        original_exif = flowData.headers.get('exif', {})
        exifInfo = {}
        if original_exif:
            tags = {name:id for id,name, _, _ in (HEADERS_EXIF + HEADERS_EXIF_OPT)}
            exifInfo = {id: original_exif[name] for name,id in tags.items() if name in original_exif}

            exifInfo[305] = 'HoshinoNe' # 305 Software

            from utils.Debug import Debug
            if not Debug.isTestMode():
                # テストモードではないので現在時刻を入れる
                exifInfo[306] = datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S") # 306 DateTime
        
        if not exifInfo:
            pass
        elif ext.lower() in ['.tiff', '.tif']:
            if 305 in exifInfo:
                save_kwargs['software'] = exifInfo.pop(305)
            
            # tifffile が自動的に処理するタグのリスト
            skipTags = {
                256, # 0100h ImageWidth                画像の幅
                257, # 0101h ImageLength               画像の高さ
                258, # 0102h BitsPerSample             画像のビットの深さ
                259, # 0103h Compression               圧縮の種類
                262, # 0106h PhotometricInterpretation 画素構成
                273, # 0111h StripOffsets              画像データのロケーション
                277, # 0115h SamplesPerPixel           コンポーネント数
                278, # 0116h RowsPerStrip              ストリップあたりの行数
                279, # 0117h StripByteCounts           ストリップの総バイト数
                282, # 011Ah XResolution               画像の幅の解像度
                283, # 011Bh YResolution               画像の高さの解像度
                284, # 011Ch PlanarConfiguration       画像データの並び
                296, # 0128h ResolutionUnit            画像の幅と高さの解像度の単位
            }

            ifd = []
            for tagId, value in exifInfo.items():
                if tagId in skipTags:
                    pass
                elif isinstance(value, list) and 0<len(value):
                    if isinstance(v[0], Fraction):
                        values = tuple((v.numerator, v.denominator) for v in value)
                        ifd.append((tagId, 5, len(values), values, True)) # RATIONAL
                    elif isinstance(v[0], int):
                        values = tuple((v.numerator, v.denominator) for v in value)
                        ifd.append((tagId, 3, len(values), values, True)) # SHORT
                elif isinstance(value, Fraction):
                    ifd.append((tagId, 5, 1, (value.numerator, value.denominator), True)) # RATIONAL
                elif isinstance(value, str):
                    ifd.append((tagId, 2, len(value) + 1, value, True)) # ASCII
                elif isinstance(value, int):
                    ifd.append((tagId, 3, 1, value, True)) # SHORT
            
            save_kwargs['extratags'] = ifd
        else:
            # EXIF bytes変換
            from PIL import Image, TiffImagePlugin
            from PIL.ExifTags import IFD,TAGS

            exif = Image.Exif()
            
            for tagId, value in exifInfo.items():
                if 256 <= tagId <= 33432:
                    ifd = exif                      # 0th IFD TIFF Tag
                elif 33434 <= tagId <= 42240:
                    ifd = exif.get_ifd(IFD.Exif)    # 0th IFD Exif Private Tag
                elif 0 <= tagId <= 31:
                    ifd = exif.get_ifd(IFD.GPSInfo) # 0th IFD GPS Info Tag

                if isinstance(value, list):
                    values = []
                    for v in value:
                        if isinstance(v, Fraction):
                            values.append(TiffImagePlugin.IFDRational(v))
                        else:
                            values.append(v)
                    ifd[tagId] = tuple(values)
                elif isinstance(value, Fraction):
                    ifd[tagId] = TiffImagePlugin.IFDRational(value)
                else:
                    ifd[tagId] = value
            
            save_kwargs['exif'] = exif.tobytes()

        # 保存処理
        if ext.lower() in ['.tiff', '.tif']:
            import tifffile
            imgMode = 'rgb' if "RGB" == imgMode else 'minisblack'
            tifffile.imwrite(filePath, imgArray, photometric=imgMode, **save_kwargs)
        else: # 他フォーマット: PIL使用
            from PIL import Image
            img = Image.fromarray(imgArray, imgMode)
            img.save(filePath, **save_kwargs)
        
        fileSize = os.path.getsize(filePath)
        return (filePath, fileSize, planeCount, width, height)
        
    def _getBitDepthForFormat(self, ext):
        """拡張子に応じたbit深度のデータ型と最大値を返す"""
        import numpy as np
        
        if ext in ['.tiff', '.tif']:
            return np.uint16, 65535  # 32bit float がうまく行かないので暫定
            #return np.float32, None  # 32bit float ：元の値をそのまま保存
        elif ext in ['.ppm', '.pgm']:
            return np.uint16, 65535  # 16bit
        else: # '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tga', '.pcx', '.sgi', '.sun', '.xpm'
            return np.uint8, 255  # デフォルトは8bit
