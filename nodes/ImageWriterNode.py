'''
ImageWriterNode class

@author: Masakazu Inoue
'''

import hashlib
import sys
import os
import traceback
import numpy as np
from tkinter import filedialog, messagebox
from base import FlowNode, FlowData
from config import BLOCK_SIZE

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ImageWriterNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_writer", "画像書き出し")
        self.outputFilePath = ""
        self.outputFileTypes = [("JPEG files", "*.jpg"), ("PNG files", "*.png"), ("All files", "*.*")]
        self.defaultOutputExtension = ".jpg"
    
    def getColor(self):
        return self._color_io
    
    def setOutputFilePath(self, filePath):
        self.outputFilePath = filePath
    
    def updateNodeText(self):
        if self.outputFilePath:
            fileName = os.path.basename(self.outputFilePath)
            displayText = f"{self.text}\n{fileName}"
        else:
            displayText = self.text
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        flowDir = os.path.dirname(self.editor.currentFlowPath)
        relativePath = os.path.relpath(self.outputFilePath, flowDir)
        nodeData["outputFilePath"] = relativePath
    
    def restore(self, nodeData):
        if "outputFilePath" in nodeData:
            flowDir = os.path.dirname(self.editor.currentFlowPath)
            self.outputFilePath = os.path.abspath(os.path.join(flowDir, nodeData["outputFilePath"]))
            self.updateNodeText()
    
    def process(self, context=None):
        if not PIL_AVAILABLE:
            messagebox.showerror(f"{self.text} エラー", "PILライブラリがインストールされていません\npip install pillow でインストールしてください。")
        
        self.reportProgress(context, "開始")
        if not self.outputFilePath:
            messagebox.showerror(f"{self.text} エラー", "出力ファイルが設定されていません")
            return
        
        # 前のノードからデータを収集
        flowDatas = []
        for node in self.inputNodes:
            flowDatas.extend(node.flowDatas)
        
        if not flowDatas:
            messagebox.showerror(f"{self.text} エラー", "画像データがありません")
            return
        
        try:
            # 全ファイルの総ブロック数を計算
            totalAllBlocks = 0
            for flowData in flowDatas:
                width, height = flowData.getDimensions()
                planeCount = flowData.getPlaneCount()
                if width > 0 and height > 0:
                    totalAllBlocks += ((height + BLOCK_SIZE - 1) // BLOCK_SIZE) * ((width + BLOCK_SIZE - 1) // BLOCK_SIZE)
            
            processedAllBlocks = 0
            
            # 複数データの処理
            self.reportProgress(context, f"処理中 ")
            
            fileInfos = []
            
            for dataIdx, flowData in enumerate(flowDatas):
                width, height = flowData.getDimensions()
                planeCount = flowData.getPlaneCount()
                if width == 0 or height == 0:
                    continue
                
                # ファイル名の生成
                if len(flowDatas) == 1:
                    outputPath = self.outputFilePath
                else:
                    base, ext = os.path.splitext(self.outputFilePath)
                    outputPath = f"{base}_{dataIdx}{ext}"
                
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
                                
                                # numpy配列で一括処理
                                imgArray[blockY:endY, blockX:endX, 0] = np.clip(r_block.data[:endY-blockY, :endX-blockX], 0, 255).astype(np.uint8)
                                imgArray[blockY:endY, blockX:endX, 1] = np.clip(g_block.data[:endY-blockY, :endX-blockX], 0, 255).astype(np.uint8)
                                imgArray[blockY:endY, blockX:endX, 2] = np.clip(b_block.data[:endY-blockY, :endX-blockX], 0, 255).astype(np.uint8)
                            
                            processedAllBlocks += 1
                            self.reportProgress(context, f"処理中", processedAllBlocks, totalAllBlocks)
                    
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
                                
                                imgArray[blockY:endY, blockX:endX, 0] = np.clip(r_block.data[:endY-blockY, :endX-blockX], 0, 255).astype(np.uint8)
                                imgArray[blockY:endY, blockX:endX, 1] = np.clip(g_avg, 0, 255).astype(np.uint8)
                                imgArray[blockY:endY, blockX:endX, 2] = np.clip(b_block.data[:endY-blockY, :endX-blockX], 0, 255).astype(np.uint8)
                            
                            processedAllBlocks += 1
                            self.reportProgress(context, f"処理中", processedAllBlocks, totalAllBlocks)
                    
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
                                
                                # numpy配列で一括処理
                                imgArray[blockY:endY, blockX:endX] = np.clip(block.data[:endY-blockY, :endX-blockX], 0, 255).astype(np.uint8)
                            
                            processedAllBlocks += 1
                            self.reportProgress(context, f"処理中", processedAllBlocks, totalAllBlocks)
                    
                    img = Image.fromarray(imgArray, 'L')
                else:
                    messagebox.showerror(f"{self.text} エラー", f"サポートされていないタイプ: {type} {mode}")
                    continue
                
                _,ext = os.path.splitext(outputPath)
                opt = {}
                if ext.lower() in ['.jpg', '.jpeg']: img.save( outputPath, quality=100, optimize=True)
                elif ext.lower() in ['.png']       : img.save( outputPath, optimize=True)
                else                               : img.save( outputPath)
                fileInfos.append( (outputPath, os.path.getsize(outputPath), planeCount, width, height))
            
            # 処理完了情報をCSV形式のFlowDataとして設定
            fileNames = [os.path.basename(path) for path, _, _, _, _ in fileInfos]
            
            headers = {
                'type': 'matrix',
                'mode': '2D',
                'columns': ['size', 'planeCount', 'width', 'height'],
                'lines': fileNames,
                'planes': ['file info']
            }
            
            resultFlowData = FlowData(headers)
            resultFlowData.setDimensions(4, len(fileInfos))
            data = [ [size, planeCount, width, height] for _, size, planeCount, width, height in fileInfos ]
            from base import DataBlock
            block = DataBlock( 0, 0, 0, data)
            resultFlowData.setBlock(block)
            
            self.flowDatas = [resultFlowData]
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            messagebox.showerror(f"{self.text} エラー", f"画像出力に失敗しました: {str(e)}\n\nトラックバック:\n{tb}")
        
        self.reportProgress(context, "完了")

    def getConfigHash(self):
        """ファイルパスを含む設定ハッシュ"""
        config = f"{self.type}_{self.outputFilePath}"
        return hashlib.md5(config.encode()).hexdigest()
