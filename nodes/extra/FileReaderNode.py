'''
FileReaderNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import csv
import os
from tkinter import messagebox
import tkinter

from config import BLOCK_SIZE
from base import FlowData, DataBlock
from nodes import BaseReaderSettingsDialog
from nodes import BaseReaderNode

class FileReaderNode(BaseReaderNode):
    # ノードタイプ
    #majorType = スーパークラスを継承
    minorType = 'file_reader'
    # ノード名
    name      = 'ファイル読み込み'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)

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
    
    def createSettingWindow(self):
        return FileReaderSettingsDialog(self.view.editor.root, self)
    
    def processFile(self, filePath, context=None):
        """単一CSVファイルの処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        # フォーマットチェック
        dataType = 'table'
        planeNames = {} # プレーン名と行番号のマップ
        colHeaders = []
        rowHeaders = []
        width  = 0
        height = 0
        with open(filePath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            isCommentL = True
            planeName  = ''
            i = 0
            for i, row in enumerate(reader):
                if not row:
                    continue
            
                # プレーン名 or コメントをチェック
                isComment = row[0].startswith('#')
                if not isCommentL and isComment:
                    # コメントの先頭
                    if 0 < i:
                        p = planeNames[planeName]
                        planeNames[planeName] = (p, i) # 前のプレーンの末行番号を記録
                        height = max(height, i - p)
                    planeName = row[0][1:].strip()  # '#'を除去、最後の # をプレーン名とする
                elif isComment:
                    # コメント行
                    planeName = row[0][1:].strip()  # '#'を除去、最後の # をプレーン名とする
                elif isCommentL:
                    # データ行の先頭
                    planeNames[planeName] = i # 行番号を記録
                    if 1 == len(planeNames):
                        # 最初のプレーンの 1 行目を取得
                        colHeaders = row
                        rowHeaders.append(row[0])
                        width = max(width, len(row))
                else:
                    # データ行
                    if 1 == len(planeNames):
                        # 最初のプレーンの 1 列目を取得
                        rowHeaders.append(row[0])
                        width = max(width, len(row))
                    
                isCommentL = isComment
            
            if not isCommentL:
                p = planeNames[planeName]
                planeNames[planeName] = (p, i + 1) # 前のプレーンの末行番号を記録
                height = max(height, i + 1 - p)

        # 列ヘッダと行ヘッダの有無を判断
        if self.isAllFloat(colHeaders) and self.isAllFloat(rowHeaders):
            dataType   = 'tensor'
            colHeaders = []
            rowHeaders = []
        elif self.isAllFloat(colHeaders):
            dataType   = 'table'
            width     -= 1
            colHeaders = []
        elif self.isAllFloat(rowHeaders):
            dataType   = 'table'
            width      = len(colHeaders)
            height    -= 1
            rowHeaders = []
            planeNames = {name:(p+1,q) for name,(p,q) in planeNames.items()}
        else:
            dataType   = colHeaders[0]
            width     -= 1
            height    -= 1
            colHeaders = colHeaders[1:]
            rowHeaders = rowHeaders[1:]
            planeNames = {name:(p+1,q) for name,(p,q) in planeNames.items()}

        # FlowDataを作成
        headers = {
            'category'   : self.getOutputCategory(),
            'type'       : dataType,
            'mode'       : '2D',
            'planes'     : planeNames.keys() if planeNames else [dataType],
            'columns'    : colHeaders,
            'lines'      : rowHeaders,
            'source_file': self.getRelativePath(filePath),
        }
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)
        
        with open(filePath, 'r', encoding='utf-8') as f:
            reader = enumerate(csv.reader(f))
            i = -1
            planeIter = iter(enumerate(planeNames.items()))
            for planeIndex, (planeName, (rowP, rowQ)) in planeIter:
                while i < rowP - 1:
                    i, row = next(reader, (i+1,None))

                while i < rowQ - 1:
                    y = i - rowP + 1
                    data = nh.empty((min(BLOCK_SIZE, height), width))
                    for j, (i, row) in enumerate(reader):
                        data[j,:] = nh.array(row[1:] if rowHeaders else row)
                        if BLOCK_SIZE - 1 <= j or rowQ - 1 <= i:
                            break
                    for x in range(0, width, BLOCK_SIZE):
                        dataBlock = DataBlock(data[:, x:x+BLOCK_SIZE], planeIndex, x, y)
                        flowData.setBlock(dataBlock)
                        self.reportBlockProgress(context)
        return flowData
    
    def isAllFloat(self, values:list) -> bool:
        """リスト内のすべての値が浮動小数点数と解釈できるかをチェック"""
        try:
            for value in values:
                float(value)
            return True
        except ValueError:
            return False
    
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
            messagebox.showerror(f"{self.node.name} エラー", f"ソートに失敗しました: {str(e)}")
