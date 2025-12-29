'''
NegateNode - 符号反転ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode

class NegateNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'negate'
    # ノード名
    name      = '符号反転'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return NegateLazyFlowData(inputData)

class NegateLazyFlowData(LazyFlowData):
    def blockOperation(self, block, planeIndex, x, y):
        import numpy as np
        from base import DataBlock

        result = -block.data
        return DataBlock(result, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['display_levels']
    
    def headerOperation(self, lazyFlowData, key):
        if not 'display_levels' in lazyFlowData.sourceFlowData.headers:
            return None
        
        inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        return {
            'display_levels': {
                'min': -inputMax,
                'exclusive_upper': -inputMin
            }
        }
