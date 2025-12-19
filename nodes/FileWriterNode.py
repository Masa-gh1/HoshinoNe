'''
FileWriterNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import csv
import sys
import os
import traceback
from tkinter import filedialog, messagebox
from base import BaseWriterNode, FlowData
from config import MAX_WORKERS, BLOCK_SIZE

class FileWriterNode(BaseWriterNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "file_writer", "ファイル書き出し", **kwargs)
        self.outputFileTypes = [("CSV files", "*.csv"), ("All files", "*.*")]
        self.defaultOutputExtension = ".csv"
        
    def processFile(self, filePath, flowData, context=None):
        """単一ファイル出力処理"""
        try:
            width, height = flowData.getDimensions()
            planeCount = flowData.getPlaneCount()
            
            if width == 0 or height == 0:
                return None
            
            planeNames = flowData.headers.get('planes', ['data']) if flowData.headers else ['data']
            
            with open(filePath, 'w', newline='', encoding='utf-8') as f:
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
                            
                            self.reportBlockProgress(context)
            
            fileSize = os.path.getsize(filePath)
            return (filePath, fileSize, planeCount, width, height)
            
        except Exception as e:
            raise Exception(f"ファイル出力エラー ({filePath}): {str(e)}")
