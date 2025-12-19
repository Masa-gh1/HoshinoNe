'''
InverseNode - 逆数ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from base.FlowNode_CONST import *
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode 

class InverseNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'inverse'
    # ノード名
    name      = '逆数'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._inverseOperation)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels)
        return lazyFlowData
    
    @classmethod
    def _inverseOperation(cls, flowData, planeIndex, x, y):
        """逆数操作"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        arr = block.data
        with np.errstate(divide='ignore', invalid='ignore'):
            result = np.where(arr != 0, 1.0 / arr, np.nan)
        
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
            
            # 逆数変換: [a, b) → [1/b, 1/a) (ゼロを除く)
            if inputMin > 0 or inputMax < 0:
                # ゼロを含まない場合
                return {
                    'display_levels': {
                        'min': 1.0 / inputMax,
                        'exclusive_upper': 1.0 / inputMin
                    }
                }
            else:
                # ゼロを含む場合は元の値を保持
                return {'display_levels': inputLevels}
        return compute