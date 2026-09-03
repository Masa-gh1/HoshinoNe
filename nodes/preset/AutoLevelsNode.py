'''
AutoLevelsNode - 1%と99%のパーセンタイルでdisplay_levelsを自動調整するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import FlowNode

class AutoLevelsNode(FlowNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'auto_levels'
    # ノード名
    name      = '自動レベル'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_PAS
    
    def process(self, context=None):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import FlowDataWrapper

        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)
        
        if not inputStreams or not inputStreams[0]:
            return
        
        # 各入力データのdisplay_levelsを1%と99%のパーセンタイルで設定
        resultFlowDatas = []
        for i, inputData in enumerate(inputStreams[0]):
            type = inputData.getType()
            if type in ('image','table'):
                # 全画像データを読み込み
                blockArrays = []
                for block in inputData.iterateBlocks():
                    blockArrays.append(block.data.ravel())
                data = np.concatenate(blockArrays)
                
                # NaN値を除外して1%と99%のパーセンタイルを計算
                validData = data[~np.isnan(data)]
                if len(validData) > 0:
                    p1 = np.percentile(validData, 1)
                    p99 = np.percentile(validData, 99)
                else:
                    # 全てNaNの場合はデフォルト値
                    p1, p99 = 0.0, 1.0
                
                # FlowDataWrapperを使用してheadersを後方のみに伝える
                updatedHeaders = {'display_levels': {'min':float(p1), 'exclusive_upper':float(p99)}}
                wrappedData = FlowDataWrapper(inputData, updatedHeaders)
                resultFlowDatas.append(wrappedData)
            else:
                resultFlowDatas.append(inputData)
        
        # ラップされたデータを出力
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")