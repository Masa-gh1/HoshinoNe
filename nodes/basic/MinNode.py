'''
MinNode - 比較小ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np

from base.FlowNode_CONST import *
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class MinNode(LazyNNOperationNode, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'min'
    # ノード名
    name      = '比較小'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
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
        
        # auxiliary polynomial を事前統合（比較小）
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.minimum)
        
        # auxiliary table を事前統合（最初のもののみ使用）
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return MinLazyFlowData(inputData, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)
    
class MinLazyFlowData(LazyFlowData, PolynomialOperationMixin):
    def operation(self, flowData, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary polynomialを比較小
        if combinedAuxiliaryPolynomial:
            polynomialValues = self.calculatePolynomialBlock(combinedAuxiliaryPolynomial, block.planeIndex, block.x, block.y, result.shape, defaultValue=1.0)
            result = np.minimum(result, polynomialValues)
        
        # auxiliary tableを比較小
        if combinedAuxiliaryTable:
            auxiliaryBlock = combinedAuxiliaryTable.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.minimum(result, auxiliaryBlock.data)
        
        return DataBlock(result, planeIndex, x, y)
