'''
DedupNode class

@author: Masakazu Inoue
'''

from base import NNBlockOperationNode, DataBlock
import numpy as np

class InverseNode(NNBlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "inverse", "逆数")
    
    def getColor(self):
        return self._color_func
    
    def processBlock(self, block):
        """単一ブロックの逆数処理"""
        arr = block.data
        
        # ゼロでない要素のみ逆数を計算
        with np.errstate(divide='ignore', invalid='ignore'):
            result = np.where(arr != 0, 1.0 / arr, np.nan)
        
        return DataBlock(block.planeIndex, block.x, block.y, result)