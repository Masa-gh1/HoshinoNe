'''
ProductNode - 総積ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from config import BLOCK_SIZE
from base import DataBlock
from nodes import N1BlockOperationNode, TensorOperationMixin, VectorOperationMixin
from utils import numpy_helpers as nh

class ProductNode(N1BlockOperationNode, TensorOperationMixin, VectorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "product", "総積")

    def getColor(self):
        return self._color_op
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：Tensorを事前統合"""
        datas = []
        vectors = []
        tensors = []
        
        for data in inputDatas:
            dataType = data.headers.get('type', 'matrix')
            if   dataType == 'vector':
                vectors.append(data)
            elif dataType == 'tensor':
                tensors.append(data)
            else:
                datas.append(data)
        
        # vector を事前統合(乗算)
        self._combinedVector = self.computeCombinedVector(vectors, np.multiply)
        
        # tensor を事前統合(乗算)
        self._combinedTensor = self.computeCombinedTensor(tensors, np.multiply)
        
        if datas:
            return datas
        elif self._combinedVector:
            datas = [self._combinedVector] 
            self._combinedVector = None
            return datas
        elif self._combinedTensor:
            datas = [self._combinedTensor] 
            self._combinedTensor = None
            return datas
        else:
            return None

    def getResultDimensions(self, inputDatas):
        """乗算では全入力データを包含するサイズを使用"""
        return self.getUnionDimensions(inputDatas)
    
    def setupDisplayLevels(self, outputFlowData, inputDatas):
        """乗算されたdisplay_levelsを設定"""
        allLevels = []
        for data in inputDatas:
            if data.headers and 'display_levels' in data.headers:
                levels = data.headers['display_levels']
                allLevels.append((levels['min'], levels['exclusive_upper']))
        
        if not allLevels:
            return
        
        minProduct = 1.0
        maxProduct = 1.0
        
        for minVal, maxVal in allLevels:
            products = [minProduct * minVal, minProduct * maxVal, maxProduct * minVal, maxProduct * maxVal]
            minProduct = min(products)
            maxProduct = max(products)
        
        outputFlowData.headers['display_levels'] = {
            'min': minProduct,
            'exclusive_upper': maxProduct
        }
    
    def processBlock(self, block, inputDatas):
        """単一ブロックの乗算処理"""
        planeIdx = block.planeIndex
        x, y = block.x, block.y
        
        resultWidth, resultHeight = self.getResultDimensions(inputDatas)
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth = min(BLOCK_SIZE, resultWidth - x)
        result = None
        
        # matrixデータの乗算（NaN対応）
        for inputData in inputDatas:
            inputBlock = inputData.getBlock(planeIdx, x, y)
            if inputBlock:
                minH = min(blockHeight, inputBlock.data.shape[0])
                minW = min(blockWidth, inputBlock.data.shape[1])
                
                if result is None:
                    # 最初のブロックで初期化
                    result = nh.nans((blockHeight, blockWidth))
                    result[:minH, :minW] = inputBlock.data[:minH, :minW]
                else:
                    # NaN対応乗算（効率的な順序）
                    result[:minH, :minW] = np.where(
                        ~np.isnan(result[:minH, :minW]) & ~np.isnan(inputBlock.data[:minH, :minW]),
                        result[:minH, :minW] * inputBlock.data[:minH, :minW],
                        np.where(
                            np.isnan(result[:minH, :minW]),
                            inputBlock.data[:minH, :minW],
                            result[:minH, :minW]
                        )
                    )
            
        # matrixデータがない場合の初期化
        if result is None:
            result = nh.nans((blockHeight, blockWidth))
        
        # vector を乗算（NaN対応）
        if self._combinedVector:
            block = self._combinedVector.getBlock( planeIdx, x, y)
            if block:
                result = result * block.data
        
        # tensor を乗算（NaN対応）
        if self._combinedTensor:
            tensorValues = self.calculateTensorBlock(self._combinedTensor, planeIdx, x, y, result.shape, defaultValue=1.0)
            if block:
                result = result * tensorValues
        
        return DataBlock(result, planeIdx, x, y)
    
    def _processTensorMultiplication(self, block, tensorDatas):
        """全てtensorの場合の乗算処理（係数の畳み込み）"""
        planeIdx = block.planeIndex
        
        # 最初のtensorの係数行列を取得
        firstTensor = tensorDatas[0]
        coeffBlock = firstTensor.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            return None
        
        result = coeffBlock.data.copy()
        
        # 他のtensorと畳み込み乗算
        for tensorData in tensorDatas[1:]:
            coeffBlock = tensorData.getBlock(planeIdx, 0, 0)
            if coeffBlock:
                result = self._convolveTensorCoeffs(result, coeffBlock.data)
        
        return DataBlock(result, planeIdx, block.x, block.y)
    
    def _convolveTensorCoeffs(self, coeffs1, coeffs2):
        """係数行列の畳み込み乗算"""
        # numpyで2次元畳み込みを実装
        h1, w1 = coeffs1.shape
        h2, w2 = coeffs2.shape
        
        resultH = h1 + h2 - 1
        resultW = w1 + w2 - 1
        result = nh.zeros((resultH, resultW))
        
        # numpyのブロードキャストを活用した効率的な実装
        for i in range(h2):
            for j in range(w2):
                if coeffs2[i, j] != 0:
                    result[i:i+h1, j:j+w1] += coeffs1 * coeffs2[i, j]
        
        return result
