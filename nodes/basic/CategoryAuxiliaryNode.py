'''
CategoryAuxiliaryNode - データを auxiliary カテゴリに設定するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import FlowNode
from base import FlowDataWrapper

class CategoryAuxiliaryNode(FlowNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_UTIL
    minorType = 'category_auxiliary'
    # ノード名
    name      = "補正値"
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
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