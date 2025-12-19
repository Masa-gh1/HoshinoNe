'''
MergeNode class

@author: Masakazu Inoue
'''

from base import N1BlockOperationNode, DataBlock
from config import BLOCK_SIZE
import numpy as np

class MultiplicationNode(N1BlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "multiplication", "乗算")    

    def getColor(self):
        return self._color_op
    
    def getBaseDataIndex(self, inputDatas):
        """乗算ではtensorがある場合は最初のmatrixデータを基準とする"""
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'matrix') if data.headers else 'matrix'
            if dataType != 'tensor':
                return i
        return 0  # tensorのみの場合は最初のtensorを基準とする
    
    def getResultDimensions(self, inputDatas):
        """乗算では全入力データを包含するサイズを使用"""
        return self.getUnionDimensions(inputDatas)

    def processBlock(self, block, inputDatas):
        """単一ブロックの乗算処理"""
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
        
        # 全てtensorの場合はtensor乗算
        if len(tensorDatas) == len(inputDatas):
            return self._processTensorMultiplication(block, tensorDatas)
        else:
            # matrixとtensorの混在またはmatrixのみの場合
            resultWidth, resultHeight = self.getResultDimensions(inputDatas)
            
            blockHeight = min(BLOCK_SIZE, resultHeight - y)
            blockWidth = min(BLOCK_SIZE, resultWidth - x)
            result = np.ones((blockHeight, blockWidth), dtype=np.float64)
            
            # matrixデータの乗算
            for inputData in matrixDatas:
                inputBlock = inputData.getBlock(planeIdx, x, y)
                if inputBlock:
                    minH = min(result.shape[0], inputBlock.data.shape[0])
                    minW = min(result.shape[1], inputBlock.data.shape[1])
                    result[:minH, :minW] *= inputBlock.data[:minH, :minW]
            
            # tensorデータの乗算
            for tensorData in tensorDatas:
                tensorValues = self._calculateTensorBlock(tensorData, planeIdx, x, y, result.shape)
                result *= tensorValues
            
            return DataBlock(planeIdx, x, y, result)
    
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
        
        return DataBlock(planeIdx, block.x, block.y, result)
    
    def _convolveTensorCoeffs(self, coeffs1, coeffs2):
        """係数行列の畳み込み乗算"""
        # numpyで2次元畳み込みを実装
        h1, w1 = coeffs1.shape
        h2, w2 = coeffs2.shape
        
        resultH = h1 + h2 - 1
        resultW = w1 + w2 - 1
        result = np.zeros((resultH, resultW), dtype=np.float64)
        
        # numpyのブロードキャストを活用した効率的な実装
        for i in range(h2):
            for j in range(w2):
                if coeffs2[i, j] != 0:
                    result[i:i+h1, j:j+w1] += coeffs1 * coeffs2[i, j]
        
        return result
    
    def _calculateTensorBlock(self, tensorData, planeIdx, blockX, blockY, blockShape):
        """テンソルデータからブロック内の各座標に対応する値を計算"""
        width, height = tensorData.getDimensions()
        planeCount = tensorData.getPlaneCount()
        if width < 1 or height < 1 or planeIdx >= planeCount:
            return np.ones(blockShape)
        
        # 指定プレーンの係数行列を取得
        coeffBlock = tensorData.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            return np.ones(blockShape)
        
        coeffMatrix = coeffBlock.data
        maxOrderY, maxOrderX = coeffMatrix.shape
        
        # ブロック内の座標配列を作成
        blockHeight, blockWidth = blockShape
        by_coords, bx_coords = np.meshgrid(range(blockHeight), range(blockWidth), indexing='ij')
        x_coords = blockX + bx_coords
        y_coords = blockY + by_coords
        
        # numpy配列演算で多項式計算
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