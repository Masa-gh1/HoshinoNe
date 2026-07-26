'''
CountNode - カウントノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import N1BlockOperationNode

class CountNode(N1BlockOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'count'
    # ノード名
    name      = 'カウント'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def getBaseDataIndex(self, inputDatas):
        """カウントではpolynomial,tensor がある場合は最初のtableデータを基準とする"""
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'table') if data.headers else 'table'
            if dataType != 'polynomial' and dataType != 'tensor':
                return i
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'table') if data.headers else 'table'
            if dataType != 'polynomial':
                return i
        return 0  # polynomialのみの場合は最初のpolynomialを基準とする
    
    def getOutputDimensions(self, baseData, inputDatas):
        """カウントでは全入力データを包含するサイズを使用"""
        self._outputDimensions = self.getUnionDimensions(inputDatas)
        return self._outputDimensions
    
    def processHeaders(self, baseData, inputDatas):
        """入力データ数に基づくdisplay_levelsを設定"""
        dataCount = len(inputDatas)
        return {
            'display_levels':{
                'min': 0.0,
                'exclusive_upper': float(dataCount)
            }
        }
    
    def processBlock(self, inputDatas, planeIndex, x, y):
        """単一ブロックのカウント処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        resultWidth, resultHeight = self._outputDimensions
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth  = min(BLOCK_SIZE, resultWidth  - x)
        result = nh.zeros((blockHeight, blockWidth))
        
        # スレッドローカルに作業用メモリを確保
        _invalidA = self.getLocal('_invalidA', (BLOCK_SIZE, BLOCK_SIZE), dtype=bool)
        
        # tableのカウント(NaN対応)
        for inputData in inputDatas:
            dataType = inputData.headers.get('type', 'table') if inputData.headers else 'table'
            if   dataType == 'polynomial':
                # polynomial なので全体を +1
                result += 1
            elif dataType == 'tensor':
                block = self.calculateTensorBlock(inputData, planeIndex, x, y, result.shape, defaultValue=np.nan)
                if not block.data is None:
                    # 計算範囲の作業用メモリを取得
                    invalidA = _invalidA[:result.shape[0], :result.shape[1]]
                    
                    # NaNでない有効なピクセルのみカウント
                    np.isnan(block.data, out=invalidA)
                    np.logical_not(invalidA, out=invalidA)
                    result += invalidA
            else:
                inputBlock = inputData.getBlock(planeIndex, x, y)
                if inputBlock:
                    # 計算範囲を取得
                    minH = min(blockHeight, inputBlock.data.shape[0])
                    minW = min(blockWidth , inputBlock.data.shape[1])
                    
                    # 計算範囲の結果を取得
                    res = result[:minH, :minW]
                    
                    # 計算範囲の作業用メモリを取得
                    invalidA = _invalidA[:minH, :minW]
                    
                    # 計算範囲のデータを取得
                    data = inputBlock.data[:minH, :minW]
                    
                    # NaNでない有効なピクセルのみカウント
                    np.isnan(data, out=invalidA)
                    np.logical_not(invalidA, out=invalidA)
                    res += invalidA
        
        return DataBlock(result, planeIndex, x, y)
    
    import threading
    local = threading.local()

    @staticmethod
    def getLocal(name, shape=None, dtype=None):
        if not hasattr(CountNode.local, "CountNode"):
            CountNode.local.CountNode = {}
        
        var = CountNode.local.CountNode.get(name, None)
        
        if var is None and shape is None:
            return None
        elif var is None or var.shape != shape or var.dtype != dtype:
            import numpy as np
            var = np.empty(shape, dtype=dtype)
            CountNode.local.CountNode[name] = var
            return var
        else:
            return var
