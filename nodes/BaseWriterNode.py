'''
BaseWriterNode abstract class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
import hashlib
import os
import threading
import tkinter as tk
from tkinter import filedialog
from base import DataBlock
from base import FlowData
from base import FlowNode
from nodes import ConfigurableNode

class BaseWriterNode(FlowNode,ConfigurableNode):
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
            context['processedBlocks_lock'] = threading.Lock()
        
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
        
    def onEdit(self):
        """Settings dialogを開く"""
        return BaseWriterSettingsDialog(self.editor.root, self)

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
        
        resultFlowData = FlowData(headers)
        resultFlowData.setDimensions(4, len(fileInfos))
        data = [[size, planeCount, width, height] for _, size, planeCount, width, height in fileInfos]
        block = DataBlock(data, 0, 0, 0)
        resultFlowData.setBlock(block)
        
        self.flowDatas = [resultFlowData]
    
    def countFlowDataBlocks(self, flowData):
        """FlowDataのブロック数を計算（サブクラスでオーバーライド可能）"""
        return flowData.getBlockCount()
    
    def reportBlockProgress(self, context, message="処理中"):
        """ブロック進捗を報告（BaseReaderNodeと同様）"""
        if context and 'totalBlocks' in context:
            with context['processedBlocks_lock']:
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

class BaseWriterSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        
        self.title(f"{node.text}設定")
        self.geometry("500x300")
        
        # メインフレーム
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 出力ファイルパス
        pathFrame = tk.Frame(mainFrame)
        pathFrame.pack(fill=tk.X, pady=5)
        
        tk.Label(pathFrame, text="出力ファイル:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        fileFrame = tk.Frame(pathFrame)
        fileFrame.pack(fill=tk.X, pady=2)
        
        self.pathVar = tk.StringVar(value=self.node.outputFilePath)
        pathEntry = tk.Entry(fileFrame, textvariable=self.pathVar, state="readonly")
        pathEntry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Button(fileFrame, text="参照", command=self.browseFile).pack(side=tk.RIGHT, padx=(5, 0))
        
        # カスタム設定項目
        customFrame = self.createCustomSettings(mainFrame)
        if customFrame:
            customFrame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # ボタン
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def browseFile(self):
        dialog = filedialog.asksaveasfilename(
            title=f"{self.node.text} - 出力ファイルを選択",
            filetypes=self.node.outputFileTypes,
            defaultextension=self.node.defaultOutputExtension
        )
        if dialog:
            self.pathVar.set(dialog)
    
    def createCustomSettings(self, parent):
        """カスタム設定項目を作成（サブクラスでオーバーライド）
        
        Returns:
            作成したフレーム、またはNone
        """
        return None
    
    def customOnApply(self):
        """カスタム設定の適用（サブクラスでオーバーライド）"""
        pass
    
    def onApply(self):
        # 出力ファイルパスの更新
        self.node.setOutputFilePath(self.pathVar.get())
        
        # カスタム設定の適用
        self.customOnApply()
        
        self.node.updateNodeText()
        
        newHash = self.node.getConfigHash()
        if newHash != self.node._lastConfigHash:
            self.node.editor.onNodeConfigChanged(self.node)
    
    def onClose(self):
        self.destroy()
