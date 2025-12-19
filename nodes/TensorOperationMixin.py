'''
TensorOperationMixin - tensor操作の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import FlowData
from base import DataBlock
import utils.numpy_helpers as nh

class TensorOperationMixin:
    """tensor 操作の共通機能を提供するMixin"""
    
    @classmethod
    def computeCombinedTensor(cls, tensorDatas, operation):
        """複数tensorを事前に統合計算"""
        if not tensorDatas:
            return None
        if len(tensorDatas) == 1:
            return tensorDatas[0]
        
        # 最初のtensorをベースとしてコピー
        result = FlowData(tensorDatas[0].headers.copy())

        # 出力の範囲を縦横最大にする
        width, height = tensorDatas[0].getDimensions()
        for tensorData in tensorDatas[1:]:
            w, h = tensorData.getDimensions()
            width  = max(width , w)
            height = max(height, h)
        result.setDimensions(width, height)
        
        # 最初のtensorのデータをコピー
        for block in tensorDatas[0].iterateBlocks():
            newBlock = DataBlock(block.data.copy(), block.planeIndex, block.x, block.y)
            result.setBlock(newBlock)
        
        # 残りのtensorを順次適用
        for tensorData in tensorDatas[1:]:
            for block in result.iterateBlocks():
                otherBlock = tensorData.getBlock(block.planeIndex, block.x, block.y)
                if otherBlock is not None:
                    block.data = operation(block.data, otherBlock.data)
        
        return result
    
    @classmethod
    def calculateTensorRange(cls, tensor, width, height):
        """多項式tensorの範囲を計算（四隅と中央で評価）"""
        def evalPoly(x, y):
            value = 0.0
            y_power = 1.0
            for j in range(tensor.shape[0]):
                x_power = 1.0
                for i in range(tensor.shape[1]):
                    value += tensor[j, i] * x_power * y_power
                    x_power *= x
                y_power *= y
            return value
        
        # 四隅と中央で評価
        v1 = evalPoly(0, 0)
        v2 = evalPoly(width-1, 0)
        v3 = evalPoly(0, height-1)
        v4 = evalPoly(width-1, height-1)
        v5 = evalPoly((width-1)/2, (height-1)/2)
        
        return min(v1, v2, v3, v4, v5), max(v1, v2, v3, v4, v5)
    
    @classmethod
    def calculateTensorBlock(cls, tensorData, planeIdx, x, y, blockShape, defaultValue=0.0):
        """テンソルデータからブロック内の各座標に対応する値を計算"""
        width, height = tensorData.getDimensions()
        planeCount = tensorData.getPlaneCount()
        if width < 1 or height < 1 or planeIdx >= planeCount:
            if defaultValue == 0.0:
                return nh.zeros(blockShape)
            elif defaultValue == 1.0:
                return nh.ones(blockShape)
            else:
                return nh.full(blockShape, defaultValue)
        
        # 指定プレーンの係数行列を取得
        coeffBlock = tensorData.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            if defaultValue == 0.0:
                return nh.zeros(blockShape)
            elif defaultValue == 1.0:
                return nh.ones(blockShape)
            else:
                return nh.full(blockShape, defaultValue)
        
        coeffMatrix = coeffBlock.data
        maxOrderY, maxOrderX = coeffMatrix.shape
        
        # ブロック内の座標配列を作成（スレッドセーフ: np.meshgrid 置き換え）
        blockHeight, blockWidth = blockShape
        y_indices = nh.arange(blockHeight).reshape(-1, 1)
        x_indices = nh.arange(blockWidth)
        y_coords = y + np.broadcast_to(y_indices, (blockHeight, blockWidth))
        x_coords = x + np.broadcast_to(x_indices, (blockHeight, blockWidth))
        
        # numpy配列演算で多項式計算
        result = nh.zeros(blockShape)
        y_power = nh.ones(x_coords.shape)
        for j in range(maxOrderY):
            x_power = nh.ones(x_coords.shape)
            for i in range(maxOrderX):
                coeff = coeffMatrix[j, i]
                if coeff != 0:
                    result += coeff * x_power * y_power
                x_power *= x_coords
            y_power *= y_coords
        
        return result