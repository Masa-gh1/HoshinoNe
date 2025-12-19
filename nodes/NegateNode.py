'''
NegateNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from base import LazyNNOperationNode, DataBlock
from base.LazyFlowData import LazyFlowData

class NegateNode(LazyNNOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "negate", "符号反転")
    
    def getColor(self):
        return self._color_func
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._negateOperation)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels)
        return lazyFlowData
    
    def _negateOperation(self, flowData, planeIndex, x, y):
        """符号反転操作"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = -block.data
        return DataBlock(block.planeIndex, block.x, block.y, result)
    
    def _computeDisplayLevels(self):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            try:
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
            except (KeyError, AttributeError):
                return None
        return compute