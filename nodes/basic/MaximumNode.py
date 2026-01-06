'''
MaximumNode - 最大ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin

class MaximumNode(N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'maximum'
    # ノード名
    name      = '最大'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：Polynomialを事前統合"""
        datas = []
        polynomials = []
        
        for data in inputDatas:
            dataType = data.headers.get('type', 'table')
            if dataType == 'polynomial':
                polynomials.append(data)
            else:
                datas.append(data)
        
        # polynomial を事前統合(最大)
        self._combinedPolynomials = polynomials
        
        if datas:
            return datas
        elif self._combinedPolynomials:
            datas = [self._combinedPolynomials[0]]
            del self._combinedPolynomials[0]
            return datas
        else:
            return None

    def getOutputDimensions(self, baseData, inputDatas):
        """選択大では全入力データを包含するサイズを使用"""
        self._outputDimensions = self.getUnionDimensions(inputDatas)
        return self._outputDimensions
    
    def processBlock(self, inputDatas, planeIndex, x, y):
        """単一ブロックの最大処理"""
        import numpy as np
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        resultWidth, resultHeight = self._outputDimensions
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth  = min(BLOCK_SIZE, resultWidth - x)
        
        if not inputDatas:
            # データがないので NaN で初期化
            result = nh.nans((blockHeight, blockWidth))
        else:
            result = None
            # table の最大（NaN対応）
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
                        # NaN 対応最大
                        result[:minH, :minW] = np.where(
                            ~np.isnan(result[:minH, :minW]) & ~np.isnan(inputBlock.data[:minH, :minW]),
                            np.maximum(result[:minH, :minW], inputBlock.data[:minH, :minW]),
                            np.where(
                                np.isnan(result[:minH, :minW]),
                                inputBlock.data[:minH, :minW],
                                result[:minH, :minW]
                            )
                        )
        
        for polynomial in self._combinedPolynomials:
            # polynomial の最大（NaN対応）
            polynomialValues = self.calculatePolynomialBlock(polynomial, planeIndex, x, y, result.shape)
            result = np.where(
                np.isnan(result),
                polynomialValues,
                np.maximum( result, polynomialValues)
            )
        
        return DataBlock(result, planeIndex, x, y)
