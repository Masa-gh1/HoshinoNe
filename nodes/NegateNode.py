'''
NegateNode class

@author: Masakazu Inoue
'''

from base import NNBlockOperationNode, DataBlock
import numpy as np

class NegateNode(NNBlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "negate", "符号反転")
    
    def getColor(self):
        return self._color_func
    
    def processBlock(self, block):
        """単一ブロックの符号反転処理"""
        # 符号反転
        result = -block.data
        
        return DataBlock(block.planeIndex, block.x, block.y, result)