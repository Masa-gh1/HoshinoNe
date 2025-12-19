'''
FileWriterNode class

@author: Masakazu Inoue
'''

import csv
import sys
import os
import traceback
from tkinter import filedialog, messagebox
from base import FlowNode, FlowData
from config import MAX_WORKERS, BLOCK_SIZE

class FileWriterNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "file_writer", "ファイル書き出し")
        self.outputFilePath = ""
        self.outputFileTypes = [("CSV files", "*.csv"), ("All files", "*.*")]
        self.defaultOutputExtension = ".csv"
    
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
        self.reportProgress(context, "開始")
        if not self.outputFilePath:
            messagebox.showerror(f"{self.text} エラー", "出力ファイルが設定されていません")
            return
        
        # 前のノードからデータを収集
        flowDatas = []
        for node in self.inputNodes:
            flowDatas.extend(node.flowDatas)
        
        if not flowDatas:
            messagebox.showerror(f"{self.text} エラー", "データがありません")
            return
        
        try:
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
                
                planeNames = flowData.headers.get('planes', ['data']) if flowData.headers else ['data']
                totalBlocks = ((height + BLOCK_SIZE - 1) // BLOCK_SIZE) * ((width + BLOCK_SIZE - 1) // BLOCK_SIZE) * planeCount
                processedBlocks = 0
                
                with open(outputPath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # 行ヘッダーを取得
                    lineHeaders = flowData.headers.get('lines', []) if flowData.headers else []
                    
                    # 各プレーンを処理
                    for planeIdx in range(planeCount):
                        # プレーン数が2以上の場合はプレーン名を書き込み
                        if planeCount >= 2:
                            writer.writerow([f'# {planeNames[planeIdx]}'])
                        
                        # ヘッダー行を書き込み
                        if flowData.headers and 'columns' in flowData.headers:
                            headerRow = [flowData.headers.get('type', 'matrix')]
                            headerRow.extend(flowData.headers['columns'])
                            writer.writerow(headerRow)
                        
                        # ブロック単位でデータを読み取り、CSVに書き込み
                        currentRow = 0
                        for blockY in range(0, height, BLOCK_SIZE):
                            for blockX in range(0, width, BLOCK_SIZE):
                                self.reportProgress(context, "書き込み中", processedBlocks, totalBlocks)
                                block = flowData.getBlock(planeIdx, blockX, blockY)
                                
                                if block:
                                    blockHeight = block.getHeight()
                                    blockWidth = block.getWidth()
                                    
                                    for y in range(blockHeight):
                                        row = []
                                        # 1列目に行ヘッダーを追加
                                        if currentRow < len(lineHeaders):
                                            row.append(lineHeaders[currentRow])
                                        else:
                                            row.append(f'row_{currentRow}')
                                        
                                        # データを追加
                                        for x in range(blockWidth):
                                            value = block.data[y][x]
                                            if value is None:
                                                row.append('')
                                            else:
                                                row.append(str(value))
                                        writer.writerow(row)
                                        currentRow += 1
                                
                                processedBlocks += 1
                
                fileInfos.append((outputPath, os.path.getsize(outputPath), planeCount, width, height))
            
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
            data = [[size, planeCount, width, height] for _, size, planeCount, width, height in fileInfos]
            from base import DataBlock
            block = DataBlock(0, 0, 0, data)
            resultFlowData.setBlock(block)
            
            self.flowDatas = [resultFlowData]
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            messagebox.showerror(f"{self.text} エラー", f"ファイル出力に失敗しました: {str(e)}\n\nトラックバック:\n{tb}")
        
        self.reportProgress(context, "完了")