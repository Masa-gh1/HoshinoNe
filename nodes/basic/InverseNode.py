'''
InverseNode - 逆数ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
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
        return InverseLazyFlowData(inputData)

class InverseLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import DataBlock

        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        arr = block.data
        with np.errstate(divide='ignore', invalid='ignore'):
            result = np.where(arr != 0, 1.0 / arr, nh.nan)
        
        return DataBlock(result, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['display_levels']
    
    def headerOperation(self, lazyFlowData, key):
        if not 'display_levels' in lazyFlowData.sourceFlowData.headers:
            return None
        
        inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
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
