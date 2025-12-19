'''
MaxNode - 比較大ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, TensorOperationMixin 

class MaxNode(LazyNNOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "max", "比較大")
    
    def getColor(self):
        return self._color_func
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        primaryDatas = []
        auxiliaryTensors = []
        auxiliaryMatrices = []
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            if category == 'auxiliary':
                dataType = data.headers.get('type', 'matrix')
                if dataType == 'tensor':
                    auxiliaryTensors.append(data)
                else:
                    auxiliaryMatrices.append(data)
            else:
                primaryDatas.append(data)
        
        # auxiliary tensor を事前統合（比較小）
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxiliaryTensors, np.maximum)
        
        # auxiliary matrix を事前統合（最初のもののみ使用）
        self._combinedAuxiliaryMatrix = None
        if auxiliaryMatrices:
            self._combinedAuxiliaryMatrix = auxiliaryMatrices[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._MaxOperation, self._combinedAuxiliaryTensor, self._combinedAuxiliaryMatrix)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels, self._combinedAuxiliaryTensor)
        return lazyFlowData
    
    @classmethod
    def _MaxOperation(cls, flowData, planeIndex, x, y, combinedAuxiliaryTensor, combinedAuxiliaryMatrix):
        """スケール操作（事前統合されたauxiliaryデータを乗算）"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary tensorを比較小
        if combinedAuxiliaryTensor:
            tensorValues = cls.calculateTensorBlock(combinedAuxiliaryTensor, block.planeIndex, block.x, block.y, result.shape, defaultValue=1.0)
            result = np.maximum(result, tensorValues)
        
        # auxiliary matrixを比較小
        if combinedAuxiliaryMatrix:
            auxiliaryBlock = combinedAuxiliaryMatrix.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.maximum(result, auxiliaryBlock.data)
        
        return DataBlock(result, block.planeIndex, block.x, block.y)
    
    @classmethod
    def _computeDisplayLevels(cls, combinedAuxiliaryTensor):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            # クリップ処理では元の範囲を保持
            inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
            return {'display_levels': inputLevels} if inputLevels else None
        return compute