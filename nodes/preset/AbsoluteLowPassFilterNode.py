'''
AbsoluteLowPassFilterNode - 絶対値ローパスフィルターノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class AbsoluteLowPassFilterNode(LazyNNOperationNode, PolynomialOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "absolute_lowpass_filter", "絶対値(低通)")
        self._combinedPolynomial = None
    
    def getColor(self):
        return self._color_func
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        primaryDatas = []
        auxiliaryPolynomials = []
        auxiliaryMatrices = []
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            if category == 'auxiliary':
                dataType = data.headers.get('type', 'matrix')
                if dataType == 'polynomial':
                    auxiliaryPolynomials.append(data)
                else:
                    auxiliaryMatrices.append(data)
            else:
                primaryDatas.append(data)
        
        # auxiliary polynomialを事前統合
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.add)
        
        # auxiliary matrixを事前統合
        self._combinedAuxiliaryMatrix = None
        if auxiliaryMatrices:
            self._combinedAuxiliaryMatrix = auxiliaryMatrices[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._absoluteLowPassFilterOperation, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryMatrix)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryMatrix)
        return lazyFlowData
    
    @classmethod
    def _absoluteLowPassFilterOperation(cls, flowData, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryMatrix):
        """絶対値低域通過フィルター操作（閾値を超える値をNaNに変換）"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary polynomialから閾値を取得
        if combinedAuxiliaryPolynomial:
            polynomialValues = cls.calculatePolynomialBlock(combinedAuxiliaryPolynomial, block.planeIndex, block.x, block.y, result.shape, defaultValue=1.0)
            mask = np.abs(result) > polynomialValues
            result = np.where(mask, np.nan, result)
        
        # auxiliary matrixから閾値を取得
        if combinedAuxiliaryMatrix:
            auxiliaryBlock = combinedAuxiliaryMatrix.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                mask = np.abs(result) > auxiliaryBlock.data
                result = np.where(mask, np.nan, result)
        
        return DataBlock(result, block.planeIndex, block.x, block.y)
    
    @classmethod
    def _computeDisplayLevels(cls):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            # フィルター処理では元の範囲を保持（一部がNaNになるだけ）
            inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
            return {'display_levels': inputLevels} if inputLevels else None
        return compute