'''
NegateNode class

@author: Masakazu Inoue
'''

from base import NNBlockOperationNode, DataBlock
from utils.interval_helper import createHalfOpenEnd
import numpy as np

class NegateNode(NNBlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "negate", "符号反転")
    
    def getColor(self):
        return self._color_func
    
    def getDisplayLevels(self, inputFlowData):
        """入力データの符号反転されたdisplay_levelsを返す"""
        inputLevels = inputFlowData.headers['display_levels']
        inputMin = inputLevels['min']
        inputMax = inputLevels['exclusive_upper']
        
        # 符号反転: [a, b) → (-b, -a] → [-b, -a+ε)
        outputMin = -inputMax
        outputMax = -inputMin
        
        return {
            'min': outputMin,
            'exclusive_upper': createHalfOpenEnd(outputMin, outputMax)
        }
    
    def processBlock(self, block):
        """単一ブロックの符号反転処理"""
        # 符号反転
        result = -block.data
        
        return DataBlock(block.planeIndex, block.x, block.y, result)