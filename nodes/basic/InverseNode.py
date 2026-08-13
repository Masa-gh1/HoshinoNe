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
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return InverseLazyFlowData(inputData)

class InverseLazyFlowData(LazyFlowData):
    def blockOperation(self, block, planeIndex, x, y):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        data = block.data
        isValid = data != 0
        result = np.divide( 1.0, data, where=isValid)
        np.logical_not(isValid, out=isValid)
        result[isValid] = nh.nan
        
        return DataBlock(result, planeIndex, x, y)
