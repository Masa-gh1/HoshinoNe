'''
ScaleNode - 乗算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, TensorOperationMixin, PolynomialOperationMixin

class ScaleNode(LazyNNOperationNode, TensorOperationMixin, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'scale'
    # ノード名
    name      = '乗算'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        import numpy as np
        
        prmDatas       = []
        prmTensors     = []
        prmPolynomials = []
        auxDatas       = []
        auxTensors     = []
        auxPolynomials = []
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            dataType = data.headers.get('type', 'table')
            if category == 'auxiliary':
                if   dataType == 'tensor':
                    auxTensors.append(data)
                elif dataType == 'polynomial':
                    auxPolynomials.append(data)
                else:
                    auxDatas.append(data)
            else:
                if   dataType == 'tensor':
                    prmTensors.append(data)
                elif dataType == 'polynomial':
                    prmPolynomials.append(data)
                else:
                    prmDatas.append(data)
        
        # auxiliary data と tensor を事前統合(乗算)
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxDatas + auxTensors, np.multiply)
        
        # auxiliary polynomial を事前統合(乗算)
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxPolynomials, np.multiply)
        
        return prmDatas + prmTensors + prmPolynomials
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return ScaleLazyFlowData(inputData, self._combinedAuxiliaryTensor, self._combinedAuxiliaryPolynomial)

class ScaleLazyFlowData(LazyFlowData, TensorOperationMixin, PolynomialOperationMixin):
    def blockOperation(self, block, planeIndex, x, y, combinedAuxiliaryTensor, combinedAuxiliaryPolynomial):
        import numpy as np
        from base import DataBlock
        
        result = block.data.copy()
        
        # auxiliary data と tensor を乗算
        if combinedAuxiliaryTensor:
            block = self.calculateTensorBlock(combinedAuxiliaryTensor, planeIndex, x, y, result.shape, defaultValue=1.0)
            if not block is None:
                result *= block
        
        # auxiliary polynomial を乗算
        if combinedAuxiliaryPolynomial:
            block = self.calculatePolynomialBlock(combinedAuxiliaryPolynomial, planeIndex, x, y, result.shape, defaultValue=1.0)
            if not block is None:
                result *= block
        
        return DataBlock(result, planeIndex, x, y)
