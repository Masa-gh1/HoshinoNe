'''
FileReaderNode class

@author: Masakazu Inoue
'''

import csv
import hashlib
import os
from tkinter import filedialog
from base import FlowNode, FlowData, DataBlock
from config import MAX_WORKERS, BLOCK_SIZE

class FileReaderNode(FlowNode):
    def __init__(self, canvas, editor, x, y, nonDialog=False, **kwargs):
        self.filePaths = []
        super().__init__(canvas, editor, x, y, "file_reader", "ファイル読み込み")
        self.filetypes = [("CSV files", "*.csv")]
    
    def getColor(self):
        return 'lightyellow'
    
    def setFilePaths(self, filePaths):
        self.filePaths = filePaths

    def store(self, nodeData):
        # 相対パスで保存
        flowDir = os.path.dirname(self.editor.currentFlowPath)
        relativePaths = [os.path.relpath(path, flowDir) for path in self.filePaths]
        nodeData["filePaths"] = relativePaths
    
    def restore(self, nodeData):
        if "filePaths" in nodeData:
            flowDir = os.path.dirname(self.editor.currentFlowPath)
            self.filePaths = [os.path.abspath(os.path.join(flowDir, path)) for path in nodeData["filePaths"]]
            self.updateNodeText()

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
    
    def process(self, context):
        self.reportProgress(context, "開始")
        allData = []
        headers = []
        
        totalFiles = len(self.filePaths)
        for fileIdx, filePath in enumerate(self.filePaths):
            self.reportProgress(context, "読み込み中", fileIdx, totalFiles)
            with open(filePath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                
                # プレーン情報を初期化
                currentPlane = 0
                planeNames = []
                planeData = []
                dataType = 'matrix'
                
                for row in reader:
                    if not row:
                        continue
                    
                    # プレーンマーカーをチェック
                    if row[0].startswith('# '):
                        planeName = row[0][2:]  # '# 'を除去
                        planeNames.append(planeName)
                        if currentPlane > 0:  # 2枚目以降のプレーン
                            planeData.append(fileData)
                        fileData = []
                        rowHeaders = []
                        currentPlane += 1
                        continue
                    
                    # ヘッダー行をチェック (各プレーンでリセット)
                    if len(row) > 1 and not row[0].replace('.', '').replace('-', '').replace('e', '').replace('+', '').isdigit():
                        # 最初のヘッダーでないか、数値ではない場合はヘッダーとみなす
                        try:
                            float(row[1])  # 2列目が数値かチェック
                            # 数値の場合はデータ行として処理
                        except ValueError:
                            # 数値でない場合はヘッダー行
                            if not headers:  # 最初のヘッダーのみ保存
                                dataType = row[0] if row[0] else 'matrix'
                                headers = row[1:]
                            continue
                    
                    # データ行を処理
                    if row:
                        rowHeader = row[0]
                        rowHeaders.append(rowHeader)
                        convertedRow = []
                        for value in row[1:]:
                            try:
                                convertedRow.append(float(value))
                            except ValueError:
                                convertedRow.append(None)
                        fileData.append(convertedRow)
                
                # 最後のプレーンを追加
                if fileData:
                    planeData.append(fileData)
                
                # プレーンが1つだけの場合は直接追加
                if not planeNames:
                    allData.extend(fileData)
                else:
                    # 複数プレーンの場合は最初のプレーンを使用
                    if planeData:
                        allData.extend(planeData[0])
        
        # FlowDataを作成してブロック単位で保存
        flowHeaders = {'type': dataType, 'mode': '3D' if planeNames else '2D', 'columns': headers, 'lines': rowHeaders}
        if planeNames:
            flowHeaders['planes'] = planeNames
        flowData = FlowData(flowHeaders)
        if planeData:
            # 複数プレーンの場合
            height = len(planeData[0]) if planeData[0] else 0
            width = len(planeData[0][0]) if height > 0 else 0
            planeCount = len(planeData)
            flowData.setDimensions(width, height, planeCount)
            
            for planeIdx, data in enumerate(planeData):
                for y in range(0, height, BLOCK_SIZE):
                    for x in range(0, width, BLOCK_SIZE):
                        endY = min(y + BLOCK_SIZE, height)
                        endX = min(x + BLOCK_SIZE, width)
                        
                        block = []
                        for rowIdx in range(y, endY):
                            if rowIdx < len(data):
                                blockRow = data[rowIdx][x:endX]
                                block.append(blockRow)
                        
                        if block:
                            dataBlock = DataBlock(planeIdx, x, y, block)
                            flowData.setBlock(dataBlock)
            self.flowDatas = [flowData]
        elif allData:
            # 単一プレーンの場合
            height = len(allData)
            width = len(allData[0]) if height > 0 else 0
            flowData.setDimensions(width, height, 1)
            
            for y in range(0, height, BLOCK_SIZE):
                for x in range(0, width, BLOCK_SIZE):
                    endY = min(y + BLOCK_SIZE, height)
                    endX = min(x + BLOCK_SIZE, width)
                    
                    block = []
                    for rowIdx in range(y, endY):
                        blockRow = allData[rowIdx][x:endX]
                        block.append(blockRow)
                    
                    dataBlock = DataBlock(0, x, y, block)
                    flowData.setBlock(dataBlock)
            self.flowDatas = [flowData]
        else:
            self.flowDatas = []
        
        self.reportProgress(context, "完了")
    
    def getConfigHash(self):
        """ファイルパスを含む設定ハッシュ"""
        config = f"{self.type}_{''.join(self.filePaths)}"
        return hashlib.md5(config.encode()).hexdigest()