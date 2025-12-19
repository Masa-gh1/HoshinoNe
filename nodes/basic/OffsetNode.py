'''
OffsetNode - 加算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, TensorOperationMixin 

class OffsetNode(LazyNNOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "offset", "加算")
        self._combinedTensor = None
    
    def getColor(self):
        return self._color_op
    
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
        
        # auxiliary tensorを事前統合
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxiliaryTensors, np.add)
        
        # auxiliary matrixを事前統合（最初のものをベースに加算）
        self._combinedAuxiliaryMatrix = None
        if auxiliaryMatrices:
            self._combinedAuxiliaryMatrix = auxiliaryMatrices[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._offsetOperation, self._combinedAuxiliaryTensor, self._combinedAuxiliaryMatrix)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels, self._combinedAuxiliaryTensor, self._combinedAuxiliaryMatrix)
        return lazyFlowData
    
    @classmethod
    def _offsetOperation(cls, flowData, planeIndex, x, y, combinedAuxiliaryTensor, combinedAuxiliaryMatrix):
        """オフセット操作（事前統合されたauxiliaryデータを加算）"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary tensorを加算
        if combinedAuxiliaryTensor:
            tensorValues = cls.calculateTensorBlock(combinedAuxiliaryTensor, block.planeIndex, block.x, block.y, result.shape)
            result = np.add(result, tensorValues)
        
        # auxiliary matrixを加算
        if combinedAuxiliaryMatrix:
            auxiliaryBlock = combinedAuxiliaryMatrix.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.add(result, auxiliaryBlock.data)
        
        return DataBlock(result, block.planeIndex, block.x, block.y)
    
    @classmethod
    def _computeDisplayLevels(cls, combinedAuxiliaryTensor, combinedAuxiliaryMatrix):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            try:
                inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
                if not inputLevels or 'min' not in inputLevels or 'exclusive_upper' not in inputLevels:
                    return None
                    
                inputMin = inputLevels['min']
                inputMax = inputLevels['exclusive_upper']
                
                if combinedAuxiliaryTensor:
                    coeffBlock = combinedAuxiliaryTensor.getBlock(0, 0, 0)
                    if coeffBlock:
                        width, height = lazyFlowData.sourceFlowData.getDimensions()
                        offsetMin, offsetMax = cls.calculateTensorRange(coeffBlock.data, width, height)
                        return {
                            'display_levels': {
                                'min': inputMin + offsetMin,
                                'exclusive_upper': inputMax + offsetMax
                            }
                        }
                # auxiliary matrixの場合は範囲計算が複雑なので省略
                # auxiliaryがない場合は元のdisplay_levelsをそのまま返す
                return {'display_levels': inputLevels}
            except (KeyError, AttributeError):
                return None
        return compute
    
