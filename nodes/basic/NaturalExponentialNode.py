'''
NaturalExponentialNode - 自然指数ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode 

class NaturalExponentialNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'natural_exponential'
    # ノード名
    name      = '自然指数'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return AbsoluteLazyFlowData(inputData)

class AbsoluteLazyFlowData(LazyFlowData):
    def blockOperation(self, block, planeIndex, x, y):
        import numpy as np
        from base import DataBlock
        
        result = np.exp(block.data)
        
        return DataBlock(result, planeIndex, x, y)
