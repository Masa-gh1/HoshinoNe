'''
ScaleNode - 乗算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class ScaleNode(LazyNNOperationNode, PolynomialOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "scale", "乗算")
    
    def getColor(self):
        return self._color_op
    
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
        
        # auxiliary polynomialを事前統合（乗算）
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.multiply)
        
        # auxiliary tableを事前統合（最初のもののみ使用）
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._scaleOperation, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels, self._combinedAuxiliaryPolynomial)
        return lazyFlowData
    
    @classmethod
    def _scaleOperation(cls, flowData, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        """スケール操作（事前統合されたauxiliaryデータを乗算）"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary polynomialを乗算
        if combinedAuxiliaryPolynomial:
            polynomialValues = cls.calculatePolynomialBlock(combinedAuxiliaryPolynomial, block.planeIndex, block.x, block.y, result.shape, defaultValue=1.0)
            result = np.multiply(result, polynomialValues)
        
        # auxiliary tableを乗算
        if combinedAuxiliaryTable:
            auxiliaryBlock = combinedAuxiliaryTable.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.multiply(result, auxiliaryBlock.data)
        
        return DataBlock(result, block.planeIndex, block.x, block.y)
    
    @classmethod
    def _computeDisplayLevels(cls, combinedAuxiliaryPolynomial):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
            if not inputLevels or 'min' not in inputLevels or 'exclusive_upper' not in inputLevels:
                return None
                
            inputMin = inputLevels['min']
            inputMax = inputLevels['exclusive_upper']
            
            if combinedAuxiliaryPolynomial:
                polynomial = combinedAuxiliaryPolynomial.getBlock(0, 0, 0)
                if polynomial:
                    width, height = lazyFlowData.sourceFlowData.getDimensions()
                    scaleMin, scaleMax = cls.calculatePolynomialRange(polynomial.data, width, height)
                    
                    # 乗算の場合は範囲が複雑になる
                    products = [inputMin * scaleMin, inputMin * scaleMax, inputMax * scaleMin, inputMax * scaleMax]
                    
                    return {
                        'display_levels': {
                            'min': min(products),
                            'exclusive_upper': max(products)
                        }
                    }
            # auxiliary tableの場合は範囲計算が複雑なので省略
            # auxiliaryがない場合は元のdisplay_levelsをそのまま返す
            return {'display_levels': inputLevels}
        return compute