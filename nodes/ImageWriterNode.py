'''
ImageWriterNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import os
import numpy as np
from base import BaseWriterNode
from config import BLOCK_SIZE

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ImageWriterNode(BaseWriterNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_writer", "画像書き出し", **kwargs)
        self.outputFileTypes = [("JPEG files", "*.jpg"), ("PNG files", "*.png"), ("All files", "*.*")]
        self.defaultOutputExtension = ".jpg"
    
    def processFile(self, filePath, flowData, context=None):
        """単一ファイル出力処理"""
        if not PIL_AVAILABLE:
            raise Exception("PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
        
        try:
            width, height = flowData.getDimensions()
            planeCount = flowData.getPlaneCount()
            
            if width == 0 or height == 0:
                return None
            
            type = flowData.getType()
            mode = flowData.getMode()
            
            if(  type == 'image' and mode == 'RGB'
              or type == 'matrix' and mode == '2D' and planeCount == 3
              ):
                # RGBカラー画像
                imgArray = np.zeros((height, width, 3), dtype=np.uint8)
                
                for blockY in range(0, height, BLOCK_SIZE):
                    for blockX in range(0, width, BLOCK_SIZE):
                        
                        r_block = flowData.getBlock(0, blockX, blockY)
                        g_block = flowData.getBlock(1, blockX, blockY)
                        b_block = flowData.getBlock(2, blockX, blockY)
                        
                        if r_block and g_block and b_block:
                            blockHeight = r_block.getHeight()
                            blockWidth = r_block.getWidth()
                            
                            endY = min(blockY + blockHeight, height)
                            endX = min(blockX + blockWidth, width)
                            
                            # display_levelsを使用したスケーリング
                            display_levels = flowData.headers.get('display_levels', {}) if flowData.headers else {}
                            min_val = display_levels.get('min', 0.0)
                            max_val = display_levels.get('exclusive_upper', 1.0)
                            
                            # 入力範囲から[0, 255]へのスケーリング（NaNは0に変換）
                            scale = 255.0 / (max_val - min_val) if max_val != min_val else 255.0
                            r_data = np.nan_to_num((r_block.data[:endY-blockY, :endX-blockX] - min_val) * scale, nan=0.0)
                            g_data = np.nan_to_num((g_block.data[:endY-blockY, :endX-blockX] - min_val) * scale, nan=0.0)
                            b_data = np.nan_to_num((b_block.data[:endY-blockY, :endX-blockX] - min_val) * scale, nan=0.0)
                            imgArray[blockY:endY, blockX:endX, 0] = np.clip(np.round(r_data), 0, 255).astype(np.uint8)
                            imgArray[blockY:endY, blockX:endX, 1] = np.clip(np.round(g_data), 0, 255).astype(np.uint8)
                            imgArray[blockY:endY, blockX:endX, 2] = np.clip(np.round(b_data), 0, 255).astype(np.uint8)
                        
                        self.reportBlockProgress(context)
                
                img = Image.fromarray(imgArray, 'RGB')
            elif(  type == 'image' and mode == 'RGGB'
                or type == 'matrix' and mode == '2D' and planeCount == 4
                ):
                # RGGB 4チャンネル画像をRGBに変換
                imgArray = np.zeros((height, width, 3), dtype=np.uint8)
                
                for blockY in range(0, height, BLOCK_SIZE):
                    for blockX in range(0, width, BLOCK_SIZE):
                        
                        r_block = flowData.getBlock(0, blockX, blockY)   # R
                        g1_block = flowData.getBlock(1, blockX, blockY)  # G1
                        b_block = flowData.getBlock(2, blockX, blockY)   # B
                        g2_block = flowData.getBlock(3, blockX, blockY)  # G2
                        
                        if r_block and g1_block and b_block and g2_block:
                            blockHeight = r_block.getHeight()
                            blockWidth = r_block.getWidth()
                            
                            endY = min(blockY + blockHeight, height)
                            endX = min(blockX + blockWidth, width)
                            
                            # G1とG2の平均をGチャンネルとして使用
                            g_avg = (g1_block.data[:endY-blockY, :endX-blockX] + g2_block.data[:endY-blockY, :endX-blockX]) / 2
                            
                            # display_levelsを使用したスケーリング
                            display_levels = flowData.headers.get('display_levels', {}) if flowData.headers else {}
                            min_val = display_levels.get('min', 0.0)
                            max_val = display_levels.get('exclusive_upper', 1.0)
                            
                            # 入力範囲から[0, 255]へのスケーリング（NaNは0に変換）
                            scale = 255.0 / (max_val - min_val) if max_val != min_val else 255.0
                            r_data = np.nan_to_num((r_block.data[:endY-blockY, :endX-blockX] - min_val) * scale, nan=0.0)
                            g_data = np.nan_to_num((g_avg - min_val) * scale, nan=0.0)
                            b_data = np.nan_to_num((b_block.data[:endY-blockY, :endX-blockX] - min_val) * scale, nan=0.0)
                            imgArray[blockY:endY, blockX:endX, 0] = np.clip(np.round(r_data), 0, 255).astype(np.uint8)
                            imgArray[blockY:endY, blockX:endX, 1] = np.clip(np.round(g_data), 0, 255).astype(np.uint8)
                            imgArray[blockY:endY, blockX:endX, 2] = np.clip(np.round(b_data), 0, 255).astype(np.uint8)
                        
                        self.reportBlockProgress(context)
                
                img = Image.fromarray(imgArray, 'RGB')
            elif(  type == 'image' and mode == 'L'
                or type == 'matrix' and mode == '2D' and planeCount == 1
                ):
                # グレースケール画像
                imgArray = np.zeros((height, width), dtype=np.uint8)
                
                for blockY in range(0, height, BLOCK_SIZE):
                    for blockX in range(0, width, BLOCK_SIZE):
                        block = flowData.getBlock(0, blockX, blockY)
                        
                        if block:
                            blockHeight = block.getHeight()
                            blockWidth = block.getWidth()
                            
                            endY = min(blockY + blockHeight, height)
                            endX = min(blockX + blockWidth, width)
                            
                            # display_levelsを使用したスケーリング
                            display_levels = flowData.headers.get('display_levels', {}) if flowData.headers else {}
                            min_val = display_levels.get('min', 0.0)
                            max_val = display_levels.get('exclusive_upper', 1.0)
                            
                            # 入力範囲から[0, 255]へのスケーリング（NaNは0に変換）
                            scale = 255.0 / (max_val - min_val) if max_val != min_val else 255.0
                            data = np.nan_to_num((block.data[:endY-blockY, :endX-blockX] - min_val) * scale, nan=0.0)
                            imgArray[blockY:endY, blockX:endX] = np.clip(np.round(data), 0, 255).astype(np.uint8)
                        
                        self.reportBlockProgress(context)
                
                img = Image.fromarray(imgArray, 'L')
            else:
                raise Exception(f"サポートされていないタイプ: {type} {mode}")
            
            _,ext = os.path.splitext(filePath)
            if   ext.lower() in ['.jpg', '.jpeg']: img.save(filePath, quality=100, optimize=True)
            elif ext.lower() in ['.png']         : img.save(filePath, optimize=True)
            else                                 : img.save(filePath)
            
            fileSize = os.path.getsize(filePath)
            return (filePath, fileSize, planeCount, width, height)
            
        except Exception as e:
            raise Exception(f"画像出力エラー ({filePath}): {str(e)}")


