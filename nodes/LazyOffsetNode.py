'''
LazyOffsetNode - LazyFlowDataを用いるオフセット加算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import LazyBlockOperationNode, TensorOperationMixin, DataBlock
from base.LazyFlowData import LazyFlowData

class LazyOffsetNode(LazyBlockOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "lazy_offset", "オフセット(遅延実行)")
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
            # 複数のauxiliary matrixがある場合は統合が必要
            # 現在は最初のもののみ使用
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._offsetOperation)
        lazyFlowData.addHeaderCompute('display_levels', self._computeDisplayLevels)
        return lazyFlowData
    
    def _offsetOperation(self, flowData, planeIndex, blockX, blockY):
        """オフセット操作（事前統合されたauxiliaryデータを加算）"""
        block = flowData.getBlock(planeIndex, blockX * flowData._blockSize, blockY * flowData._blockSize)
        if not block:
            return block
        
        result = block.data.copy()
        
        # auxiliary tensorを加算
        if self._combinedAuxiliaryTensor:
            tensorValues = self.calculateTensorBlock(self._combinedAuxiliaryTensor, block.planeIndex, block.x, block.y, result.shape)
            result = np.add(result, tensorValues)
        
        # auxiliary matrixを加算
        if self._combinedAuxiliaryMatrix:
            auxiliaryBlock = self._combinedAuxiliaryMatrix.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                result = np.add(result, auxiliaryBlock.data)
        
        return DataBlock(block.planeIndex, block.x, block.y, result)
    
    def _computeDisplayLevels(self):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            try:
                inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
                if not inputLevels or 'min' not in inputLevels or 'exclusive_upper' not in inputLevels:
                    return None
                    
                inputMin = inputLevels['min']
                inputMax = inputLevels['exclusive_upper']
                
                if self._combinedAuxiliaryTensor:
                    coeffBlock = self._combinedAuxiliaryTensor.getBlock(0, 0, 0)
                    if coeffBlock:
                        width, height = lazyFlowData.sourceFlowData.getDimensions()
                        offsetMin, offsetMax = self.calculateTensorRange(coeffBlock.data, width, height)
                        return {
                            'display_levels': {
                                'min': inputMin + offsetMin,
                                'exclusive_upper': inputMax + offsetMax
                            }
                        }
                # auxiliary matrixの場合は範囲計算が複雑なので省略
                # 必要に応じて後で実装可能
                # tensorがない場合はNoneを返す（元のOffsetNodeと同じ動作）
                return None
            except (KeyError, AttributeError):
                return None
        return compute
    
