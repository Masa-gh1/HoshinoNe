'''
MinNode - 比較小ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, TensorOperationMixin, PolynomialOperationMixin

class MinNode(LazyNNOperationNode, TensorOperationMixin, PolynomialOperationMixin):
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
        
        # auxiliary data と tensor を事前統合(比較小)
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxDatas + auxTensors, np.minimum)
        
        # auxiliary polynomial を設定
        self._auxiliaryPolynomials = auxPolynomials
        
        return prmStreams
    
    def createLazyFlowData(self, inputDatas):
        """LazyFlowDataを作成"""
        return MinLazyFlowData(inputDatas, self._combinedAuxiliaryTensor, self._auxiliaryPolynomials)
    
class MinLazyFlowData(LazyFlowData, TensorOperationMixin, PolynomialOperationMixin):
    def blockOperation(self, blocks, planeIndex, x, y, combinedAuxiliaryTensor, auxiliaryPolynomials):
        import numpy as np
        from base import DataBlock
        
        result = None
        for block in blocks:
            if not result:
                result = block.data.copy()
            else:
                np.minimum(result, block.data, out=result)
        
        # auxiliary data と tensor を比較小
        if combinedAuxiliaryTensor:
            block = self.calculateTensorBlock(combinedAuxiliaryTensor, planeIndex, x, y, result.shape, defaultValue=np.inf)
            if not block is None:
                np.minimum(result, block, out=result)
        
        # auxiliary polynomial を比較小
        for auxiliaryPolynomial in auxiliaryPolynomials:
            block = self.calculatePolynomialBlock(auxiliaryPolynomial, planeIndex, x, y, result.shape, defaultValue=np.inf)
            if not block is None:
                np.minimum(result, block, out=result)
        
        return DataBlock(result, planeIndex, x, y)
