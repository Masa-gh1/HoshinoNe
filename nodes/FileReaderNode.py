'''
FileReaderNode class

@author: Masakazu Inoue
'''

import csv
import hashlib
import os
import datetime
from tkinter import filedialog, messagebox
import tkinter
from base import BaseReaderNode, FlowData, DataBlock
from base.BaseReaderNode import BaseReaderSettingsDialog
from config import MAX_WORKERS, BLOCK_SIZE

class FileReaderNode(BaseReaderNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "file_reader", "ファイル読み込み")
        self.fileTypes = [("CSV files", "*.csv")]
    
    def countFileBlocks(self, filePath):
        """ファイルサイズベースでブロック数を推定"""
        try:
            fileSize = os.path.getsize(filePath)
            # 1KBあたり1ブロックとして推定（調整可能）
            estimatedBlocks = max(1, fileSize // 1024)
            return estimatedBlocks
        except:
            return 1
    
    def onEdit(self):
        if hasattr(self, '_settings_dialog') and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
        else:
            self._settings_dialog = FileReaderSettingsDialog(self.editor.root, self)
    
    def processFile(self, filePath, context=None):
        """単一CSVファイルの処理"""
        with open(filePath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            
            # プレーン情報を初期化
            currentPlane = 0
            planeNames = []
            planeData = []
            dataType = 'matrix'
            headers = []
            
            for row in reader:
                if not row:
                    continue
                
                # プレーンマーカーをチェック
                if row[0].startswith('#'):
                    planeName = row[0][1:].strip()  # '#'を除去
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
            
            # FlowDataを作成してブロック単位で保存
            flowHeaders = {'type': dataType, 'mode': '2D', 'columns': headers, 'lines': rowHeaders}
            if planeNames:
                flowHeaders['planes'] = planeNames
            else:
                flowHeaders['planes'] = [dataType]
            flowData = FlowData(flowHeaders)
            
            if planeData:
                # 複数プレーンの場合
                height = len(planeData[0]) if planeData[0] else 0
                width = len(planeData[0][0]) if height > 0 else 0
                flowData.setDimensions(width, height)
                
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
                                self.reportBlockProgress(context)
                return flowData
            else:
                return None

class FileReaderSettingsDialog(BaseReaderSettingsDialog):
    def createSortButton(self, parent):
        return tkinter.Button(parent, text="更新日時ソート", command=self.sortByTimestamp)
    
    def sortByTimestamp(self):
        if len(self.selectedFilePaths) <= 1:
            return
        
        try:
            self.selectedFilePaths.sort(key=lambda x: os.path.getmtime(x))
            self.updateFileList()
        except Exception as e:
            messagebox.showerror(f"{self.node.text} エラー", f"ソートに失敗しました: {str(e)}")
