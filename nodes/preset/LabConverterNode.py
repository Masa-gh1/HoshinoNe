'''
LabConverterNode - Lab 変換(白色点正規化なし)ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode, PolynomialOperationMixin 

class LabConverterNode(LazyNNOperationNode, PolynomialOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'lab_converter'
    # ノード名
    name      = 'Lab変換'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類し、auxiliaryを事前統合"""
        import numpy as np
        
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
        return LabConverterLazyFlowData(inputData)
    
class LabConverterLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y):
        """Lab 変換操作(正規化なし)"""
        from base import DataBlock

        mode = flowData.getMode()
        if not mode in ["RGB", "RGBA", "RGBG"]:
            # Labはそのまま通す
            result = flowData.getBlock(planeIndex, x, y).data
            return DataBlock(result, planeIndex, x, y)
        else:
            if mode in ["RGB", "RGBA"]:
                _R = flowData.getBlock( 0, x, y).data # R
                _G = flowData.getBlock( 1, x, y).data # G
                _B = flowData.getBlock( 2, x, y).data # B
            else: # RGBG
                _R  = flowData.getBlock( 0, x, y).data # R
                _G1 = flowData.getBlock( 1, x, y).data # G1
                _B  = flowData.getBlock( 2, x, y).data # B
                _G2 = flowData.getBlock( 3, x, y).data # G2
                _G = (_G1 + _G2) / 2                   # G
            
            # RGB/Lab変換
            if 0 == planeIndex: # L
                _L = (_R + _G + _B) / 3.0
                return DataBlock(_L, planeIndex, x, y)
            elif 1 == planeIndex: # a
                _a = (_R - _G         ) / 1.41421356237
                return DataBlock(_a, planeIndex, x, y)
            elif 2 == planeIndex: # b
                _b = (_R + _G - 2.0*_B) / 2.44948974278
                return DataBlock(_b, planeIndex, x, y)
    
    def getLazyHeaderkeys(self):
        return ['mode', 'planes']
    
    def headerOperation(self, lazyFlowData, key):
        # Lab変換では mode plane が変わる
        return {
            'mode': 'Lab',
            'planes': ['L', 'a', 'b'],
        }
