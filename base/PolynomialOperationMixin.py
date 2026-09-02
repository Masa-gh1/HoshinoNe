'''
PolynomialOperationMixin - polynomial 操作の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from .DataBlock import DataBlock
    from .FlowData import FlowData

class PolynomialOperationMixin:
    """polynomial 操作の共通機能を提供するMixin"""
    
    @classmethod
    def computeCombinedPolynomial(cls, polynomialDatas:list[FlowData], operation:callable) -> FlowData:
        """
        複数 polynomial を統合
        
        Args:
            polynomialDatas: polynomial データのリスト
            operation: 係数演算関数
        """
        import numpy as np
        from base import FlowData
        from base import DataBlock

        if not polynomialDatas:
            return None
        if 1 == len(polynomialDatas):
            return polynomialDatas[0]
        
        # 最初の polynomial をベースとしてコピー
        result = FlowData(polynomialDatas[0].headers.copy())

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
                h, w = resultBlock.data.shape
                result.setDimensions(w, h)
                result.setBlock(resultBlock)
        else:
            for planeIndex in range(planeCount):
                # 最初の polynomial の係数行列を取得
                coeffBlock = polynomialDatas[0].getBlock(planeIndex, 0, 0)
                h, w = coeffBlock.data.shape
                result.setDimensions(w, h)
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
    def calculatePolynomialRange(cls, polynomial:np.ndarray, width:int, height:int) -> tuple[float, float]:
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
    def calculatePolynomialBlock(cls, polynomialFlowData:FlowData, planeIndex:int, x:int, y:int, blockShape:tuple, defaultValue:float=0.0) -> DataBlock:
        """Polynomial データからブロック内の各座標に対応する値を計算"""
        import numpy as np
        import utils.numpy_helpers as nh
        from base import DataBlock
        
        width, height = polynomialFlowData.getDimensions()

        if 1 == polynomialFlowData.getPlaneCount():
            planeIndex = 0
        
        # 指定プレーンの係数行列を取得
        coeffBlock = polynomialFlowData.getBlock(planeIndex, 0, 0)
        if not coeffBlock:
            if 0.0 == defaultValue:
                return DataBlock(nh.zeros(blockShape), planeIndex, x, y)
            elif 1.0 == defaultValue:
                return DataBlock(nh.ones(blockShape), planeIndex, x, y)
            else:
                return DataBlock(nh.full(blockShape, defaultValue), planeIndex, x, y)
        
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
        y_power = nh.ones(y_coords.shape)
        for j in range(maxOrderY):
            x_power = nh.ones(x_coords.shape)
            for i in range(maxOrderX):
                coeff = coeffMatrix[j, i]
                if coeff != 0:
                    result += coeff * x_power * y_power
                x_power *= x_coords
            y_power *= y_coords
        
        return DataBlock(result, planeIndex, x, y)
    
    @classmethod
    def _addPolynomialPlane(cls, planeIndex, polynomialDatas):
        """polynomial の加算処理"""
        import numpy as np
        from base import DataBlock
        
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
        from base import DataBlock

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
        import utils.numpy_helpers as nh

        h1, w1 = coeffs1.shape
        h2, w2 = coeffs2.shape
        
        resultH = h1 + h2 - 1
        resultW = w1 + w2 - 1
        result = nh.zeros((resultH, resultW))
        
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
