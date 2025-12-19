'''
ScaleNode - スケール乗算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import NNBlockOperationNode, TensorOperationMixin, DataBlock

class ScaleNode(NNBlockOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "scale", "スケール")
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
        self._combinedTensor = self.computeCombinedTensor(tensorDatas, np.multiply)
        
        return matrixDatas
    
    def setupDisplayLevels(self, outputFlowData, inputFlowData):
        """スケール乗算後のdisplay_levelsを設定"""
        if not inputFlowData.headers or 'display_levels' not in inputFlowData.headers:
            return
        
        inputLevels = inputFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        if self._combinedTensor:
            coeffBlock = self._combinedTensor.getBlock(0, 0, 0)
            if coeffBlock:
                width, height = inputFlowData.getDimensions()
                scaleMin, scaleMax = self.calculateTensorRange(coeffBlock.data, width, height)
                
                products = [inputMin * scaleMin, inputMin * scaleMax, inputMax * scaleMin, inputMax * scaleMax]
                
                outputFlowData.headers['display_levels'] = {
                    'min': min(products),
                    'exclusive_upper': max(products)
                }
                return
        
        # tensorがない場合は入力のまま
        outputFlowData.headers['display_levels'] = inputLevels
    
    def processBlock(self, block):
        """ブロック処理"""
        if self._combinedTensor is None:
            return block
        
        # tensor係数から実際の値を計算
        tensorValues = self.calculateTensorBlock(self._combinedTensor, block.planeIndex, block.x, block.y, block.data.shape, defaultValue=1.0)
        
        # 乗算実行
        result = np.multiply(block.data, tensorValues)
        return DataBlock(block.planeIndex, block.x, block.y, result)
