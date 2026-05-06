'''
LowerPassNode - 下値通過ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, TensorOperationMixin, PolynomialOperationMixin

class LowerPassNode(LazyNNOperationNode, TensorOperationMixin, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'lower_pass'
    # ノード名
    name      = '下値通'
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
        
        # auxiliary data と tensor を事前統合(最小)
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxDatas + auxTensors, np.minimum)
        
        # auxiliary polynomial を設定
        self._auxiliaryPolynomials = auxPolynomials
        
        return prmDatas + prmTensors + prmPolynomials
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        return LowerPassLazyFlowData(inputData, self._combinedAuxiliaryTensor, self._auxiliaryPolynomials)

class LowerPassLazyFlowData(LazyFlowData, TensorOperationMixin, PolynomialOperationMixin):
    def blockOperation(self, block, planeIndex, x, y, combinedAuxiliaryTensor, auxiliaryPolynomials):
        import numpy as np
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        result = block.data.copy()
        
        # auxiliary data と tensor を比較
        if combinedAuxiliaryTensor:
            block = self.calculateTensorBlock(combinedAuxiliaryTensor, planeIndex, x, y, result.shape, defaultValue=np.inf)
            if not block is None:
                result[block < result] = nh.nan
        
        # auxiliary polynomial を比較
        for auxiliaryPolynomial in auxiliaryPolynomials:
            block = self.calculatePolynomialBlock(auxiliaryPolynomial, planeIndex, x, y, result.shape, defaultValue=np.inf)
            if not block is None:
                result[block < result] = nh.nan
        
        return DataBlock(result, planeIndex, x, y)
