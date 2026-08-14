'''
CategoryAuxiliaryNode - データを auxiliary カテゴリに設定するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import FlowNode

class CategoryAuxiliaryNode(FlowNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_UTIL
    minorType = 'category_auxiliary'
    # ノード名
    name      = "補正値"
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_AUX
    
    def process(self, context=None):
        from base import FlowDataWrapper
        
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)
        
        if not inputStreams or not inputStreams[0]:
            return
        
        # FlowDataWrapperを使用して category: auxiliary を後方のみに伝える
        resultFlowDatas = []
        for inputData in inputStreams[0]:
            updatedHeaders = {'category': 'auxiliary'}
            wrappedData = FlowDataWrapper(inputData, updatedHeaders)
            resultFlowDatas.append(wrappedData)
        
        # ラップされたデータを出力
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
