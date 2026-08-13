'''
MinNode - 比較小ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode

class MinNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'min'
    # ノード名
    name      = '比較小'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def createLazyFlowData(self, inputDatas):
        """LazyFlowDataを作成"""
        return MinLazyFlowData(inputDatas)
    
class MinLazyFlowData(LazyFlowData):
    def blockOperation(self, blocks, planeIndex, x, y):
        import numpy as np
        from base import DataBlock
        
        result = None
        
        if blocks:
            result = blocks[0].data.copy()
            for block in blocks[1:]:
                np.minimum(result, block.data, out=result)
        
        return DataBlock(result, planeIndex, x, y)
