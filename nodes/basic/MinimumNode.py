'''
MinimumNode - 最小ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin

class MinimumNode(N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'minimum'
    # ノード名
    name      = '最小'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：Polynomialを事前統合"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        prmDatas       = []
        prmTensors     = []
        prmPolynomials = []
        auxDatas       = []
        auxTensors     = []
        auxPolynomials = []
        variableType = nh.BDTYPE
        
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
            variableType = np.result_type(variableType, data.getVariableType())
        
        # tensor を事前統合(最小)
        self._combinedTensor = self.computeCombinedTensor(prmTensors + auxTensors, np.minimum)
        
        # polynomial を設定
        self._polynomials = prmPolynomials + auxPolynomials
        
        self._variableType = variableType
        
        if prmDatas or auxDatas:
            return prmDatas + auxDatas
        elif self._combinedTensor:
            prmDatas = [self._combinedTensor]
            self._combinedTensor = None
            return prmDatas
        elif self._combinedPolynomial:
            prmDatas = self._polynomials
            self._polynomials = None
            return prmDatas
        else:
            return None

    def getOutputDimensions(self, baseData, inputDatas):
        """最小では全入力データを包含するサイズを使用"""
        self._outputDimensions = self.getUnionDimensions(inputDatas)
        return self._outputDimensions
    
    def processBlock(self, inputDatas, planeIndex, x, y):
        """単一ブロックの最小処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        resultWidth, resultHeight = self._outputDimensions
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth  = min(BLOCK_SIZE, resultWidth  - x)
        
        if not inputDatas:
            # データがないので NaN で初期化
            result = nh.nans((blockHeight, blockWidth))
        else:
            result = None
            # table の最小(NaN対応)
            for inputData in inputDatas:
                inputBlock = inputData.getBlock(planeIndex, x, y)
                if inputBlock:
                    minH = min(blockHeight, inputBlock.data.shape[0])
                    minW = min(blockWidth, inputBlock.data.shape[1])
                    
                    if result is None:
                        # 最初のブロックで初期化
                        result = nh.nans((blockHeight, blockWidth))
                        result[:minH, :minW] = inputBlock.data[:minH, :minW]
                    else:
                        # NaN 対応最小
                        result[:minH, :minW] = np.where(
                            ~np.isnan(result[:minH, :minW]) & ~np.isnan(inputBlock.data[:minH, :minW]),
                            np.minimum(result[:minH, :minW], inputBlock.data[:minH, :minW]),
                            np.where(
                                np.isnan(result[:minH, :minW]),
                                inputBlock.data[:minH, :minW],
                                result[:minH, :minW]
                            )
                        )
        
        # tensor を最小(NaN対応)
        if self._combinedTensor:
            block = self.calculateTensorBlock(self._combinedTensor, planeIndex, x, y, result.shape, defaultValue=np.inf)
            if not block is None:
                np.minimum( result, block, out=result)
        
        # polynomial を最小(NaN対応)
        for polynomial in self._polynomials:
            block = self.calculatePolynomialBlock(polynomial, planeIndex, x, y, result.shape, defaultValue=np.inf)
            if not block is None:
                np.minimum( result, block, out=result)
        
        return DataBlock(result, planeIndex, x, y)
