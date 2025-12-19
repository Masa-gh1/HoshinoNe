'''
CategoryAuxiliaryNode - データをauxiliaryカテゴリに設定するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base import FlowNode
from base import FlowDataWrapper

class CategoryAuxiliaryNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "category_auxiliary", "補正用")
    
    def getColor(self):
        return self._color_util
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputDatas = []
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        # FlowDataWrapperを使用して category: auxiliary を後方のみに伝える
        wrappedDatas = []
        for inputData in inputDatas:
            updatedHeaders = {'category': 'auxiliary'}
            wrappedData = FlowDataWrapper(inputData, updatedHeaders)
            wrappedDatas.append(wrappedData)
        
        # ラップされたデータを出力
        self.flowDatas = wrappedDatas
        self.reportProgress(context, "完了")