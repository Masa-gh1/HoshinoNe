'''
BaseReaderNode abstract class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
import datetime
import hashlib
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

class BaseReaderNode(FlowNode,ConfigurableNode):
    """ファイル読み込みノードの基底クラス"""
    # ノードタイプ
    majorType = _MAJOR_TYPE_IO
    minorType = 'base_reader'
    # ノード名
    name      = 'BaseReaderNode'
    # 入出力タイプ
    ioType    = _IO_TYPE_0N
    outputCat = _OUT_CAT_PRI
    
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self.filePaths = []
        self.fileTypes = [("files", "*.*")]

    def getText(self):
        """ノードのテキストを取得"""
        if self.filePaths:
            if len(self.filePaths) == 1:
                displayText = f"{self.name}\n{os.path.basename(self.filePaths[0])}"
            else:
                dirname = os.path.dirname(self.filePaths[0])
                displayText = f"{self.name}\n{os.path.basename(dirname)} ... 計{len(self.filePaths)}"
        else:
            displayText = f"{self.name}\n未選択"
        return displayText
    
    def getOutputCount(self):
        return len(self.filePaths)

    def setFilePaths(self, filePaths):
        self.filePaths = filePaths
    
    def store(self, nodeData):
        """ノード固有の設定 nodeData に保存"""
        filepaths = []
        for filepath in self.filePaths:
            relapath = self.getRelativePath(filepath)
            if relapath:
                filepaths.append(relapath)
            else:
                filepaths.append(filepath)
        nodeData["filePaths"] = filepaths
    
    def restore(self, nodeData):
        """ノード固有の設定 nodeData から復元"""
        if "filePaths" in nodeData:
            filepaths = []
            for filepath in nodeData["filePaths"]:
                abspath = self.getAbsolutePath(filepath)
                if abspath:
                    filepaths.append(abspath)
                else:
                    filepaths.append(filepath)

            self.filePaths = filepaths
    
    def getRelativePath(self, filePath):
        """相対パスを取得"""
        if self.view.editor.currentFlowPath:
            flowDir = os.path.dirname(self.view.editor.currentFlowPath)
            return os.path.relpath(filePath, flowDir)
        else:
            return None
    
    def getAbsolutePath(self, filePath):
        """絶対パスを取得"""
        if self.view.editor.currentFlowPath:
            flowDir = os.path.dirname(self.view.editor.currentFlowPath)
            return os.path.abspath(os.path.join(flowDir, filePath))
        else:
            return None

    def getConfigHash(self):
        """基本的な設定ハッシュ（サブクラスでオーバーライド）"""
        config = f"{self.minorType}_{'|'.join(self.filePaths)}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def process(self, context=None):
        """ブロック単位進捗対応の共通処理フロー"""
        self.reportProgress(context, "開始")
        
        # 事前に全ファイルのブロック数を計算
        totalBlocks = 0
        
        for filePath in self.filePaths:
            totalBlocks += self.countFileBlocks(filePath)
        
        # contextにブロック情報を追加
        if context:
            context['totalBlocks'] = totalBlocks
            context['processedBlocks'] = 0
            context['processedBlocks_lock'] = threading.Lock()
        
        # 全ファイルを処理
        resultFlowDatas = []
        
        for fileIdx, filePath in enumerate(self.filePaths):
            flowData = self.processFile(filePath, context)
            if flowData:
                if isinstance(flowData, list):
                    resultFlowDatas.extend(flowData)
                else:
                    resultFlowDatas.append(flowData)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def createSettingWindow(self):
        """Settings dialogを開く"""
        return BaseReaderSettingsDialog(self.view.editor.root, self)
    
    def countFileBlocks(self, filePath):
        """ファイルのブロック数を計算（サブクラスでオーバーライド）
        
        Args:
            filePath: ブロック数を計算するファイルのパス
            
        Returns:
            ブロック数（デフォルトは1）
        """
        return 1
    
    def reportBlockProgress(self, context, message="処理中"):
        """ブロック進捗を報告（スレッドセーフ）"""
        if context and 'totalBlocks' in context:
            with context['processedBlocks_lock']:
                context['processedBlocks'] += 1
                current = context['processedBlocks']
                total = context['totalBlocks']
            self.reportProgress(context, message, current, total)
    
    @abstractmethod
    def processFile(self, filePath, context=None):
        """単一ファイルの処理（サブクラスで実装）
        
        Args:
            filePath: 処理するファイルのパス
            context: 処理コンテキスト
            
        Returns:
            FlowData または FlowDataのリスト、処理失敗時はNone
        """
        pass
    
    def getFileInfo(self, filePath):
        """ファイル固有情報を取得（サブクラスでオーバーライド）
        
        Args:
            filePath: 情報を取得するファイルのパス
            
        Returns:
            ファイル情報の辞書
        """
        try:
            stat = os.stat(filePath)
            return {
                'filePath': filePath,
                'mtime': stat.st_mtime,
                'size': stat.st_size
            }
        except Exception:
            return {
                'filePath': filePath,
                'mtime': None,
                'size': None
            }

class BaseReaderSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        
        self.title(f"{node.name}設定")
        self.geometry("600x500")
        
        # ファイルパスのコピーを作成
        self.selectedFilePaths = list(self.node.filePaths) if self.node.filePaths else []
        
        # メインフレーム（左右分割）
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左側：ファイルリスト
        leftFrame = tk.Frame(mainFrame)
        leftFrame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(leftFrame, text="ファイル:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        # ファイルリスト表示用スクロールエリア
        fileListFrame = tk.Frame(leftFrame)
        fileListFrame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # ファイルリスト表示（動的に設定）
        columns = self.getColumns()
        self.fileTreeview = ttk.Treeview(fileListFrame, columns=columns, show='headings', height=15)
        
        # 列ヘッダー設定（動的に設定）
        headers = self.getColumnHeaders()
        for col_id, header_text in headers.items():
            self.fileTreeview.heading(col_id, text=header_text)
        
        # 列幅設定（動的に設定）
        widths = self.getColumnWidths()
        for col_id, width_info in widths.items():
            self.fileTreeview.column(col_id, **width_info)
        
        fileScrollbar = ttk.Scrollbar(fileListFrame, orient=tk.VERTICAL, command=self.fileTreeview.yview)
        self.fileTreeview.configure(yscrollcommand=fileScrollbar.set)
        
        self.fileTreeview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fileScrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ファイルリストを更新
        self.updateFileList()
        
        # ファイル操作ボタン
        buttonFrame = tk.Frame(leftFrame)
        buttonFrame.pack(anchor="w", pady=5)
        
        tk.Button(buttonFrame, text="追加", command=self.addFiles).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(buttonFrame, text="削除", command=self.removeFiles).pack(side=tk.LEFT, padx=(0, 5))
        sortButton = self.createSortButton(buttonFrame)
        if sortButton:
            sortButton.pack(side=tk.LEFT)
        
        # 右側：カスタム設定項目（設定がある場合のみ表示）
        customFrame = self.createCustomSettings(None)
        if customFrame:
            rightFrame = tk.Frame(mainFrame, width=250)
            rightFrame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
            rightFrame.pack_propagate(False)
            
            tk.Label(rightFrame, text="設定:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
            
            # カスタムフレームを再作成して右フレームに配置
            customFrame = self.createCustomSettings(rightFrame)
            customFrame.pack(fill=tk.BOTH, expand=True)
        
        # ボタン
        bottomButtonFrame = tk.Frame(self)
        bottomButtonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(bottomButtonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(bottomButtonFrame, text="閉じる", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def updateFileList(self):
        # 既存項目をクリア
        for item in self.fileTreeview.get_children():
            self.fileTreeview.delete(item)
        
        if self.selectedFilePaths:
            for filePath in self.selectedFilePaths:
                # フォーマットされた情報を取得
                info = self.getFormalFileInfo(filePath)
                
                # 列構成に応じて値を設定
                columns = self.getColumns()
                values = [info.get(col, '') for col in columns]
                
                self.fileTreeview.insert('', 'end', values=values)
        else:
            columns = self.getColumns()
            empty_info = {'filename': '未選択'}
            values = [empty_info.get(col, '') for col in columns]
            self.fileTreeview.insert('', 'end', values=values)
    
    def addFiles(self):
        filePaths = self.node.view.editor.openFilesSelector(
            parent=self,
            title=f"{self.node.name} - ファイルを追加",
            filetypes=self.node.fileTypes
        )
        
        if filePaths:
            # 重複を除いて追加
            for filePath in filePaths:
                if filePath not in self.selectedFilePaths:
                    self.selectedFilePaths.append(filePath)
            
            self.updateFileList()
    
    def removeFiles(self):
        selected_items = self.fileTreeview.selection()
        if not selected_items:
            return
        
        # 選択されたアイテムのインデックスを取得
        indices_to_remove = []
        for item in selected_items:
            index = self.fileTreeview.index(item)
            indices_to_remove.append(index)
        
        # 逆順で削除
        for index in sorted(indices_to_remove, reverse=True):
            if 0 <= index < len(self.selectedFilePaths):
                del self.selectedFilePaths[index]
        
        self.updateFileList()
    
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
        # ファイルパスの更新
        self.node.filePaths = self.selectedFilePaths
        
        # カスタム設定の適用
        self.customOnApply()
        
        self.node.view.onNodeConfigChanged(self.node)
    
    def getColumns(self):
        """列構成を取得（サブクラスでオーバーライド）"""
        return ('filename', 'datetime', 'size')
    
    def getColumnHeaders(self):
        """列ヘッダーを取得（サブクラスでオーバーライド）"""
        return {
            'filename': 'ファイル名',
            'datetime': '更新日時',
            'size': 'ファイルサイズ'
        }
    
    def getColumnWidths(self):
        """列幅設定を取得（サブクラスでオーバーライド）"""
        return {
            'filename': {'width':  40, 'stretch': True},
            'datetime': {'width': 120, 'stretch': False},
            'size': {'width': 80, 'stretch': False, 'anchor': 'e'}
        }
    
    def getFormalFileInfo(self, filePath):
        """ファイルの表示用文字列を取得（サブクラスでオーバーライド）"""
        fileInfo = self.node.getFileInfo(filePath)
        
        # 更新日時
        if fileInfo.get('mtime'):
            dt = datetime.datetime.fromtimestamp(fileInfo['mtime'])
            datetime_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            datetime_str = '情報取得失敗'
        
        # ファイルサイズ
        size = fileInfo.get('size')
        if size is not None:
            size_str = f"{size:,}"
        else:
            size_str = ''
        
        return {
            'filename': os.path.basename(fileInfo.get('filePath', filePath)),
            'datetime': datetime_str,
            'size': size_str
        }
    
    def sortByFilename(self):
        if len(self.selectedFilePaths) <= 1:
            return
        
        try:
            self.selectedFilePaths.sort(key=lambda x: os.path.basename(x).lower())
            self.updateFileList()
        except Exception as e:
            messagebox.showerror(f"{self.node.name} エラー", f"ソートに失敗しました: {str(e)}")
    
    def createSortButton(self, parent):
        """ソートボタンを作成（サブクラスでオーバーライド）"""
        return tk.Button(parent, text="ファイル名ソート", command=self.sortByFilename)
    
    def onClose(self):
        self.destroy()
