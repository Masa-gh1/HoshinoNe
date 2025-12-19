'''
OffsetNode - 加算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np

from base.FlowNode_CONST import *
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class OffsetNode(LazyNNOperationNode, PolynomialOperationMixin):
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
        self._combinedPolynomial = None
    
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
        
        # auxiliary polynomialを事前統合
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.add)
        
        # auxiliary tableを事前統合（最初のものをベースに加算）
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._offsetOperation, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)
        return lazyFlowData
    
    @classmethod
    def _offsetOperation(cls, flowData, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        """オフセット操作（事前統合されたauxiliaryデータを加算）"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary polynomialを加算
        if combinedAuxiliaryPolynomial:
            polynomialValues = cls.calculatePolynomialBlock(combinedAuxiliaryPolynomial, block.planeIndex, block.x, block.y, result.shape)
            result = np.add(result, polynomialValues)
        
        # auxiliary tableを加算
        if combinedAuxiliaryTable:
            auxiliaryBlock = combinedAuxiliaryTable.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.add(result, auxiliaryBlock.data)
        
        return DataBlock(result, planeIndex, x, y)
    
    @classmethod
    def _computeDisplayLevels(cls, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        """display_levelsを計算"""
        def compute(lazyFlowData):
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
                    minValue, maxValue = cls.calculatePolynomialRange(polynomial.data, width, height)
                    mixs.extend([inputMin + minValue, inputMax + maxValue])
                inputMin = min(mixs)
                inputMax = max(mixs)

            if combinedAuxiliaryTable:
                if 'display_levels' in combinedAuxiliaryTable.headers:
                    minValue = combinedAuxiliaryTable.headers['display_levels']['min']
                    maxValue = combinedAuxiliaryTable.headers['display_levels']['exclusive_upper']
                else:
                    minValue = combinedAuxiliaryTable.getMinValue()
                    maxValue = combinedAuxiliaryTable.getMaxValue()
                inputMin += minValue
                inputMax += maxValue
            
            return {
                'display_levels': {
                    'min'            : inputMin,
                    'exclusive_upper': inputMax,
                }
            }
        return compute
    
