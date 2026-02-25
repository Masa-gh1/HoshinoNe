'''
IFFTNode - 逆FFTノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class FFTNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'ifft'
    # ノード名
    name      = '逆FFT'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def processPlane(self, flowData, planeIndex):
        """相関処理"""
        import scipy
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock

        width, height = flowData.getDimensions()
        
        # データを読み込み
        planeData = np.empty((height, width), dtype=nh.BDCOMPLEX)
        
        for block in flowData.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), height - block.y)
            blockWidth  = min(block.getWidth() , width  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        
        # NaN を補完
        np.nan_to_num(planeData, nan=0, copy=False)
        
        result = scipy.fft.ifftn(planeData).real # 逆FFT
        
        blocks = []
        for y in range(0, height, BLOCK_SIZE):
            for x in range(0, width, BLOCK_SIZE):
                blockHeight = min(BLOCK_SIZE, height - y)
                blockWidth  = min(BLOCK_SIZE, width  - x)
                endY = y + blockHeight
                endX = x + blockWidth
                dataBlock = DataBlock(result[y:endY, x:endX], planeIndex=planeIndex, x=x, y=y)
                blocks.append(dataBlock)
        
        return blocks
