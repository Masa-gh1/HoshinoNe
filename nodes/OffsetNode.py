'''
OffsetNode - オフセット加算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import NNBlockOperationNode, TensorOperationMixin, DataBlock

class OffsetNode(NNBlockOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "offset", "オフセット")
        self._combinedTensor = None
    
    def getColor(self):
        return self._color_op
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：matrixとtensorを分類し、tensorを統合"""
        matrixDatas = []
        tensorDatas = []
        
        for data in inputDatas:
            dataType = data.headers.get('type', 'matrix')
            if dataType == 'tensor':
                tensorDatas.append(data)
            else:
                matrixDatas.append(data)
        
        # tensorを事前統合
        self._combinedTensor = self.computeCombinedTensor(tensorDatas, np.add)
        
        return matrixDatas

    
    def getDisplayLevels(self, inputFlowData):
        """オフセット加算後のdisplay_levelsを計算"""
        if not inputFlowData.headers or 'display_levels' not in inputFlowData.headers:
            return None
        
        inputLevels = inputFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        if self._combinedTensor:
            coeffBlock = self._combinedTensor.getBlock(0, 0, 0)
            if coeffBlock:
                width, height = inputFlowData.getDimensions()
                offsetMin, offsetMax = self.calculateTensorRange(coeffBlock.data, width, height)
                return {
                    'min': inputMin + offsetMin,
                    'exclusive_upper': inputMax + offsetMax
                }
        
        return None
    
    def processBlock(self, block):
        """ブロック処理"""
        if self._combinedTensor is None:
            return block
        
        # tensor係数から実際の値を計算
        tensorValues = self._calculateTensorBlock(self._combinedTensor, block.planeIndex, block.x, block.y, block.data.shape)
        
        # 加算実行
        result = np.add(block.data, tensorValues)
        return DataBlock(block.planeIndex, block.x, block.y, result)
    
    def _calculateTensorBlock(self, tensorData, planeIdx, blockX, blockY, blockShape):
        """テンソルデータからブロック内の各座標に対応する値を計算"""
        width, height = tensorData.getDimensions()
        planeCount = tensorData.getPlaneCount()
        if width < 1 or height < 1 or planeIdx >= planeCount:
            return np.zeros(blockShape)
        
        coeffBlock = tensorData.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            return np.zeros(blockShape)
        
        coeffMatrix = coeffBlock.data
        maxOrderY, maxOrderX = coeffMatrix.shape
        
        blockHeight, blockWidth = blockShape
        by_coords, bx_coords = np.meshgrid(range(blockHeight), range(blockWidth), indexing='ij')
        x_coords = blockX + bx_coords
        y_coords = blockY + by_coords
        
        result = np.zeros(blockShape)
        y_power = np.ones_like(x_coords, dtype=np.float64)
        for j in range(maxOrderY):
            x_power = np.ones_like(x_coords, dtype=np.float64)
            for i in range(maxOrderX):
                coeff = coeffMatrix[j, i]
                if coeff != 0:
                    result += coeff * x_power * y_power
                x_power *= x_coords
            y_power *= y_coords
        
        return result
    

    
