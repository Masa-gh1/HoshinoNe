'''
BaseWriterNode abstract class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from abc import abstractmethod
import hashlib
import os
import threading
import tkinter as tk

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

if TYPE_CHECKING:
    from base.FlowData import FlowData
    from main.FlowEditor import FlowEditor
    

class BaseWriterNode(FlowNode,ConfigurableNode):
    """ファイル出力ノードの基底クラス"""
    # ノードタイプ
    majorType = _MAJOR_TYPE_IO
    minorType = 'base_writer'
    # ノード名
    name      = 'BaseWriterNode'
    # 入出力タイプ
    ioType    = _IO_TYPE_N0
    outputCat = _OUT_CAT_ETC
    
    def __init__(self, canvas: tk.Canvas, editor: FlowEditor, x: int, y: int, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self.outputFilePath = ""
        self.outputFileTypes = [("files", "*.*")]
        self.defaultOutputExtension = ".txt"
    
    def getText(self) -> str:
        """ノードのテキストを取得"""
        if self.outputFilePath:
            displayText = f"{self.name}\n{os.path.basename(self.outputFilePath)}"
        else:
            displayText = self.name
        return displayText
    
    def getOutputFilePath(self) -> str:
        return self.outputFilePath
    
    def setOutputFilePath(self, outputPath:str):
        self.outputFilePath = outputPath
    
    def store(self, nodeData:dict):
        """ノード固有の設定 nodeData に保存"""
        if not self.outputFilePath:
            filepath = None
        else:
            relapath = self.getRelativePath(self.outputFilePath)
            if relapath:
                filepath = relapath
            else:
                filepath = self.outputFilePath
        nodeData["outputFilePath"] = filepath
        
    def restore(self, nodeData:dict):
        """ノード固有の設定 nodeData から復元"""
        if "outputFilePath" in nodeData:
            filepath = nodeData["outputFilePath"]
            abspath = self.getAbsolutePath(filepath)
            if abspath:
                filepath = abspath

            self.outputFilePath = filepath
    
    def getRelativePath(self, filePath:str) -> str:
        """相対パスを取得"""
        if self.view.editor.currentFlowPath:
            flowDir = os.path.dirname(self.view.editor.currentFlowPath)
            return os.path.relpath(filePath, flowDir)
        else:
            return None
    
    def getAbsolutePath(self, filePath:str) -> str:
        """絶対パスを取得"""
        if self.view.editor.currentFlowPath:
            flowDir = os.path.dirname(self.view.editor.currentFlowPath)
            return os.path.abspath(os.path.join(flowDir, filePath))
        else:
            return None
    
    def getConfigHash(self) -> str:
        config = f"{self.minorType}_{self.outputFilePath}"
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
        self._createFlowData(fileInfos)
        
        self.reportProgress(context, "完了")
        
    def createSettingWindow(self) -> tk.Toplevel:
        """Settings dialogを開く"""
        return BaseWriterSettingsDialog(self.view.editor.root, self)

    def _createFlowData(self, fileInfos:list[tuple[str, int, int, int, int]]):
        """結果FlowDataを生成"""
        from base import DataBlock
        from base import FlowData

        fileNames = [os.path.basename(path) for path, _, _, _, _ in fileInfos]
        
        headers = {
            'type': 'table',
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
    
    def countFlowDataBlocks(self, flowData:FlowData) -> int:
        """FlowDataのブロック数を計算（サブクラスでオーバーライド可能）"""
        return flowData.getBlockCount()
    
    def reportBlockProgress(self, context, message:str="処理中"):
        """ブロック進捗を報告（BaseReaderNodeと同様）"""
        if context and 'totalBlocks' in context:
            with context['processedBlocks_lock']:
                context['processedBlocks'] += 1
                current = context['processedBlocks']
                total = context['totalBlocks']
            self.reportProgress(context, message, current, total)
    
    @abstractmethod
    def processFile(self, filePath:str, flowData:FlowData, context=None) -> tuple[str, int, int, int, int]:
        """単一ファイル出力処理（サブクラスで実装）
        
        Args:
            filePath: 出力ファイルパス
            flowData: 出力する FlowData
            context: 処理コンテキスト
            
        Returns:
            tuple: (filePath, fileSize, planeCount, width, height) or None
        """
        pass

class BaseWriterSettingsDialog(tk.Toplevel):
    def __init__(self, parent:tk.Widget, node:BaseWriterNode):
        super().__init__(parent)
        self.node = node
        
        self.title(f"{node.name}設定")
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
        filepath = self.node.view.editor.openOutputFileSelector(
            parent=self,
            title=f"{self.node.name} - 出力ファイルを選択",
            initialfile=self.node.outputFilePath,
            filetypes=self.node.outputFileTypes,
            defaultextension=self.node.defaultOutputExtension
        )

        if filepath:
            self.pathVar.set(filepath)
    
    def createCustomSettings(self, parent:tk.Widget) -> tk.Frame:
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
        
        self.node.view.onNodeConfigChanged(self.node)
    
    def onClose(self):
        self.destroy()
