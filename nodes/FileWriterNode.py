'''
FileWriterNode class

@author: Masakazu Inoue
'''

import csv
import os
from tkinter import filedialog, messagebox
from base import FlowNode, FlowData
from config import MAX_WORKERS, BLOCK_SIZE

class FileWriterNode(FlowNode):
    def __init__(self, canvas, editor, x, y, nonDialog=False, **kwargs):
        self.filePath = ""
        super().__init__(canvas, editor, x, y, "file_writer", "ファイル書き出し")
        self.filetypes = [("CSV files", "*.csv"), ("All files", "*.*")]
        self.defaultextension = ".csv"
        if not nonDialog:
            self.selectOutputFile()
    
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
        
        # 前のノードからデータを収集（最初のデータを使用）
        flowData = None
        for node in context['input_nodes']:
            flowData = node.flowDatas[0]
        
        if not flowData:
            messagebox.showerror("エラー", "データがありません")
            return
        
        try:
            width, height, planeCount = flowData.getDimensions()
            planeNames = flowData.headers.get('planes', ['data']) if flowData.headers else ['data']
            totalBlocks = ((height + BLOCK_SIZE - 1) // BLOCK_SIZE) * ((width + BLOCK_SIZE - 1) // BLOCK_SIZE) * planeCount
            processedBlocks = 0
            
            with open(self.filePath, 'w', newline='', encoding='utf-8') as f:
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
                        
            # 処理完了を示すためにflowDatasを設定
            self.flowDatas = [FlowData()]
        except Exception as e:
            messagebox.showerror("エラー", f"ファイル出力に失敗しました: {str(e)}")
        
        self.reportProgress(context, "完了")