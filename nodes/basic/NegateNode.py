'''
NegateNode - 符号反転ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from base.FlowNode_CONST import *
from base import DataBlock
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
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._negateOperation)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels)
        return lazyFlowData
    
    @staticmethod
    def _negateOperation(flowData, planeIndex, x, y):
        """符号反転操作"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = -block.data
        return DataBlock(result, planeIndex, x, y)
    
    @staticmethod
    def _computeDisplayLevels(lazyFlowData):
        """display_levelsを計算"""
        inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
        if not inputLevels or 'min' not in inputLevels or 'exclusive_upper' not in inputLevels:
            return None
            
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        return {
            'display_levels': {
                'min': -inputMax,
                'exclusive_upper': -inputMin
            }
        }
