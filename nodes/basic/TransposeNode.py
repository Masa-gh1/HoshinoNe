'''
TransposeNode - 転置ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class TransposeNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'transpose'
    # ノード名
    name      = '転置'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def createFlowData(self, inputData):
        from base import FlowData
        
        width, height = inputData.getDimensions()
        width, height = height, width
        
        flowData = super().createFlowData(inputData)
        flowData.setDimensions(width, height)
        
        return flowData
    
    def planeOperation(self, flowData, planeIndex):
        """行列積処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock

        width, height = flowData.getDimensions()
        
        # データを読み込み
        planeData = nh.empty((height, width))
        
        for block in flowData.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), height - block.y)
            blockWidth  = min(block.getWidth() , width  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]

        # 転置を計算
        result = planeData.T
        width, height = height, width
        
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
