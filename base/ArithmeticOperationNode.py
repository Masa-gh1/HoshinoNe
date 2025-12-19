'''
ArithmeticOperationNode abstract class

@author: Masakazu Inoue
'''

from abc import abstractmethod
from .N1BlockOperationNode import N1BlockOperationNode
import numpy as np

class ArithmeticOperationNode(N1BlockOperationNode):
    """算術演算ノードの基底クラス"""
    
    def getColor(self):
        return self._color_op
    
    def getBaseDataIndex(self, inputDatas):
        """算術演算では最初の非tensorデータを基準とする"""
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'matrix') if data.headers else 'matrix'
            if dataType != 'tensor':
                return i
        return 0
    
    def getResultDimensions(self, inputDatas):
        """算術演算では全入力データを包含するサイズを使用"""
        return self.getUnionDimensions(inputDatas)
    
    def processBlock(self, block, inputDatas):
        """算術演算の共通ブロック処理"""
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
        
        # 全てtensorの場合はtensor演算
        if len(tensorDatas) == len(inputDatas):
            return self.processTensorOperation(block, tensorDatas)
        else:
            return self.processMatrixOperation(block, inputDatas, matrixDatas, tensorDatas)
    
    @abstractmethod
    def processTensorOperation(self, block, tensorDatas):
        """tensor同士の演算（サブクラスで実装）"""
        pass
    
    @abstractmethod
    def processMatrixOperation(self, block, inputDatas, matrixDatas, tensorDatas):
        """matrix/tensor混在演算（サブクラスで実装）"""
        pass
    
    def calculateTensorBlock(self, tensorData, planeIdx, blockX, blockY, blockShape):
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