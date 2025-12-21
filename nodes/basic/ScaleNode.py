'''
ScaleNode - 乗算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class ScaleNode(LazyNNOperationNode, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'scale'
    # ノード名
    name      = '乗算'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat= スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
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
        
        # auxiliary polynomialを事前統合（乗算）
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.multiply)
        
        # auxiliary tableを事前統合（最初のもののみ使用）
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return ScaleLazyFlowData(inputData, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)

class ScaleLazyFlowData(LazyFlowData, PolynomialOperationMixin):
    def operation(self, flowData, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        import numpy as np
        from base import DataBlock

        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary polynomialを乗算
        if combinedAuxiliaryPolynomial:
            polynomialValues = self.calculatePolynomialBlock(combinedAuxiliaryPolynomial, block.planeIndex, block.x, block.y, result.shape, defaultValue=1.0)
            result = np.multiply(result, polynomialValues)
        
        # auxiliary tableを乗算
        if combinedAuxiliaryTable:
            auxiliaryBlock = combinedAuxiliaryTable.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.multiply(result, auxiliaryBlock.data)
        
        return DataBlock(result, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['display_levels']

    def headerOperation(self, lazyFlowData, key, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        if not 'display_levels' in lazyFlowData.sourceFlowData.headers:
            return None
        
        inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        if combinedAuxiliaryPolynomial:
            mixs = []
            for planeIndex in range(combinedAuxiliaryPolynomial.getPlaneCount()):
                polynomial = combinedAuxiliaryPolynomial.getBlock(planeIndex, 0, 0)
                width, height = lazyFlowData.sourceFlowData.getDimensions()
                minValue, maxValue = self.calculatePolynomialRange(polynomial.data, width, height)
                mixs.extend([inputMin * minValue, inputMin * maxValue, inputMax * minValue, inputMax * maxValue])
            inputMin = min(mixs)
            inputMax = max(mixs)
        
        if combinedAuxiliaryTable:
            mixs = []
            if 'display_levels' in combinedAuxiliaryTable.headers:
                minValue = combinedAuxiliaryTable.headers['display_levels']['min']
                maxValue = combinedAuxiliaryTable.headers['display_levels']['exclusive_upper']
            else:
                minValue = combinedAuxiliaryTable.getMinValue()
                maxValue = combinedAuxiliaryTable.getMaxValue()
            mixs = [inputMin * minValue, inputMin * maxValue, inputMax * minValue, inputMax * maxValue]
            inputMin = min(mixs)
            inputMax = max(mixs)
        
        return {
            'display_levels': {
                'min'            : inputMin,
                'exclusive_upper': inputMax,
            }
        }
