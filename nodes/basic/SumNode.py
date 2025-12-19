'''
SumNode - 統合加算ノード（N→1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from config import BLOCK_SIZE
from base import DataBlock
from nodes import N1BlockOperationNode, TensorOperationMixin 
from utils import numpy_helpers as nh

class SumNode(N1BlockOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "sum", "総和")
        self._combinedTensor = None
    
    def getColor(self):
        return self._color_op
    
    def getBaseDataIndex(self, inputDatas):
        """加算ではtensorがある場合は最初のmatrixデータを基準とする"""
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'matrix') if data.headers else 'matrix'
            if dataType != 'tensor':
                return i
        return 0  # tensorのみの場合は最初のtensorを基準とする
    
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
        
        # データタイプを分類
        tensorDatas = []
        matrixDatas = []
        
        for inputData in inputDatas:
            dataType = inputData.headers.get('type', 'matrix') if inputData.headers else 'matrix'
            if dataType == 'tensor':
                tensorDatas.append(inputData)
            else:
                matrixDatas.append(inputData)
        
        # 全てtensorの場合はtensor加算
        if len(tensorDatas) == len(inputDatas):
            if self._combinedTensor is None:
                self._combinedTensor = self.computeCombinedTensor(tensorDatas, np.add)
            tensorBlock = self._combinedTensor.getBlock(block.planeIndex, block.x, block.y)
            return tensorBlock if tensorBlock else DataBlock(block.planeIndex, block.x, block.y, np.zeros((1, 1)))
        else:
            # matrixとtensorの混在またはmatrixのみの場合
            resultWidth, resultHeight = self.getResultDimensions(inputDatas)
            
            blockHeight = min(BLOCK_SIZE, resultHeight - y)
            blockWidth = min(BLOCK_SIZE, resultWidth - x)
            result = None
            
            # matrixデータの加算（NaN対応）
            for inputData in matrixDatas:
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
            if tensorDatas:
                if self._combinedTensor is None:
                    self._combinedTensor = self.computeCombinedTensor(tensorDatas, np.add)
                if self._combinedTensor:
                    tensorValues = self.calculateTensorBlock(self._combinedTensor, planeIdx, x, y, result.shape)
                    result = np.where(
                        np.isnan(result),
                        tensorValues,
                        result + tensorValues
                    )
            
            return DataBlock(planeIdx, x, y, result)
    
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
        
        return DataBlock(planeIdx, block.x, block.y, result)
    
