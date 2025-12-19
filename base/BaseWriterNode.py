'''
BaseWriterNode abstract class

@author: Masakazu Inoue
'''

import hashlib
import os
import threading
import tkinter as tk
from abc import abstractmethod
from tkinter import filedialog
from .FlowNode import FlowNode

class BaseWriterNode(FlowNode):
    """ファイル出力ノードの基底クラス"""
    
    def __init__(self, canvas, editor, x, y, nodeType, text, **kwargs):
        super().__init__(canvas, editor, x, y, nodeType, text, **kwargs)
        self.outputFilePath = ""
        self.outputFileTypes = [("files", "*.*")]
        self.defaultOutputExtension = ".txt"
    
    def getColor(self):
        return self._color_io
    
    def setOutputFilePath(self, outputPath):
        self.outputFilePath = outputPath
    
    def updateNodeText(self):
        if self.outputFilePath:
            displayText = f"{self.text}\n{os.path.basename(self.outputFilePath)}"
        else:
            displayText = self.text
        self.editor.updateNodeText(self, displayText)
    
    def store(self, nodeData):
        """相対パスで保存"""
        flowDir = os.path.dirname(self.editor.currentFlowPath)
        relativePath = os.path.relpath(self.outputFilePath, flowDir)
        nodeData["outputFilePath"] = relativePath
    
    def restore(self, nodeData):
        """絶対パスに復元"""
        if "outputFilePath" in nodeData:
            flowDir = os.path.dirname(self.editor.currentFlowPath)
            self.outputFilePath = os.path.abspath(os.path.join(flowDir, nodeData["outputFilePath"]))
            self.updateNodeText()
    
    def getConfigHash(self):
        config = f"{self.type}_{self.outputFilePath}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def process(self, context=None):
        """出力処理の共通フロー"""
        if not self.outputFilePath:
            raise ValueError("出力ファイルが指定されていません")
        
        self.reportProgress(context, "開始")
        
        # 全入力ノードからflowDataを収集
        flowDatas = []
        for node in self.inputNodes:
            flowDatas.extend(node.flowDatas)
        
        if not flowDatas:
            return
        
        # 事前に全データのブロック数を計算
        totalBlocks = 0
        for flowData in flowDatas:
            totalBlocks += self.countFlowDataBlocks(flowData)
        
        # contextにブロック情報を追加
        if context:
            context['totalBlocks'] = totalBlocks
            context['processedBlocks'] = 0
            context['_block_lock'] = threading.Lock()
        
        # 複数データの場合はファイル名に連番を付加
        fileInfos = []
        for dataIdx, flowData in enumerate(flowDatas):
            if len(flowDatas) == 1:
                outputPath = self.outputFilePath
            else:
                base, ext = os.path.splitext(self.outputFilePath)
                outputPath = f"{base}_{dataIdx}{ext}"
            
            fileInfo = self.processFile(outputPath, flowData, context)
            if fileInfo:
                fileInfos.append(fileInfo)
        
        # 結果データを生成
        self._createResultFlowData(fileInfos)
        
        self.reportProgress(context, "完了")
    
    def _createResultFlowData(self, fileInfos):
        """結果FlowDataを生成"""
        fileNames = [os.path.basename(path) for path, _, _, _, _ in fileInfos]
        
        headers = {
            'type': 'matrix',
            'mode': '2D',
            'columns': ['size', 'planeCount', 'width', 'height'],
            'lines': fileNames,
            'planes': ['file info']
        }
        
        from .FlowData import FlowData
        from .DataBlock import DataBlock
        resultFlowData = FlowData(headers)
        resultFlowData.setDimensions(4, len(fileInfos))
        data = [[size, planeCount, width, height] for _, size, planeCount, width, height in fileInfos]
        block = DataBlock(0, 0, 0, data)
        resultFlowData.setBlock(block)
        
        self.flowDatas = [resultFlowData]
    
    def countFlowDataBlocks(self, flowData):
        """FlowDataのブロック数を計算（サブクラスでオーバーライド可能）"""
        return flowData.getBlockCount()
    
    def reportBlockProgress(self, context, message="処理中"):
        """ブロック進捗を報告（BaseReaderNodeと同様）"""
        if context and 'totalBlocks' in context:
            with context['_block_lock']:
                context['processedBlocks'] += 1
                current = context['processedBlocks']
                total = context['totalBlocks']
            self.reportProgress(context, message, current, total)
    
    @abstractmethod
    def processFile(self, filePath, flowData, context=None):
        """単一ファイル出力処理（サブクラスで実装）
        
        Args:
            filePath: 出力ファイルパス
            flowData: 出力するFlowData
            context: 処理コンテキスト
            
        Returns:
            tuple: (filePath, fileSize, planeCount, width, height) or None
        """
        pass
    
    def onEdit(self):
        """Settings dialogを開く"""
        dialog = filedialog.asksaveasfilename(
            title=f"{self.text} - 出力ファイルを選択",
            filetypes=self.outputFileTypes,
            defaultextension=self.defaultOutputExtension
        )
        if dialog:
            self.setOutputFilePath(dialog)
            self.updateNodeText()