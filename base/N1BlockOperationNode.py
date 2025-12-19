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

    def process(self, context):
        self.reportProgress(context, "開始")
        inputDatas = []
        
        # このノードに接続されている前のノードからデータを収集
        for node in context['input_nodes']:
            inputDatas.extend(node.flowDatas)
        
        if inputDatas:
            # 入力データをサイズの大きい順にソート
            inputDatas.sort(key=lambda data: data.getDiagonal2(), reverse=True)
            
            # 結果用のFlowDataを初期化
            firstData = inputDatas[0]
            width, height = firstData.getDimensions()
            flowData = FlowData(firstData.headers)
            flowData.setDimensions(width, height)
            
            # ブロック単位で処理（並列化）
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for block in firstData.iterateBlocks():
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