'''
CountNode - カウントノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from config import BLOCK_SIZE
from base import DataBlock
from nodes import N1BlockOperationNode
from utils import numpy_helpers as nh

class CountNode(N1BlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "count", "カウント")
    
    def getColor(self):
        return self._color_func
    
    def getBaseDataIndex(self, inputDatas):
        """カウントではtensorがある場合は最初のmatrixデータを基準とする"""
        for i, data in enumerate(inputDatas):
            dataType = data.headers.get('type', 'matrix') if data.headers else 'matrix'
            if dataType != 'tensor':
                return i
        return 0  # tensorのみの場合は最初のtensorを基準とする
    
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
        planeIdx = block.planeIndex
        x, y = block.x, block.y
        
        # データタイプを分類
        tensorDatas = []
        matrixDatas = []
        
        for inputData in inputDatas:
            dataType = inputData.headers.get('type', 'matrix') if inputData.headers else 'matrix'
            if dataType == 'tensor':
                tensorDatas.append(inputData)
            else:
                matrixDatas.append(inputData)
        
        # 全てtensorの場合はtensor数を返す
        if len(tensorDatas) == len(inputDatas):
            return self._processTensorCount(block, tensorDatas)
        else:
            # matrixとtensorの混在またはmatrixのみの場合
            resultWidth, resultHeight = self.getResultDimensions(inputDatas)
            
            blockHeight = min(BLOCK_SIZE, resultHeight - y)
            blockWidth = min(BLOCK_SIZE, resultWidth - x)
            result = nh.zeros((blockHeight, blockWidth))
            
            # matrixデータのカウント（NaN対応）
            for inputData in matrixDatas:
                inputBlock = inputData.getBlock(planeIdx, x, y)
                if inputBlock:
                    minH = min(blockHeight, inputBlock.data.shape[0])
                    minW = min(blockWidth, inputBlock.data.shape[1])
                    # NaNでない有効なピクセルのみカウント
                    valid_mask = ~np.isnan(inputBlock.data[:minH, :minW])
                    result[:minH, :minW] += valid_mask
            
            # tensorは全領域に影響するので全体にtensor数を加算
            if tensorDatas:
                result += len(tensorDatas)
            
            return DataBlock(result, planeIdx, x, y)
    
    def _processTensorCount(self, block, tensorDatas):
        """全てtensorの場合のカウント処理"""
        planeIdx = block.planeIndex
        
        # 最初のtensorの係数行列を取得してサイズを決定
        firstTensor = tensorDatas[0]
        coeffBlock = firstTensor.getBlock(planeIdx, 0, 0)
        if not coeffBlock:
            return None
        
        # tensor数で埋めた行列を作成
        result = np.full_like(coeffBlock.data, len(tensorDatas))
        
        return DataBlock(result, planeIdx, block.x, block.y)