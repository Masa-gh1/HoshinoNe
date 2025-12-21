'''
AbsoluteNode - 絶対値ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode 

class AbsoluteNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'absolute'
    # ノード名
    name      = '絶対値'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return AbsoluteLazyFlowData(inputData)

class AbsoluteLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y):
        import numpy as np
        from base import DataBlock

        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = np.abs(block.data)
        
        return DataBlock(result, planeIndex, x, y)

    def getLazyHeaderkeys(self):
        return ['display_levels']    

    def headerOperation(self, lazyFlowData, key):
        if not 'display_levels' in lazyFlowData.sourceFlowData.headers:
            return None
        
        inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        # 絶対値変換: [a, b) → [0, max(|a|, |b|))
        absMin = abs(inputMin)
        absMax = abs(inputMax)
        
        return {
            'display_levels': {
                'min': 0.0,
                'exclusive_upper': max(absMin, absMax)
            }
        }
