'''
ImageReaderNode class

@author: Masakazu Inoue
'''

import hashlib
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog
from PIL import Image
from base import FlowNode, FlowData, DataBlock
from config import MAX_WORKERS, BLOCK_SIZE

class ImageReaderNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_reader", "画像読み込み")
        self.filePaths = []
        self.fileTypes = [("Image files", "*.jpg *.jpeg *.png *.bmp *.gif")]
    
    def getColor(self):
        return 'lightyellow'
    
    def setFilePaths(self, filePaths):
        self.filePaths = filePaths
    
    def updateNodeText(self):
        if self.filePaths:
            fileNames = [os.path.basename(path) for path in self.filePaths]
            if 1 == len(fileNames):
                displayText = f"{self.text}\n{fileNames[0]}"
            else:
                displayText = f"{self.text}\n{fileNames[0]} ... 計{len(fileNames)}"
        else:
            displayText = self.text
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        flowDir = os.path.dirname(self.editor.currentFlowPath)
        relativePaths = [os.path.relpath(path, flowDir) for path in self.filePaths]
        nodeData["filePaths"] = relativePaths
    
    def restore(self, nodeData):
        if "filePaths" in nodeData:
            flowDir = os.path.dirname(self.editor.currentFlowPath)
            self.filePaths = [os.path.abspath(os.path.join(flowDir, path)) for path in nodeData["filePaths"]]
            self.updateNodeText()
    
    def process(self, context):
        self.reportProgress(context, "開始")
        
        # ブロック単位で処理（並列化）
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            resultFlowDatas = []
            futureToDatas = {}
            
            for fileIdx, filePath in enumerate(self.filePaths):
                img = Image.open(filePath)
                width, height = img.size
                
                if img.mode == 'RGB':
                    # RGBカラー画像の場合
                    headers = {'type': 'image', 'mode': 'RGB', 'planes': ['R', 'G', 'B']}
                    pixels = list(img.getdata())
                    flowData = FlowData(headers)
                    flowData.setDimensions(width, height)
                    resultFlowDatas.append(flowData)
                    
                    for blockY in range(0, height, BLOCK_SIZE):
                        for blockX in range(0, width, BLOCK_SIZE):
                            future = executor.submit(self._processRgbBlock, pixels, width, height, blockX, blockY)
                            futureToDatas[future] = flowData
                else:
                    # グレースケール画像の場合
                    headers = {'type': 'image', 'mode': 'L', 'planes': ['L']}
                    img_gray = img.convert('L')
                    pixels = list(img_gray.getdata())
                    flowData = FlowData(headers)
                    flowData.setDimensions(width, height)
                    resultFlowDatas.append(flowData)
                    
                    for blockY in range(0, height, BLOCK_SIZE):
                        for blockX in range(0, width, BLOCK_SIZE):
                            future = executor.submit(self._processGrayBlock, pixels, width, height, blockX, blockY)
                            futureToDatas[future] = flowData

            # 全ブロックの処理完了を待つ
            self.reportProgress(context, "処理中")
            totalBlocks = len(futureToDatas)
            for i, future in enumerate(as_completed(futureToDatas)):
                blocks = future.result()
                for block in blocks:
                    futureToDatas[future].setBlock(block)
                self.reportProgress(context, "処理中", i + 1, totalBlocks)
    
            self.flowDatas = resultFlowDatas
                    
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        """ファイルパスを含む設定ハッシュ"""
        config = f"{self.type}_{''.join(self.filePaths)}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def _processRgbBlock(self, pixels, width, height, blockX, blockY):
        """単一RGBブロックの処理"""
        endY = min(blockY + BLOCK_SIZE, height)
        endX = min(blockX + BLOCK_SIZE, width)
        
        blockWidth = endX - blockX
        blockHeight = endY - blockY
        
        # RGB各プレーンのブロックをnumpy配列で作成
        r_block = np.zeros((blockHeight, blockWidth), dtype=np.float64)
        g_block = np.zeros((blockHeight, blockWidth), dtype=np.float64)
        b_block = np.zeros((blockHeight, blockWidth), dtype=np.float64)
        
        for y in range(blockHeight):
            for x in range(blockWidth):
                pixelIdx = (blockY + y) * width + (blockX + x)
                r, g, b = pixels[pixelIdx]
                r_block[y, x] = float(r)
                g_block[y, x] = float(g)
                b_block[y, x] = float(b)
        
        # 各プレーンのブロック情報を返す
        blocks = []
        for planeIdx, block in enumerate([r_block, g_block, b_block]):
            blocks.append(DataBlock(planeIdx, blockX, blockY, block))
        return blocks
    
    def _processGrayBlock(self, pixels, width, height, blockX, blockY):
        """単一グレースケールブロックの処理"""
        endY = min(blockY + BLOCK_SIZE, height)
        endX = min(blockX + BLOCK_SIZE, width)
        
        blockWidth = endX - blockX
        blockHeight = endY - blockY
        
        gray_block = np.zeros((blockHeight, blockWidth), dtype=np.float64)
        for y in range(blockHeight):
            for x in range(blockWidth):
                pixelIdx = (blockY + y) * width + (blockX + x)
                pixel = pixels[pixelIdx]
                gray_block[y, x] = float(pixel)
        
        # 各プレーンのブロック情報を返す
        blocks = []
        for planeIdx, block in enumerate([gray_block]):
            blocks.append(DataBlock(planeIdx, blockX, blockY, block))
        return blocks
