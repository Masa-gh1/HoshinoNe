'''
PowerNode - 冪算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class PowerNode(LazyNNOperationNode, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'power'
    # ノード名
    name      = '冪算'
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
        
        # auxiliary polynomialを事前統合（加算：指数の加算）
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.add)
        
        # auxiliary tableを事前統合（最初のもののみ使用）
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return PowerLazyFlowData(inputData, self._combinedAuxiliaryPolynomial, self._combinedAuxiliaryTable)

class PowerLazyFlowData(LazyFlowData, PolynomialOperationMixin):
    def operation(self, flowData, planeIndex, x, y, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        import numpy as np
        from base import DataBlock

        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data
        is_complex = np.iscomplexobj(result)
        
        # auxiliary polynomialを指数として冪乗
        if combinedAuxiliaryPolynomial:
            polynomialValues = self.calculatePolynomialBlock(combinedAuxiliaryPolynomial, planeIndex, x, y, result.shape, defaultValue=1.0)
            power_result = np.power(result, polynomialValues)
            result = power_result if is_complex else np.real(power_result)
        
        # auxiliary tableを指数として冪乗
        if combinedAuxiliaryTable:
            auxiliaryBlock = combinedAuxiliaryTable.getBlock(planeIndex, x, y)
            if auxiliaryBlock:
                power_result = np.power(result, auxiliaryBlock.data)
                result = power_result if is_complex else np.real(power_result)
        
        return DataBlock( result, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['display_levels']
    
    def headerOperation(cls, lazyFlowData, key, combinedAuxiliaryPolynomial, combinedAuxiliaryTable):
        import numpy as np
        
        if not 'display_levels' in lazyFlowData.sourceFlowData.headers:
            return None
        
        inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        if combinedAuxiliaryPolynomial:
            polynomial = combinedAuxiliaryPolynomial.getBlock(0, 0, 0)
            if polynomial:
                width, height = lazyFlowData.sourceFlowData.getDimensions()
                expMin, expMax = cls.calculatePolynomialRange(polynomial.data, width, height)
                
                # 冪乗の範囲計算（実数部のみ）
                powers = [np.real(inputMin ** expMin), np.real(inputMin ** expMax),
                            np.real(inputMax ** expMin), np.real(inputMax ** expMax)]
                return {
                    'display_levels': {
                        'min': min(powers),
                        'exclusive_upper': max(powers)
                    }
                }
        
        # 複雑な場合は元のdisplay_levelsをそのまま返す
        return {'display_levels': inputLevels}
