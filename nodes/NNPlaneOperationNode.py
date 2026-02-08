'''
NNPlaneOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from base import FlowNode

class NNPlaneOperationNode(FlowNode):
    """データ入出力 N:N の計算ノードの基底クラス"""
    # ノードタイプ
    majorType = 'NN_operation'
    minorType = 'NN_operation'
    # ノード名
    name      = 'NNOperationNode'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_PAS

    def process(self, context=None):
        from utils import measurement as mes
        from utils.ThreadPool import ParallelExecutor
        
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
        
        futureToDatas = {}
        futureCountPerDatas = {}
        
        for inputData in processedInputs:
            # 結果用の FlowData を初期化
            flowData = self.createFlowData(inputData)
            futureCountPerDatas[flowData] = 0

            # プレーン単位で並列処理
            for planeIndex in range(inputData.getPlaneCount()):
                future = ParallelExecutor.submit(self, mes.elapsedThreading, self.processPlane, inputData, planeIndex)
                futureToDatas[future] = flowData
                futureCountPerDatas[flowData] += 1
        
        # 全プレーンの処理完了を待つ
        self.reportProgress(context, "処理中")
        resultFlowDatas = []
        totalPlaneCount = len(futureToDatas)
        for i, future in enumerate(as_completed(futureToDatas)):
            resultBlocks = future.result()
            flowData = futureToDatas.pop(future)
            for resultBlock in resultBlocks:
                flowData.setBlock(resultBlock)
            
            futureCountPerDatas[flowData] -= 1
            if 0 == futureCountPerDatas[flowData]:
                # 全部プレーンの処理が終わった flowData を結果配列に追加
                futureCountPerDatas.pop(flowData)
                resultFlowDatas.append(flowData)
            
            self.reportProgress(context, "処理中", i + 1, totalPlaneCount)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理 (サブクラスでオーバーライド可能)
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            処理対象データのリスト
        """
        return inputDatas
    
    def createFlowData(self, inputData):
        """LazyFlowDataを作成 (サブクラスでオーバーライド可能)
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            LazyFlowData
        """
        from base import FlowData

        # headers を生成
        headers = inputData.headers.copy()
        headers.update(self.processHeaders(inputData))

        # サイズを決定
        width, height = inputData.getDimensions()
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)

        return flowData

    def processHeaders(self, inputData):
        """
        出力 FlowData の headers を処理 (サブクラスでオーバーライド可能)
        
        Args:
            inputFlowData: 入力FlowData
        """
        return {}
    
    @abstractmethod
    def processPlane(self, flowData, planeIndex):
        """データの処理 (サブクラスで実装)
        
        Args:
            flowData: 処理対象のデータ
            
        Returns:
            処理結果の FlowData
        """
        pass
