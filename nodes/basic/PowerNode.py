'''
PowerNode - 冪算ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, TensorOperationMixin 

class PowerNode(LazyNNOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "power", "冪算")
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
        
        # auxiliary tensorを事前統合（加算：指数の加算）
        self._combinedAuxiliaryTensor = self.computeCombinedTensor(auxiliaryTensors, np.add)
        
        # auxiliary matrixを事前統合（最初のもののみ使用）
        self._combinedAuxiliaryMatrix = None
        if auxiliaryMatrices:
            self._combinedAuxiliaryMatrix = auxiliaryMatrices[0]
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._powerOperation, self._combinedAuxiliaryTensor, self._combinedAuxiliaryMatrix)
        lazyFlowData.addHeaderOperation('display_levels', self._computeDisplayLevels, self._combinedAuxiliaryTensor, self._combinedAuxiliaryMatrix)
        return lazyFlowData
    
    @classmethod
    def _powerOperation(cls, flowData, planeIndex, x, y, combinedAuxiliaryTensor, combinedAuxiliaryMatrix):
        """冪乗操作（事前統合されたauxiliaryデータを指数として使用）"""
        block = flowData.getBlock(planeIndex, x, y)
        if not block:
            return block
        
        result = block.data.copy()
        is_complex = np.iscomplexobj(result)
        
        # auxiliary tensorを指数として冪乗
        if combinedAuxiliaryTensor:
            tensorValues = cls.calculateTensorBlock(combinedAuxiliaryTensor, block.planeIndex, block.x, block.y, result.shape, defaultValue=1.0)
            power_result = np.power(result, tensorValues)
            result = power_result if is_complex else np.real(power_result)
        
        # auxiliary matrixを指数として冪乗
        if combinedAuxiliaryMatrix:
            auxiliaryBlock = combinedAuxiliaryMatrix.getBlock(planeIndex, block.x, block.y)
            if auxiliaryBlock:
                power_result = np.power(result, auxiliaryBlock.data)
                result = power_result if is_complex else np.real(power_result)
        
        return DataBlock( result, block.planeIndex, block.x, block.y)
    
    @classmethod
    def _computeDisplayLevels(cls, combinedAuxiliaryTensor, combinedAuxiliaryMatrix):
        """display_levelsを計算"""
        def compute(lazyFlowData):
            inputLevels = lazyFlowData.sourceFlowData.headers['display_levels']
            if not inputLevels or 'min' not in inputLevels or 'exclusive_upper' not in inputLevels:
                return None
                
            inputMin = inputLevels['min']
            inputMax = inputLevels['exclusive_upper']
            
            if combinedAuxiliaryTensor:
                tensor = combinedAuxiliaryTensor.getBlock(0, 0, 0)
                if tensor:
                    width, height = lazyFlowData.sourceFlowData.getDimensions()
                    expMin, expMax = cls.calculateTensorRange(tensor.data, width, height)
                    
                    # 冪乗の範囲計算（実数部のみ）
                    powers = [np.real(inputMin ** expMin), np.real(inputMin ** expMax), 
                             np.real(inputMax ** expMin), np.real(inputMax ** expMax)]
                    return {
                        'display_levels': {
                            'min': min(powers),
                            'exclusive_upper': max(powers)
                        }
                    }
            
            # 複雑な場合は元のdisplay_levelsをそのまま返す
            return {'display_levels': inputLevels}
        return compute