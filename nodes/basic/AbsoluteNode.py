'''
AbsoluteNode - 絶対値ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode 

class AbsoluteNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'absolute'
    # ノード名
    name      = '絶対値'
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
        
        result = np.abs(block.data)
        
        return DataBlock(result, planeIndex, x, y)
