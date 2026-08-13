'''
SquaredNormNode - ノルムの二乗ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode 

class SquaredNormNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'squared_norm'
    # ノード名
    name      = 'ノルムの二乗'
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
        
        if np.iscomplexobj(block.data):
            # 複素数なので、二乗して加算
            #    | a   + bi         |^2
            #  = ((a^2 + b ^2)^(1/2))^2 複素数の大きさ(ノルム)を三平方の定理で求める
            #  =   a^2 + b ^2
            result = np.square(block.data.real) + np.square(block.data.imag)
        elif np.issubdtype(block.data.dtype, np.number):
            # 実数なので、二乗する
            result = np.square(block.data)
        else:
            # その他なので、実直に計算する
            result = np.square(np.abs(block.data))
        
        return DataBlock(result, planeIndex, x, y)
