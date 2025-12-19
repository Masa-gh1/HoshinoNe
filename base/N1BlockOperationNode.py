'''
N1BlockOperationNode base class

@author: Masakazu Inoue
'''

from .FlowNode import FlowNode
from .FlowData import FlowData
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MAX_WORKERS

class N1BlockOperationNode(FlowNode):
    """データ入出力 N:1 のブロック単位計算ノードの基底クラス"""

    def getBaseDataIndex(self, inputDatas):
        """基準データのインデックスを返す（サブクラスでオーバーライド可能）"""
        return 0  # デフォルトは最初のデータ
    
    def getResultDimensions(self, inputDatas):
        """結果画像のサイズを決定（サブクラスでオーバーライド可能）"""
        baseIndex = self.getBaseDataIndex(inputDatas)
        return inputDatas[baseIndex].getDimensions()
    
    def getUnionDimensions(self, inputDatas):
        """全入力データを包含する最大サイズを計算"""
        maxWidth = max(data.getDimensions()[0] for data in inputDatas)
        maxHeight = max(data.getDimensions()[1] for data in inputDatas)
        return maxWidth, maxHeight
    
    def process(self, context):
        self.reportProgress(context, "開始")
        inputDatas = []
        
        # このノードに接続されている前のノードからデータを収集
        for node in context['input_nodes']:
            inputDatas.extend(node.flowDatas)
        
        if inputDatas:
            # 基準データとサイズを決定
            baseIndex = self.getBaseDataIndex(inputDatas)
            baseData = inputDatas[baseIndex]
            width, height = self.getResultDimensions(inputDatas)
            
            # 結果用のFlowDataを初期化
            flowData = FlowData(baseData.headers)
            flowData.setDimensions(width, height)
            
            # ブロック単位で処理（並列化）
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for block in flowData.iterateBlocks():
                    future = executor.submit(self.processBlock, block, inputDatas)
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
    
    def processBlock(self, block, inputDatas):
        """単一ブロックの処理（サブクラスでオーバーライド）"""
        raise NotImplementedError("サブクラスで実装してください")