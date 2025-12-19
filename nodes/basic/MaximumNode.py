'''
MaximumNode - 最大ノード（N:1）

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
        elif self._combinedTensor:
            datas = [self._combinedTensor]
            self._combinedTensor = None
            return datas
        elif self._combinedPolynomials:
            datas = [self._combinedPolynomials[0]]
            del self._combinedPolynomials[0]
            return datas
        else:
            return None

    def getResultDimensions(self, inputDatas):
        """選択大では全入力データを包含するサイズを使用"""
        return self.getUnionDimensions(inputDatas)
    
    def setupDisplayLevels(self, outputFlowData, inputDatas):
        """選択大されたdisplay_levelsを設定"""
        allLevels = []
        for data in inputDatas:
            if data.headers and 'display_levels' in data.headers:
                levels = data.headers['display_levels']
                allLevels.append((levels['min'], levels['exclusive_upper']))
        
        if not allLevels:
            return
        
        levelMin = max(level[0] for level in allLevels)
        levelMax = max(level[1] for level in allLevels)
        
        outputFlowData.headers['display_levels'] = {
            'min'            : levelMin,
            'exclusive_upper': levelMax
        }
    
    def processBlock(self, block, inputDatas):
        """単一ブロックの最大処理"""
        planeIndex = block.planeIndex
        x, y = block.x, block.y
        
        resultWidth, resultHeight = self.getResultDimensions(inputDatas)
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth  = min(BLOCK_SIZE, resultWidth - x)
        
        if not inputDatas:
            # データがないので NaN で初期化
            result = nh.nans((blockHeight, blockWidth))
        else:
            result = None
            # ableデータの最大（NaN対応）
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
                        # NaN対応最大（効率的な順序）
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
            # polynomialデータの最大（NaN対応）
            polynomialValues = self.calculatePolynomialBlock(polynomial, planeIndex, x, y, result.shape)
            result = np.where(
                np.isnan(result),
                polynomialValues,
                np.maximum( result, polynomialValues)
            )
        
        return DataBlock(result, planeIndex, x, y)
