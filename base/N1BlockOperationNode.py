'''
N1BlockOperationNode base class

@author: Masakazu Inoue
'''

from abc import abstractmethod
from .FlowNode import FlowNode
from .FlowData import FlowData
from concurrent.futures import as_completed
from utils.ThreadPool import ProcessExecutor

class N1BlockOperationNode(FlowNode):
    """データ入出力 N:1 のブロック単位計算ノードの基底クラス"""
    
    def __init__(self, canvas, editor, x, y, nodeType, text, **kwargs):
        super().__init__( canvas, editor, x, y, nodeType, text, **kwargs)
        self._baseDataIndex = None

    def getBaseDataIndex(self, inputDatas):
        """基準データのインデックスを返す（サブクラスでオーバーライド可能）"""
        return 0  # デフォルトは最初のデータ
    
    def getResultDimensions(self, inputDatas):
        """結果画像のサイズを決定（サブクラスでオーバーライド可能）"""
        if self._baseDataIndex is None:
            self._baseDataIndex = self.getBaseDataIndex(inputDatas)
        return inputDatas[self._baseDataIndex].getDimensions()
    
    def getUnionDimensions(self, inputDatas):
        """全入力データを包含する最大サイズを計算"""
        maxWidth = max(data.getDimensions()[0] for data in inputDatas)
        maxHeight = max(data.getDimensions()[1] for data in inputDatas)
        return maxWidth, maxHeight
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        inputDatas = []
        
        # このノードに接続されている前のノードからデータを収集
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        if inputDatas:
            # 基準データとサイズを決定（キャッシュを使用）
            if self._baseDataIndex is None:
                self._baseDataIndex = self.getBaseDataIndex(inputDatas)
            baseData = inputDatas[self._baseDataIndex]
            width, height = self.getResultDimensions(inputDatas)
            
            # 結果用のFlowDataを初期化（headersをコピー）
            headers = baseData.headers.copy() if baseData.headers else {}
            flowData = FlowData(headers)
            flowData.setDimensions(width, height)
            
            # 入力データからdisplay_levelsを計算して設定
            displayLevels = self.getDisplayLevels(inputDatas)
            if displayLevels and flowData.headers:
                flowData.headers['display_levels'] = displayLevels
            
            # ブロック単位で並列処理
            futures = []
            for block in flowData.iterateBlocks():
                future = ProcessExecutor.submit(self.processBlock, block, inputDatas)
                futures.append(future)
            
            # 全ブロックの処理完了を待つ
            self.reportProgress(context, "処理中")
            totalBlocks = len(futures)
            for i, future in enumerate(as_completed(futures)):
                resultBlock = future.result()
                if resultBlock:
                    flowData.setBlock(resultBlock)
                self.reportProgress(context, "処理中", i + 1, totalBlocks)
            self.flowDatas = [flowData]
        else:
            self.flowDatas = []
        
        self.reportProgress(context, "完了")
    
    def getDisplayLevels(self, inputDatas):
        """入力データから出力のdisplay_levelsを計算（サブクラスでオーバーライド）
        
        Args:
            inputDatas: 入力FlowDataのリスト
            
        Returns:
            display_levelsの辞書、またはNone
        """
        return None
    
    @abstractmethod
    def processBlock(self, block, inputDatas):
        """単一ブロックの処理（サブクラスで実装）
        
        Args:
            block: 処理対象のブロック
            inputDatas: 入力データのリスト
            
        Returns:
            処理結果のDataBlock
        """
        pass