'''
InverseNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base import NNBlockOperationNode, DataBlock
from utils.interval_helper import createHalfOpenEnd
import numpy as np

class InverseNode(NNBlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "inverse", "逆数")
    
    def getColor(self):
        return self._color_func
    
    def getDisplayLevels(self, inputFlowData):
        """入力データの逆数変換されたdisplay_levelsを返す"""
        inputLevels = inputFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        # 逆数変換: [a, b) → [1/b, 1/a) (ゼロを除く)
        if inputMin > 0 or inputMax < 0:
            # ゼロを含まない場合
            outputMin = 1.0 / inputMax
            outputMax = 1.0 / inputMin
            
            return {
                'min': outputMin,
                'exclusive_upper': createHalfOpenEnd(outputMin, outputMax)
            }
        return None
    
    def processBlock(self, block):
        """単一ブロックの逆数処理"""
        arr = block.data
        
        # ゼロでない要素のみ逆数を計算
        with np.errstate(divide='ignore', invalid='ignore'):
            result = np.where(arr != 0, 1.0 / arr, np.nan)
        
        return DataBlock(block.planeIndex, block.x, block.y, result)