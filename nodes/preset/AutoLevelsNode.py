'''
AutoLevelsNode - 1%と99%のパーセンタイルでdisplay_levelsを自動調整するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from config import BLOCK_SIZE
from base.FlowNode_CONST import *
from base import FlowNode
from base import FlowDataWrapper
from utils import numpy_helpers as nh

class AutoLevelsNode(FlowNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_UTIL
    minorType = 'auto_levels'
    # ノード名
    name      = '自動レベル'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_PAS

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputDatas = []
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        # 各入力データのdisplay_levelsを1%と99%のパーセンタイルで設定
        for inputData in inputDatas:
            if inputData.headers and inputData.headers.get('type') in ('image','table'):
                width, height = inputData.getDimensions()
                planeCount = inputData.getPlaneCount()
                
                # 全画像データを読み込み
                imageData = nh.zeros((height, width))
                
                for planeIndex in range(planeCount):
                    for y in range(0, height, BLOCK_SIZE):
                        for x in range(0, width, BLOCK_SIZE):
                            block = inputData.getBlock(planeIndex, x, y)
                            if block:
                                blockHeight = min(block.getHeight(), height - y)
                                blockWidth = min(block.getWidth(), width - x)
                                endY = y + blockHeight
                                endX = x + blockWidth
                                imageData[y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
                
                # NaN値を除外して1%と99%のパーセンタイルを計算
                validData = imageData[~np.isnan(imageData)]
                if len(validData) > 0:
                    p1 = np.percentile(validData, 1)
                    p99 = np.percentile(validData, 99)
                else:
                    # 全てNaNの場合はデフォルト値
                    p1, p99 = 0.0, 1.0
                
                # FlowDataWrapperを使用してheadersを後方のみに伝える
                updatedHeaders = {'display_levels': {'min':float(p1), 'exclusive_upper':float(p99)}}
                wrappedData = FlowDataWrapper(inputData, updatedHeaders)
                inputDatas[inputDatas.index(inputData)] = wrappedData
        
        # ラップされたデータを出力
        self.flowDatas = inputDatas
        self.reportProgress(context, "完了")