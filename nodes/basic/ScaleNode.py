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
    
    def preprocessStreams(self, inputStreams):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        import numpy as np
        
        prmStreams     = []
        auxDatas       = []
        auxTensors     = []
        auxPolynomials = []
        
        for stream in inputStreams:
            if stream:
                category = stream[0].headers.get('category', 'primary')
                if category == 'auxiliary':
                    for data in stream:
                        dataType = data.headers.get('type', 'table')
                        if   dataType == 'tensor':
                            auxTensors.append(data)
                        elif dataType == 'polynomial':
                            auxPolynomials.append(data)
                        else:
                            auxDatas.append(data)
                else:
                    prmStreams.append(stream)
        
        # auxiliary data と tensor を事前統合(乗算)
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxDatas + auxTensors, np.multiply)
        
        # auxiliary polynomial を事前統合(乗算)
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxPolynomials, np.multiply)
        
        return prmStreams
    
    def createLazyFlowData(self, inputDatas):
        """LazyFlowDataを作成"""
        return ScaleLazyFlowData(inputDatas, self._combinedAuxiliaryTensor, self._combinedAuxiliaryPolynomial)

class ScaleLazyFlowData(LazyFlowData, TensorOperationMixin, PolynomialOperationMixin):
    def blockOperation(self, blocks, planeIndex, x, y, combinedAuxiliaryTensor, combinedAuxiliaryPolynomial):
        import numpy as np
        from base import DataBlock
        
        result = None
        for block in blocks:
            if result is None:
                result = block.data.copy()
            else:
                result *= block.data
        
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
