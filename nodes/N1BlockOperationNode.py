'''
N1BlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
from concurrent.futures import as_completed

from base import FlowNode
from base import FlowData
from utils.ThreadPool import ProcessExecutor

class N1BlockOperationNode(FlowNode):
    """データ入出力 N:1 のブロック単位計算ノードの基底クラス"""
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputDatas = []
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        if not inputDatas:
            self.flowDatas = []
            self.reportProgress(context, "完了")
            return
        
        # 前処理
        processedInputs = self.preprocessInputs(inputDatas)
        
        if not processedInputs:
            self.flowDatas = processedInputs
        else:
            # 基準データとサイズを決定
            baseDataIndex = self.getBaseDataIndex(processedInputs)
            baseData = processedInputs[baseDataIndex]
            width, height = self.getResultDimensions(processedInputs)
            
            # 結果用のFlowDataを初期化（headersをコピー）
            headers = baseData.headers.copy() if baseData.headers else {}
            flowData = FlowData(headers)
            flowData.setDimensions(width, height)
            
            # display_levelsをheaders経由で設定
            self.setupDisplayLevels(flowData, processedInputs)
            
            # ブロック単位で並列処理
            futures = []
            for block in flowData.iterateBlocks():
                future = ProcessExecutor.submit(self.processBlock, block, processedInputs)
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
        
        self.reportProgress(context, "完了")
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理（サブクラスでオーバーライド可能）
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            処理対象データのリスト
        """
        return inputDatas
    
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
        width, height = inputDatas[0].getDimensions()
        for data in inputDatas[1:]:
            w, h = data.getDimensions()
            width  = max(width, w)
            height = max(height, h)
        return width, height
    
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
    
    def setupDisplayLevels(self, outputFlowData, inputDatas):
        """出力FlowDataのdisplay_levelsを設定（サブクラスでオーバーライド可能）
        
        Args:
            outputFlowData: 出力FlowData
            inputDatas: 入力FlowDataのリスト
        """
        # デフォルトは基準データのままコピー
        if self._baseDataIndex is not None and inputDatas:
            baseData = inputDatas[self._baseDataIndex]
            if baseData.headers and 'display_levels' in baseData.headers:
                outputFlowData.headers['display_levels'] = baseData.headers['display_levels']
    
