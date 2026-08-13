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
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return NegateLazyFlowData(inputData)

class NegateLazyFlowData(LazyFlowData):
    def blockOperation(self, block, planeIndex, x, y):
        import numpy as np
        from base import DataBlock

        result = -block.data
        return DataBlock(result, planeIndex, x, y)
