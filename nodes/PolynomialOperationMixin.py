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
        """複数 polynomial を統合計算
        
        Args:
            polynomialDatas: polynomial データのリスト
            operation: 係数演算関数 (加算・減算用)
        """
        if not polynomialDatas:
            return None
        if len(polynomialDatas) == 1:
            return polynomialDatas[0]
        
        # 最初の polynomial をベースとしてコピー
        result = FlowData(polynomialDatas[0].headers.copy())

        # 出力の範囲を縦横最大にする
        width, height = polynomialDatas[0].getDimensions()
        for polynomialData in polynomialDatas[1:]:
            w, h = polynomialData.getDimensions()
            width  = max(width , w)
            height = max(height, h)
        result.setDimensions(width, height)
        
        # operation から関数を判定
        if   np.add      == operation:
            combineFunc       = cls._addPolynomialPlane
            updateHeadersFunc = None
        elif np.multiply == operation:
            combineFunc       = cls._multiplyPolynomialPlane
            updateHeadersFunc = cls._updateHeaders
        else:
            combineFunc       = None
            updateHeadersFunc = cls._updateHeaders
        
        # 各プレーン毎に計算
        planeCount = polynomialDatas[0].getPlaneCount()
        if combineFunc:
            for planeIndex in range(planeCount):
                resultBlock = combineFunc(planeIndex, polynomialDatas)
                result.setBlock(resultBlock)
        else:
            for planeIndex in range(planeCount):
                # 最初の polynomial の係数行列を取得
                coeffBlock = polynomialDatas[0].getBlock(planeIndex, 0, 0)
                data = coeffBlock.data.copy()

                # 残りの polynomial を順次適用
                for polynomialData in polynomialDatas[1:]:
                    otherBlock = polynomialData.getBlock(planeIndex, 0, 0)
                    data = operation(data, otherBlock.data)
                    result.setBlock(DataBlock(data, planeIndex, 0, 0))
        
        # headers 更新
        if updateHeadersFunc:
            updateHeadersFunc(result)
        
        return result
    
    @classmethod
    def calculatePolynomialRange(cls, polynomial, width, height):
        """多項式 polynomial の範囲を計算（四隅と中央で評価）"""
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
    def calculatePolynomialBlock(cls, polynomialData, planeIndex, x, y, blockShape, defaultValue=0.0):
        """Polynomial データからブロック内の各座標に対応する値を計算"""
        width, height = polynomialData.getDimensions()
        planeCount = polynomialData.getPlaneCount()
        if width < 1 or height < 1 or planeIndex >= planeCount:
            if defaultValue == 0.0:
                return nh.zeros(blockShape)
            elif defaultValue == 1.0:
                return nh.ones(blockShape)
            else:
                return nh.full(blockShape, defaultValue)
        
        # 指定プレーンの係数行列を取得
        coeffBlock = polynomialData.getBlock(planeIndex, 0, 0)
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
        
        # numpy 配列演算で多項式計算
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
    
    @classmethod
    def _addPolynomialPlane(cls, planeIndex, polynomialDatas):
        """polynomial の加算処理"""
        # 最初の polynomial の係数行列を取得
        coeffBlock = polynomialDatas[0].getBlock(planeIndex, 0, 0)
        data = coeffBlock.data.copy()

        # 残りの polynomial を順次適用
        for polynomialData in polynomialDatas[1:]:
            otherBlock = polynomialData.getBlock(planeIndex, 0, 0)
            data = np.add(data, otherBlock.data)
        
        return DataBlock(data, planeIndex, 0, 0)

    @classmethod
    def _multiplyPolynomialPlane(cls, planeIndex, polynomialDatas):
        """polynomial の乗算処理（係数の畳み込み）"""
        # 最初の polynomial の係数行列を取得
        coeffBlock = polynomialDatas[0].getBlock(planeIndex, 0, 0)
        data = coeffBlock.data.copy()
        
        # 他の polynomial と畳み込み乗算
        for polynomialData in polynomialDatas[1:]:
            coeffBlock = polynomialData.getBlock(planeIndex, 0, 0)
            if coeffBlock:
                data = cls._convolvePolynomialCoeffs(data, coeffBlock.data)
        
        return DataBlock(data, planeIndex, 0, 0)
    
    @classmethod
    def _convolvePolynomialCoeffs(cls, coeffs1, coeffs2):
        """係数行列の畳み込み乗算"""
        h1, w1 = coeffs1.shape
        h2, w2 = coeffs2.shape
        
        resultH = h1 + h2 - 1
        resultW = w1 + w2 - 1
        result = nh.zeros((resultH, resultW))
        
        # numpy のブロードキャストを活用した効率的な実装
        for i in range(h2):
            for j in range(w2):
                if coeffs2[i, j] != 0:
                    result[i:i+h1, j:j+w1] += coeffs1 * coeffs2[i, j]
        
        return result
    
    @classmethod
    def _updateHeaders(cls, flowData):
        """乗算後の headers を更新"""
        if 'max_orders' in flowData.headers:
            # 最初のブロックから次数を取得
            block = flowData.getBlock(0, 0, 0)
            if block:
                h, w = block.data.shape
                flowData.headers['max_orders'] = [w - 1, h - 1]
