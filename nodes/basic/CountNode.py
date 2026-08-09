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
    
    def blockOperation(self, blocks, planeIndex, x, y):
        """単一ブロックのカウント処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        resultWidth, resultHeight = self._outputDimensions
        
        resultHeight = min(BLOCK_SIZE, resultHeight - y)
        resultWidth  = min(BLOCK_SIZE, resultWidth  - x)
        result = nh.zeros((resultHeight, resultWidth))
        
        # スレッドローカルに作業用メモリを確保
        _invalidA = self.getLocal('_invalidA', (BLOCK_SIZE, BLOCK_SIZE), dtype=bool)
        
        # tableのカウント(NaN対応)
        for block in blocks:
            if block:
                # 計算範囲を取得
                blockH, blockW = block.data.shape
                blockH = min(resultHeight, blockH) if 1<blockH else resultHeight # ブロックの高さが1の場合、ブロードキャストにする
                blockW = min(resultWidth , blockW) if 1<blockW else resultWidth  # ブロックの幅が1の場合、ブロードキャストにする
                minH = min(resultHeight, blockH)
                minW = min(resultWidth , blockW)
                
                # 計算範囲の結果を取得
                res = result[:minH, :minW]
                
                # 計算範囲の作業用メモリを取得
                invalidA = _invalidA[:minH, :minW]
                
                # 計算範囲のデータを取得
                data = block.data[:blockH, :blockW]
                
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
