'''
MergeNode class

@author: Masakazu Inoue
'''

from base import N1BlockOperationNode, DataBlock
import numpy as np

class MultiplicationNode(N1BlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "multiplication", "乗算")    

    def processBlock(self, block, inputDatas):
        """単一ブロックの乗算処理"""
        planeIdx = block.planeIndex
        x, y = block.x, block.y
        
        # データタイプ別に分類
        imageArrays = []
        tensorDatas = []
        
        for inputData in inputDatas:
            dataType = inputData.headers.get('type', 'matrix') if inputData.headers else 'matrix'
            
            if dataType == 'tensor':
                tensorDatas.append(inputData)
            else:
                inputBlock = inputData.getBlock(planeIdx, x, y)
                if inputBlock:
                    imageArrays.append(inputBlock.data)
        
        # 乗算処理
        if imageArrays:
            # 全て同じサイズかチェック
            firstShape = imageArrays[0].shape
            if all(arr.shape == firstShape for arr in imageArrays):
                result = np.prod(imageArrays, axis=0)
            else:
                # サイズが異なる場合はパディングしてnp.prodを使用
                maxHeight = max(arr.shape[0] for arr in imageArrays)
                maxWidth = max(arr.shape[1] for arr in imageArrays)
                paddedArrays = []
                for arr in imageArrays:
                    padded = np.pad(arr, ((0, maxHeight - arr.shape[0]), (0, maxWidth - arr.shape[1])), mode='constant', constant_values=1)
                    paddedArrays.append(padded)
                result = np.prod(paddedArrays, axis=0)
        else:
            result = np.ones_like(block.data)
        
        # 全てのtensorから計算された値を乗算
        for tensorData in tensorDatas:
            tensorValues = self._calculateTensorBlock(tensorData, planeIdx, x, y, result.shape)
            result *= tensorValues
        
        return DataBlock(planeIdx, x, y, result)
    
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