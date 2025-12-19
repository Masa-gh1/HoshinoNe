'''
SumNode - 総和ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from config import BLOCK_SIZE
from base import DataBlock
from nodes import N1BlockOperationNode, TensorOperationMixin, VectorOperationMixin
from utils import numpy_helpers as nh

class SumNode(N1BlockOperationNode, TensorOperationMixin, VectorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "sum", "総和")
    
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
        
        # vector を事前統合(加算)
        self._combinedVector = self.computeCombinedVector(vectors, np.add)
        
        # tensor を事前統合(加算)
        self._combinedTensor = self.computeCombinedTensor(tensors, np.add)
        
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
            'min': minSum,
            'exclusive_upper': maxSum
        }
    
    def processBlock(self, block, inputDatas):
        """単一ブロックの加算処理"""
        planeIdx = block.planeIndex
        x, y = block.x, block.y
        
        resultWidth, resultHeight = self.getResultDimensions(inputDatas)
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth = min(BLOCK_SIZE, resultWidth - x)
        result = None
        
        # matrixデータの加算（NaN対応）
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
        
        # matrixデータがない場合の初期化
        if result is None:
            result = nh.nans((blockHeight, blockWidth))
        
        # tensorデータの加算（NaN対応）
        if self._combinedTensor:
            tensorValues = self.calculateTensorBlock(self._combinedTensor, planeIdx, x, y, result.shape)
            result = np.where(
                np.isnan(result),
                tensorValues,
                result + tensorValues
            )
        
        return DataBlock(result, planeIdx, x, y)
    
    def _processTensorAddition(self, block, tensorDatas):
        """全てtensorの場合の加算処理"""
        planeIdx = block.planeIndex
        
        # 最初のtensorの係数行列を取得
        firstTensor = tensorDatas[0]
        coeffBlock = firstTensor.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            return None
        
        result = coeffBlock.data.copy()
        
        # 他のtensorの係数行列を加算
        for tensorData in tensorDatas[1:]:
            coeffBlock = tensorData.getBlock(planeIdx, 0, 0)
            if coeffBlock:
                # サイズを合わせて加算
                minH = min(result.shape[0], coeffBlock.data.shape[0])
                minW = min(result.shape[1], coeffBlock.data.shape[1])
                result[:minH, :minW] += coeffBlock.data[:minH, :minW]
        
        return DataBlock(result, planeIdx, block.x, block.y)
    
