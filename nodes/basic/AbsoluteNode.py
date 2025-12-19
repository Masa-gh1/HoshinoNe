'''
AbsoluteNode - 絶対値ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from base.FlowNode_CONST import *
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode 

class AbsoluteNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
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
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._absoluteOperation)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels)
        return lazyFlowData
    
    @classmethod
    def _absoluteOperation(cls, flowData, planeIndex, x, y):
        """絶対値操作"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = np.abs(block.data)
        
        return DataBlock(result, block.planeIndex, block.x, block.y)
    
    @classmethod
    def _computeDisplayLevels(cls):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
            if not inputLevels or 'min' not in inputLevels or 'exclusive_upper' not in inputLevels:
                return None
                
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
        return compute