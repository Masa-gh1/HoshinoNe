'''
ImageWriterNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import os
import datetime
import numpy as np
from nodes import BaseWriterNode
from config import BLOCK_SIZE, HEADERS_EXIF, HEADERS_EXIF_OPT

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import tifffile
    TIFFFILE_AVAILABLE = True
except ImportError:
    TIFFFILE_AVAILABLE = False

class ImageWriterNode(BaseWriterNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_writer", "画像書き出し", **kwargs)
        self.outputFileTypes = [("JPEG files", "*.jpg"), ("PNG files", "*.png"), ("TIFF files", "*.tiff"), ("All files", "*.*")]
        self.defaultOutputExtension = ".jpg"
    
    def processFile(self, filePath, flowData, context=None):
        """単一ファイル出力処理"""
        # 拡張子に応じたbit深度のデータ型と最大値を決定
        _, ext = os.path.splitext(filePath)
        
        if ext.lower() in ['.tiff', '.tif']:
            if not TIFFFILE_AVAILABLE:
                raise Exception("tifffileライブラリがインストールされていません\npip install tifffile でインストールしてください。")
        else:
            if not PIL_AVAILABLE:
                raise Exception("PILライブラリがインストールされていません\npip install pillow でインストールしてください。")

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
        exif_dict = {}
        if original_exif:
            preserve_tags = [name for name, _, _ in (HEADERS_EXIF + HEADERS_EXIF_OPT)]
            exif_dict = {tag: original_exif[tag] for tag in preserve_tags if tag in original_exif}
            
            # テストモード時は元のDateTimeを保持、通常モード時のみ更新
            test_mode = os.getenv('FLOWEDITOR_TEST_MODE', '').lower() in ['1', 'true', 'yes']
            # テストモード ###################
            
            exif_dict['Software'] = 'ほしのね'
            if not test_mode:
                exif_dict['DateTime'] = datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S")
        
        if not exif_dict:
            pass
        elif ext.lower() in ['.tiff', '.tif']:
            save_kwargs['metadata'] = exif_dict
        else:
            # EXIF bytes変換
            if exif_dict:
                exif = Image.Exif()
                tag_map = {tname: tid for tid, tname in TAGS.items()}
                
                for tag_name, value in exif_dict.items():
                    if tag_name in tag_map:
                        exif[tag_map[tag_name]] = value
                
                save_kwargs['exif'] = exif.tobytes()

        # 保存処理
        if ext.lower() in ['.tiff', '.tif']:
            imgMode = 'rgb' if "RGB" == imgMode else 'minisblack'
            tifffile.imwrite(filePath, imgArray, photometric=imgMode, **save_kwargs)
        else: # 他フォーマット: PIL使用
            img = Image.fromarray(imgArray, imgMode)
            img.save(filePath, **save_kwargs)
        
        fileSize = os.path.getsize(filePath)
        return (filePath, fileSize, planeCount, width, height)
        
    def _getBitDepthForFormat(self, ext):
        """拡張子に応じたbit深度のデータ型と最大値を返す"""
        if ext in ['.tiff', '.tif']:
            return np.uint16, 65535  # 32bit float がうまく行かないので暫定
            #return np.float32, None  # 32bit float ：元の値をそのまま保存
        elif ext in ['.ppm', '.pgm']:
            return np.uint16, 65535  # 16bit
        else: # '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tga', '.pcx', '.sgi', '.sun', '.xpm'
            return np.uint8, 255  # デフォルトは8bit
