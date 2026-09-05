'''
InverseMatrixNode - 逆行列ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class InverseMatrixNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_U_OP
    minorType = 'inverse_matrix'
    # ノード名
    name      = '逆行列'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def createFlowData(self, inputData):
        from base import FlowData
        
        width, height = inputData.getDimensions()
        
        if width != height:
            raise ValueError(f"逆行列の計算ができません: 列数({widthA})と行数({heightB})が一致しません。")
        
        # headers を生成
        headers = inputData.headers.copy()

        # 結果用の FlowData を生成
        flowData = FlowData(headers)
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

        #逆行列を計算
        try:
            result = np.linalg.inv(planeData)
        except np.linalg.LinAlgError:
            result = nh.nans((height,width))
        
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
