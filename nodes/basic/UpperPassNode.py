'''
HighPassFilterNode - ハイパスフィルターノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin

class UpperPassNode(LazyNNOperationNode, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'upper_pass'
    # ノード名
    name      = '上値通'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self._combinedPolynomial = None
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        import numpy as np

        primaryDatas = []
        auxiliaryPolynomials = []
        auxiliaryTables = []
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            if category == 'auxiliary':
                dataType = data.headers.get('type', 'table')
                if dataType == 'polynomial':
                    auxiliaryPolynomials.append(data)
                else:
                    auxiliaryTables.append(data)
            else:
                primaryDatas.append(data)
        
        # auxiliary polynomialを事前統合
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.add)
        
        # auxiliary tableを事前統合
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = UpperPassLazyFlowData(inputData, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)
        return lazyFlowData
    
class UpperPassLazyFlowData(LazyFlowData, PolynomialOperationMixin):
    def blockOperation(self, block, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        result = block.data.copy()
        
        # auxiliary polynomialから閾値を取得
        if combinedAuxiliaryPolynomial:
            polynomialValues = self.calculatePolynomialBlock(combinedAuxiliaryPolynomial, planeIndex, x, y, result.shape, defaultValue=1.0)
            result[result < polynomialValues] = nh.nan
        
        # auxiliary tableから閾値を取得
        if combinedAuxiliaryTable:
            auxiliaryBlock = combinedAuxiliaryTable.getBlock(planeIndex, x, y)
            result[result < auxiliaryBlock.data] = nh.nan
        
        return DataBlock(result, planeIndex, x, y)
