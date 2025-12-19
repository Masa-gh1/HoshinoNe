'''
SumNode - 総和ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from config import BLOCK_SIZE
from base.FlowNode_CONST import *
from base import DataBlock
from nodes import N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin
from utils import numpy_helpers as nh

class SumNode(N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'sum'
    # ノード名
    name      = '総和'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：Polynomialを事前統合"""
        datas = []
        tensors = []
        polynomials = []
        
        for data in inputDatas:
            dataType = data.headers.get('type', 'table')
            if   dataType == 'tensor':
                tensors.append(data)
            elif dataType == 'polynomial':
                polynomials.append(data)
            else:
                datas.append(data)
        
        # tensor を事前統合(加算)
        self._combinedTensor = self.computeCombinedTensor(tensors, np.add)
        
        # polynomial を事前統合(加算)
        self._combinedPolynomial = self.computeCombinedPolynomial(polynomials, np.add)
        
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

    def getResultDimensions(self, inputDatas):
        """加算では全入力データを包含するサイズを使用"""
        return self.getUnionDimensions(inputDatas)
    
    def setupDisplayLevels(self, outputFlowData, inputDatas):
        """加算されたdisplay_levelsを設定"""
        allLevels = []
        for data in inputDatas:
            if data.headers and 'display_levels' in data.headers:
                levels = data.headers['display_levels']
                allLevels.append((levels['min'], levels['exclusive_upper']))
        
        if not allLevels:
            return
        
        minSum = sum(level[0] for level in allLevels)
        maxSum = sum(level[1] for level in allLevels)
        
        outputFlowData.headers['display_levels'] = {
            'min'            : minSum,
            'exclusive_upper': maxSum
        }
    
    def processBlock(self, block, inputDatas):
        """単一ブロックの加算処理"""
        planeIndex = block.planeIndex
        x, y = block.x, block.y
        
        resultWidth, resultHeight = self.getResultDimensions(inputDatas)
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth = min(BLOCK_SIZE, resultWidth - x)
        result = None
        
        # tableデータの加算（NaN対応）
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
                    # NaN対応加算（効率的な順序）
                    result[:minH, :minW] = np.where(
                        ~np.isnan(result[:minH, :minW]) & ~np.isnan(inputBlock.data[:minH, :minW]),
                        result[:minH, :minW] + inputBlock.data[:minH, :minW],
                        np.where(
                            np.isnan(result[:minH, :minW]),
                            inputBlock.data[:minH, :minW],
                            result[:minH, :minW]
                        )
                    )
        
        # tableデータがない場合の初期化
        if result is None:
            result = nh.nans((blockHeight, blockWidth))
        
        # polynomialデータの加算（NaN対応）
        if self._combinedPolynomial:
            polynomialValues = self.calculatePolynomialBlock(self._combinedPolynomial, planeIndex, x, y, result.shape)
            result = np.where(
                np.isnan(result),
                polynomialValues,
                result + polynomialValues
            )
        
        return DataBlock(result, planeIndex, x, y)
    
    def _processPolynomialAddition(self, block, polynomialDatas):
        """全てpolynomialの場合の加算処理"""
        planeIndex = block.planeIndex
        
        # 最初のpolynomialの係数行列を取得
        firstPolynomial = polynomialDatas[0]
        coeffBlock = firstPolynomial.getBlock(planeIndex, 0, 0)
        if not coeffBlock:
            return None
        
        result = coeffBlock.data.copy()
        
        # 他のpolynomialの係数行列を加算
        for polynomialData in polynomialDatas[1:]:
            coeffBlock = polynomialData.getBlock(planeIndex, 0, 0)
            if coeffBlock:
                # サイズを合わせて加算
                minH = min(result.shape[0], coeffBlock.data.shape[0])
                minW = min(result.shape[1], coeffBlock.data.shape[1])
                result[:minH, :minW] += coeffBlock.data[:minH, :minW]
        
        return DataBlock(result, planeIndex, block.x, block.y)
    
