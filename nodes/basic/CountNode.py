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

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def getBaseDataIndex(self, inputDatas):
        """カウントではpolynomialがある場合は最初のtableデータを基準とする"""
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'table') if data.headers else 'table'
            if dataType != 'polynomial':
                return i
        return 0  # polynomialのみの場合は最初のpolynomialを基準とする
    
    def getResultDimensions(self, inputDatas):
        """カウントでは全入力データを包含するサイズを使用"""
        return self.getUnionDimensions(inputDatas)
    
    def setupDisplayLevels(self, outputFlowData, inputDatas):
        """入力データ数に基づくdisplay_levelsを設定"""
        dataCount = len(inputDatas)
        outputFlowData.headers['display_levels'] = {
            'min': 0.0,
            'exclusive_upper': float(dataCount)
        }
    
    def processBlock(self, block, inputDatas):
        """単一ブロックのカウント処理"""
        import numpy as np
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        from base import DataBlock

        planeIndex = block.planeIndex
        x, y = block.x, block.y
        
        # データタイプを分類
        polynomialDatas = []
        tableDatas = []
        
        for inputData in inputDatas:
            dataType = inputData.headers.get('type', 'table') if inputData.headers else 'table'
            if dataType == 'polynomial':
                polynomialDatas.append(inputData)
            else:
                tableDatas.append(inputData)
        
        # 全てpolynomialの場合はpolynomial数を返す
        if len(polynomialDatas) == len(inputDatas):
            return self._processPolynomialCount(block, polynomialDatas)
        else:
            # table と polynomial の混在または table のみの場合
            resultWidth, resultHeight = self.getResultDimensions(inputDatas)
            
            blockHeight = min(BLOCK_SIZE, resultHeight - y)
            blockWidth = min(BLOCK_SIZE, resultWidth - x)
            result = nh.zeros((blockHeight, blockWidth))
            
            # table データのカウント（NaN対応）
            for inputData in tableDatas:
                inputBlock = inputData.getBlock(planeIndex, x, y)
                if inputBlock:
                    minH = min(blockHeight, inputBlock.data.shape[0])
                    minW = min(blockWidth, inputBlock.data.shape[1])
                    # NaNでない有効なピクセルのみカウント
                    valid_mask = ~np.isnan(inputBlock.data[:minH, :minW])
                    result[:minH, :minW] += valid_mask
            
            # polynomialは全領域に影響するので全体にpolynomial数を加算
            if polynomialDatas:
                result += len(polynomialDatas)
            
            return DataBlock(result, planeIndex, x, y)
    
    def _processPolynomialCount(self, block, polynomialDatas):
        """全てpolynomialの場合のカウント処理"""
        import numpy as np
        from base import DataBlock

        planeIndex = block.planeIndex
        
        # 最初のpolynomialの係数行列を取得してサイズを決定
        firstPolynomial = polynomialDatas[0]
        coeffBlock = firstPolynomial.getBlock(planeIndex, 0, 0)
        if not coeffBlock:
            return None
        
        # polynomial数で埋めた行列を作成
        result = np.full_like(coeffBlock.data, len(polynomialDatas))
        
        return DataBlock(result, planeIndex, 0, 0)