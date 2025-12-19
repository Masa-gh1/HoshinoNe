'''
CategoryAuxiliaryNode - データをauxiliaryカテゴリに設定するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base import FlowNode

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
        
        # 各入力データのheadersにcategory: auxiliaryを設定
        for inputData in inputDatas:
            if inputData.headers:
                inputData.headers = inputData.headers.copy()
                inputData.headers['category'] = 'auxiliary'
        
        # 入力データをそのまま出力
        self.flowDatas = inputDatas
        self.reportProgress(context, "完了")