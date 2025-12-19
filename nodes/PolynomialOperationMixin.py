'''
PolynomialOperationMixin - polynomial操作の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
from base import FlowData
from base import DataBlock
import utils.numpy_helpers as nh

class PolynomialOperationMixin:
    """polynomial 操作の共通機能を提供するMixin"""
    
    @classmethod
    def computeCombinedPolynomial(cls, polynomialDatas, operation):
        """複数polynomialを事前に統合計算"""
        if not polynomialDatas:
            return None
        if len(polynomialDatas) == 1:
            return polynomialDatas[0]
        
        # 最初のpolynomialをベースとしてコピー
        result = FlowData(polynomialDatas[0].headers.copy())

        # 出力の範囲を縦横最大にする
        width, height = polynomialDatas[0].getDimensions()
        for polynomialData in polynomialDatas[1:]:
            w, h = polynomialData.getDimensions()
            width  = max(width , w)
            height = max(height, h)
        result.setDimensions(width, height)
        
        # 最初のpolynomialのデータをコピー
        for block in polynomialDatas[0].iterateBlocks():
            newBlock = DataBlock(block.data.copy(), block.planeIndex, block.x, block.y)
            result.setBlock(newBlock)
        
        # 残りのpolynomialを順次適用
        for polynomialData in polynomialDatas[1:]:
            for block in result.iterateBlocks():
                otherBlock = polynomialData.getBlock(block.planeIndex, block.x, block.y)
                if otherBlock is not None:
                    block.data = operation(block.data, otherBlock.data)
        
        return result
    
    @classmethod
    def calculatePolynomialRange(cls, polynomial, width, height):
        """多項式polynomialの範囲を計算（四隅と中央で評価）"""
        def evalPoly(x, y):
            value = 0.0
            y_power = 1.0
            for j in range(polynomial.shape[0]):
                x_power = 1.0
                for i in range(polynomial.shape[1]):
                    value += polynomial[j, i] * x_power * y_power
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
    def calculatePolynomialBlock(cls, polynomialData, planeIdx, x, y, blockShape, defaultValue=0.0):
        """Polynomialデータからブロック内の各座標に対応する値を計算"""
        width, height = polynomialData.getDimensions()
        planeCount = polynomialData.getPlaneCount()
        if width < 1 or height < 1 or planeIdx >= planeCount:
            if defaultValue == 0.0:
                return nh.zeros(blockShape)
            elif defaultValue == 1.0:
                return nh.ones(blockShape)
            else:
                return nh.full(blockShape, defaultValue)
        
        # 指定プレーンの係数行列を取得
        coeffBlock = polynomialData.getBlock(planeIdx, 0, 0)
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