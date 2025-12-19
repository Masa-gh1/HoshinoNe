'''
MergeNode class

@author: Masakazu Inoue
'''

from base import N1BlockOperationNode, DataBlock
import numpy as np

class AdditionNode(N1BlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "addition", "加算")
    
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
            return self._processTensorAddition(block, tensorDatas)
        else:
            # matrixとtensorの混在またはmatrixのみの場合
            resultWidth, resultHeight = self.getResultDimensions(inputDatas)
            from config import BLOCK_SIZE
            
            blockHeight = min(BLOCK_SIZE, resultHeight - y)
            blockWidth = min(BLOCK_SIZE, resultWidth - x)
            result = np.zeros((blockHeight, blockWidth), dtype=np.float64)
            
            # matrixデータの加算
            for inputData in matrixDatas:
                inputBlock = inputData.getBlock(planeIdx, x, y)
                if inputBlock:
                    minH = min(result.shape[0], inputBlock.data.shape[0])
                    minW = min(result.shape[1], inputBlock.data.shape[1])
                    result[:minH, :minW] += inputBlock.data[:minH, :minW]
            
            # tensorデータの加算
            for tensorData in tensorDatas:
                tensorValues = self._calculateTensorBlock(tensorData, planeIdx, x, y, result.shape)
                result += tensorValues
            
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
    
    def _calculateTensorBlock(self, tensorData, planeIdx, blockX, blockY, blockShape):
        """テンソルデータからブロック内の各座標に対応する値を計算"""
        width, height = tensorData.getDimensions()
        planeCount = tensorData.getPlaneCount()
        if width < 1 or height < 1 or planeIdx >= planeCount:
            return np.zeros(blockShape)
        
        # 指定プレーンの係数行列を取得
        coeffBlock = tensorData.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            return np.zeros(blockShape)
        
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