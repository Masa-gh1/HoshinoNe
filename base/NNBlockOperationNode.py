'''
NNBlockOperationNode base class

@author: Masakazu Inoue
'''

from abc import abstractmethod
from .FlowNode import FlowNode
from .FlowData import FlowData
from concurrent.futures import as_completed
from utils.ThreadPool import ProcessExecutor

class NNBlockOperationNode(FlowNode):
    """データ入出力 N:N のブロック単位計算ノードの基底クラス"""

    def process(self, context=None):
        self.reportProgress(context, "開始")
        inputDatas = []
        
        # このノードに接続されている前のノードからデータを収集
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        if inputDatas:
            resultFlowDatas = []
            futureToDatas = {}
            
            for inputData in inputDatas:
                # 結果用のFlowDataを初期化
                width, height = inputData.getDimensions()
                flowData = FlowData(inputData.headers)
                flowData.setDimensions(width, height)
                resultFlowDatas.append(flowData)
                
                # ブロック単位で並列処理
                for block in inputData.iterateBlocks():
                    future = ProcessExecutor.submit(self.processBlock, block)
                    futureToDatas[future] = flowData
            
            # 全ブロックの処理完了を待つ
            self.reportProgress(context, "処理中")
            totalBlocks = len(futureToDatas)
            for i, future in enumerate(as_completed(futureToDatas)):
                resultBlock = future.result()
                if resultBlock:
                    futureToDatas[future].setBlock(resultBlock)
                self.reportProgress(context, "処理中", i + 1, totalBlocks)
            
            self.flowDatas = resultFlowDatas
        else:
            self.flowDatas = []
        
        self.reportProgress(context, "完了")
    
    @abstractmethod
    def processBlock(self, block):
        """単一ブロックの処理（サブクラスで実装）
        
        Args:
            block: 処理対象のブロック
            
        Returns:
            処理結果のDataBlock
        """
        pass