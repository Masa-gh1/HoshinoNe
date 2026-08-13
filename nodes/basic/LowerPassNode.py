'''
LowerPassNode - 下値通過ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode

class LowerPassNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'lower_pass'
    # ノード名
    name      = '下値通'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def createLazyFlowData(self, inputDatas):
        """LazyFlowDataを作成"""
        return LowerPassLazyFlowData(inputDatas)

class LowerPassLazyFlowData(LazyFlowData):
    def blockOperation(self, blocks, planeIndex, x, y):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        result = None
        
        if blocks:
            result = blocks[0].data.copy()
            for block in blocks[1:]:
                result[block.data < result] = nh.nan
        
        return DataBlock(result, planeIndex, x, y)
