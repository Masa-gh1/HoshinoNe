'''
RGBConverterNode - RGB 変換(正規化なし)ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np

from base.FlowNode_CONST import *
from base import DataBlock
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class RGBConverterNode(LazyNNOperationNode, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'rgb_converter'
    # ノード名
    name      = 'RGB変換'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        primaryDatas = []
        auxiliaryPolynomials = []
        auxiliaryTables = []
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            if category == 'auxiliary':
                dataType = data.headers.get('type', 'table')
                if dataType == 'polynomial':
                    auxiliaryPolynomials.append(data)
                else:
                    auxiliaryTables.append(data)
            else:
                primaryDatas.append(data)
        
        # auxiliary polynomialを事前統合
        self._combinedAuxiliaryPolynomial = self.computeCombinedPolynomial(auxiliaryPolynomials, np.add)
        
        # auxiliary tableを事前統合
        self._combinedAuxiliaryTable = None
        if auxiliaryTables:
            self._combinedAuxiliaryTable = auxiliaryTables[0]
            for table in auxiliaryTables[1:]:
                self._combinedAuxiliaryTable += table
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        lazyFlowData = LazyFlowData(inputData)
        lazyFlowData.addOperation(self._labConverterOperation)
        lazyFlowData.addHeaderOperation('mode'  , self._computeHeaders)
        lazyFlowData.addHeaderOperation('planes', self._computeHeaders)
        return lazyFlowData
    
    @staticmethod
    def _labConverterOperation(flowData, planeIndex, x, y):
        """RGB 変換 (正規化なし)"""
        mode = flowData.getMode()
        if not mode in ["Lab", "RGBA", "RGBG"]:
            # RGBはそのまま通す
            result = flowData.getBlock(planeIndex, x, y).data
            return DataBlock(result, planeIndex, x, y)
        elif "Lab" == mode:
            # Lab/RGB変換(正規化なし)
            if   0 == planeIndex: # R
                _L = flowData.getBlock( 0, x, y).data # L
                _a = flowData.getBlock( 1, x, y).data # a
                #b = flowData.getBlock( 2, x, y).data # b
                _R = _L + _a
                #B = _L + _b
                #G = 3.0 * _L - _R - _B
                return DataBlock(_R, planeIndex, x, y)
            elif 1 == planeIndex: # G
                _L = flowData.getBlock( 0, x, y).data # L
                _a = flowData.getBlock( 1, x, y).data # a
                _b = flowData.getBlock( 2, x, y).data # b
                _R = _L + _a
                _B = _L + _b
                _G = 3.0 * _L - _R - _B
                return DataBlock(_G, planeIndex, x, y)
            elif 2 == planeIndex: # B
                _L = flowData.getBlock( 0, x, y).data # L
                #a = flowData.getBlock( 1, x, y).data # a
                _b = flowData.getBlock( 2, x, y).data # b
                #R = _L + _a
                _B = _L + _b
                #G = 3.0 * _L - _R - _B
                return DataBlock(_B, planeIndex, x, y)
        elif "RGBA" == mode:
            if   0 == planeIndex: # R
                _R = flowData.getBlock( 0, x, y).data # R
                return DataBlock(_R, planeIndex, x, y)
            elif 1 == planeIndex: # G
                _G = flowData.getBlock( 1, x, y).data # G
                return DataBlock(_G, planeIndex, x, y)
            elif 2 == planeIndex: # B
                _B = flowData.getBlock( 2, x, y).data # B
                return DataBlock(_B, planeIndex, x, y)
        else: # RGBG
            if   0 == planeIndex: # R
                _R  = flowData.getBlock( 0, x, y).data # R
                return DataBlock(_R, planeIndex, x, y)
            elif 1 == planeIndex: # G
                _G1 = flowData.getBlock( 1, x, y).data # G1
                _G2 = flowData.getBlock( 3, x, y).data # G2
                _G = (_G1 + _G2) / 2                   # G
                return DataBlock(_G, planeIndex, x, y)
            elif 2 == planeIndex: # B
                _B  = flowData.getBlock( 2, x, y).data # B
                return DataBlock(_B, planeIndex, x, y)
    
    @staticmethod
    def _computeHeaders(lazyFlowData):
        """ヘッダーを計算"""
        # Lab変換では mode plane が変わる
        return {
            'mode': 'RGB',
            'planes': ['R', 'G', 'B'],
        }
