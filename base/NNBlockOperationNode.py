'''
NNBlockOperationNode base class

@author: Masakazu Inoue
'''

from .FlowNode import FlowNode
from .FlowData import FlowData
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MAX_WORKERS

class NNBlockOperationNode(FlowNode):
    """データ入出力 N:N のブロック単位計算ノードの基底クラス"""

    def process(self, context):
        self.reportProgress(context, "開始")
        inputDatas = []
        
        # このノードに接続されている前のノードからデータを収集
        for node in context['input_nodes']:
            inputDatas.extend(node.flowDatas)
        
        if inputDatas:
            inputDatas.sort(key=lambda data: data.getDiagonal2(), reverse=True)
            
            # ブロック単位で処理（並列化）
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                resultFlowDatas = []
                futureToDatas = {}
                
                for inputData in inputDatas:
                    # 結果用のFlowDataを初期化
                    width, height, planeCount = inputData.getDimensions()
                    flowData = FlowData(inputData.headers)
                    flowData.setDimensions(width, height, planeCount)
                    resultFlowDatas.append(flowData)
                    
                    for block in inputData.iterateBlocks():
                        future = executor.submit(self.processBlock, block)
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
    
    def processBlock(self, block):
        """単一ブロックの処理（サブクラスでオーバーライド）"""
        raise NotImplementedError("サブクラスで実装してください")