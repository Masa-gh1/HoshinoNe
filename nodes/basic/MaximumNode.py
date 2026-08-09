'''
MaximumNode - 最大ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import PolynomialOperationMixin
from base import TensorOperationMixin
from nodes import N1BlockOperationNode

class MaximumNode(N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'maximum'
    # ノード名
    name      = '最大'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def getOutputDimensions(self, baseData, inputDatas):
        """最大では全入力データを包含するサイズを使用"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        variableType = nh.BDTYPE
        for data in inputDatas:
            variableType = np.result_type(variableType, data.getVariableType())
        self._variableType = variableType
        
        self._outputDimensions = self.getUnionDimensions(inputDatas)
        return self._outputDimensions
    
    def blockOperation(self, blocks, planeIndex, x, y):
        """単一ブロックの最大処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        resultWidth, resultHeight = self._outputDimensions
        
        resultHeight = min(BLOCK_SIZE, resultHeight - y)
        resultWidth  = min(BLOCK_SIZE, resultWidth  - x)
        result  = nh.full((resultHeight, resultWidth), -np.inf, dtype=self._variableType)
        invalid = nh.ones((resultHeight, resultWidth), dtype=bool)
        
        # スレッドローカルに作業用メモリを確保
        _invalidA = self.getLocal('_invalidA', (BLOCK_SIZE, BLOCK_SIZE), dtype=bool)
        _data     = self.getLocal('_data'    , (BLOCK_SIZE, BLOCK_SIZE), dtype=self._variableType)
        
        # tableの最大(NaN対応)
        for block in blocks:
            if block:
                # 計算範囲を取得
                blockH, blockW = block.data.shape
                blockH = min(resultHeight, blockH)
                blockW = min(resultWidth, blockW)
                minH = min(resultHeight, blockH) if 1<blockH else resultHeight # ブロックの高さが1の場合、ブロードキャストにする
                minW = min(resultWidth , blockW) if 1<blockW else resultWidth  # ブロックの幅が1の場合、ブロードキャストにする
                
                # 計算範囲の結果を取得
                res = result[:minH, :minW]
                inv = invalid[:minH, :minW]
                
                # 計算範囲の作業用メモリを取得
                invalidA = _invalidA[:minH, :minW]
                data     = _data[:minH, :minW]
                
                # データをコピー
                data[:] = block.data[:blockH, :blockW]
                
                # nan の位置を更新
                np.isnan(data, out=invalidA)
                np.logical_and(inv, invalidA, out=inv)

                # 値の最大
                np.nan_to_num(data, nan=0.0, copy=False)
                np.maximum( res, data, out=res)
        
        # nan の位置を適用
        if invalid.any():
            result[invalid] = np.nan
        
        return DataBlock(result, planeIndex, x, y)
    
    import threading
    local = threading.local()

    @staticmethod
    def getLocal(name, shape=None, dtype=None):
        if not hasattr(MaximumNode.local, "MaximumNode"):
            MaximumNode.local.MaximumNode = {}
        
        var = MaximumNode.local.MaximumNode.get(name, None)
        
        if var is None and shape is None:
            return None
        elif var is None or var.shape != shape or var.dtype != dtype:
            import numpy as np
            var = np.empty(shape, dtype=dtype)
            MaximumNode.local.MaximumNode[name] = var
            return var
        else:
            return var
