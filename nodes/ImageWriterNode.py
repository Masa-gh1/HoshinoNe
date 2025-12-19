'''
ImageWriterNode class

@author: Masakazu Inoue
'''

import hashlib
import os
import numpy as np
from tkinter import filedialog, messagebox
from PIL import Image
from base import FlowNode, FlowData
from config import BLOCK_SIZE

class ImageWriterNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        self.filePath = ""
        super().__init__(canvas, editor, x, y, "image_writer", "画像書き出し")
        self.filetypes = [("JPEG files", "*.jpg"), ("PNG files", "*.png"), ("All files", "*.*")]
        self.defaultextension = ".jpg"
    
    def getColor(self):
        return 'lightcyan'
    
    def setFilePath(self, filePath):
        self.filePath = filePath
    
    def updateNodeText(self):
        if self.filePath:
            fileName = os.path.basename(self.filePath)
            displayText = f"{self.text}\n{fileName}"
        else:
            displayText = self.text
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        flowDir = os.path.dirname(self.editor.currentFlowPath)
        relativePath = os.path.relpath(self.filePath, flowDir)
        nodeData["filePath"] = relativePath
    
    def restore(self, nodeData):
        if "filePath" in nodeData:
            flowDir = os.path.dirname(self.editor.currentFlowPath)
            self.filePath = os.path.abspath(os.path.join(flowDir, nodeData["filePath"]))
            self.updateNodeText()
    
    def process(self, context):
        self.reportProgress(context, "開始")
        if not self.filePath:
            messagebox.showerror("エラー", "出力ファイルが設定されていません")
            return
        
        # 前のノードからデータを収集
        flowDatas = []
        for node in context['input_nodes']:
            flowDatas.extend(node.flowDatas)
        
        if not flowDatas:
            messagebox.showerror("エラー", "画像データがありません")
            return
        
        try:
            # 全ファイルの総ブロック数を計算
            totalAllBlocks = 0
            for flowData in flowDatas:
                width, height, planeCount = flowData.getDimensions()
                if width > 0 and height > 0:
                    totalAllBlocks += ((height + BLOCK_SIZE - 1) // BLOCK_SIZE) * ((width + BLOCK_SIZE - 1) // BLOCK_SIZE)
            
            processedAllBlocks = 0
            
            # 複数データの処理
            self.reportProgress(context, f"処理中 ")
            
            for dataIdx, flowData in enumerate(flowDatas):
                width, height, planeCount = flowData.getDimensions()
                if width == 0 or height == 0:
                    continue
                
                # ファイル名の生成
                if len(flowDatas) == 1:
                    outputPath = self.filePath
                else:
                    base, ext = os.path.splitext(self.filePath)
                    outputPath = f"{base}_{dataIdx}{ext}"
                
                mode = flowData.getMode()
                if mode == 'RGB':
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
                elif mode == 'L':
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
                    messagebox.showerror("エラー", f"サポートされていないモード: {mode}")
                    continue
                
                img.save(outputPath)
            
            # 処理完了を示すためにflowDatasを設定
            self.flowDatas = [FlowData()]
        except Exception as e:
            messagebox.showerror("エラー", f"画像出力に失敗しました: {str(e)}")
        
        self.reportProgress(context, "完了")

    def getConfigHash(self):
        """ファイルパスを含む設定ハッシュ"""
        config = f"{self.type}_{self.filePath}"
        return hashlib.md5(config.encode()).hexdigest()
