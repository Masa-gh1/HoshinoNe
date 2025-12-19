'''
ProductNode - 統合乗算ノード（N→1）

@author: Masakazu Inoue
'''

from base import N1BlockOperationNode, TensorOperationMixin, DataBlock
from config import BLOCK_SIZE
import numpy as np

class ProductNode(N1BlockOperationNode, TensorOperationMixin):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "product", "総積")
        self._combinedTensor = None    

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
    
    def getDisplayLevels(self, inputDatas):
        """入力データの乗算されたdisplay_levelsを返す"""
        # 全入力データのdisplay_levelsを収集
        allLevels = []
        for data in inputDatas:
            if data.headers and 'display_levels' in data.headers:
                levels = data.headers['display_levels']
                allLevels.append((levels['min'], levels['exclusive_upper']))
        
        if not allLevels:
            return None
        
        # 乗算の場合：範囲の積を計算
        minProduct = 1.0
        maxProduct = 1.0
        
        for minVal, maxVal in allLevels:
            # 範囲の積を計算（符号を考慮）
            products = [minProduct * minVal, minProduct * maxVal, maxProduct * minVal, maxProduct * maxVal]
            minProduct = min(products)
            maxProduct = max(products)
        
        return {
            'min': minProduct,
            'exclusive_upper': maxProduct
        }

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
            if not hasattr(self, '_combinedTensor') or self._combinedTensor is None:
                self._combinedTensor = self.computeCombinedTensor(tensorDatas, np.multiply)
            tensorBlock = self._combinedTensor.getBlock(block.planeIndex, block.x, block.y)
            return tensorBlock if tensorBlock else DataBlock(block.planeIndex, block.x, block.y, np.ones((1, 1)))
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
            if tensorDatas:
                if not hasattr(self, '_combinedTensor') or self._combinedTensor is None:
                    self._combinedTensor = self.computeCombinedTensor(tensorDatas, np.multiply)
                if self._combinedTensor:
                    tensorValues = self.calculateTensorBlock(self._combinedTensor, planeIdx, x, y, result.shape, defaultValue=1.0)
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
    
