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
    def blockOperation(self, block, planeIndex, x, y):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        arr = block.data
        with np.errstate(divide='ignore', invalid='ignore'):
            result = np.where(arr != 0, 1.0 / arr, nh.nan)
        
        return DataBlock(result, planeIndex, x, y)
