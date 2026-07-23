'''
OffsetNode - 加算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNBinaryOperationNode

class OffsetNode(LazyNNBinaryOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'offset'
    # ノード名
    name      = '加算'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def createLazyFlowData(self, inputDatas):
        """LazyFlowDataを作成"""
        return OffsetLazyFlowData(inputDatas)

class OffsetLazyFlowData(LazyFlowData):
    def blockOperation(self, blocks, planeIndex, x, y):
        import numpy as np
        from base import DataBlock
        
        result = None
        
        if blocks:
            result = blocks[0].data.copy()
            for block in blocks[1:]:
                result += block.data
        
        return DataBlock(result, planeIndex, x, y)
