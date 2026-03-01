'''
ProductNode - 総積ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin

class ProductNode(N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'product'
    # ノード名
    name      = '総積'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def preprocessInputs(self, inputDatas):
        """入力データの前処理：Polynomialを事前統合"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        datas = []
        tensors = []
        polynomials = []
        variableType = nh.BDTYPE
        
        for data in inputDatas:
            dataType = data.headers.get('type', 'table')
            if   dataType == 'tensor':
                tensors.append(data)
            elif dataType == 'polynomial':
                polynomials.append(data)
            else:
                datas.append(data)
            variableType = np.result_type(variableType, data.getVariableType())
        
        # tensor を事前統合(乗算)
        self._combinedTensor = self.computeCombinedTensor(tensors, np.multiply)
        
        # polynomial を事前統合(乗算)
        self._combinedPolynomial = self.computeCombinedPolynomial(polynomials, np.multiply)
        
        self._variableType = variableType
        
        if datas:
            return datas
        elif self._combinedTensor:
            datas = [self._combinedTensor]
            self._combinedTensor = None
            return datas
        elif self._combinedPolynomial:
            datas = [self._combinedPolynomial]
            self._combinedPolynomial = None
            return datas
        else:
            return None

    def getOutputDimensions(self, baseData, inputDatas):
        """乗算では全入力データを包含するサイズを使用"""
        self._outputDimensions = self.getUnionDimensions(inputDatas)
        return self._outputDimensions
    
    def processBlock(self, inputDatas, planeIndex, x, y):
        """単一ブロックの乗算処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock

        resultWidth, resultHeight = self._outputDimensions
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth = min(BLOCK_SIZE, resultWidth - x)
        result = None
        
        # tableデータの乗算（NaN対応）
        for inputData in inputDatas:
            inputBlock = inputData.getBlock(planeIndex, x, y)
            if inputBlock:
                minH = min(blockHeight, inputBlock.data.shape[0])
                minW = min(blockWidth, inputBlock.data.shape[1])
                
                if result is None:
                    # 最初のブロックで初期化
                    result = nh.nans((blockHeight, blockWidth), dtype=self._variableType)
                    result[:minH, :minW] = inputBlock.data[:minH, :minW]
                else:
                    # NaN対応乗算
                    result[:minH, :minW] = np.where(
                        ~np.isnan(result[:minH, :minW]) & ~np.isnan(inputBlock.data[:minH, :minW]),
                        result[:minH, :minW] * inputBlock.data[:minH, :minW],
                        np.where(
                            np.isnan(result[:minH, :minW]),
                            inputBlock.data[:minH, :minW],
                            result[:minH, :minW]
                        )
                    )
            
        # tableデータがない場合の初期化
        if result is None:
            result = nh.nans((blockHeight, blockWidth))
        
        # tensor を乗算（NaN対応）
        if self._combinedTensor:
            block = self._combinedTensor.getBlock( planeIndex, x, y)
            if block:
                result *= block.data
        
        # polynomial を乗算（NaN対応）
        if self._combinedPolynomial:
            polynomialValues = self.calculatePolynomialBlock(self._combinedPolynomial, planeIndex, x, y, result.shape, defaultValue=1.0)
            if not polynomialValues is None:
                result *= polynomialValues
        
        return DataBlock(result, planeIndex, x, y)
