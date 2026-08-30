'''
MatrixProductNode - 行列積ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class MatrixProductNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_B_OP
    minorType = 'matrix_product'
    # ノード名
    name      = '行列積'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def createFlowData(self, inputDatas):
        from base import FlowData
        
        inputDataA = inputDatas[0]
        inputDataB = inputDatas[1]

        widthA, heightA = inputDataA.getDimensions()
        widthB, heightB = inputDataB.getDimensions()
        
        if widthA != heightB:
            raise ValueError(f"行列積の計算ができません: Aの列数({widthA})とBの行数({heightB})が一致しません。")
        
        # headers を生成
        headers = inputDataA.headers.copy()

        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(widthB, heightA)
        
        return flowData

    def planeOperation(self, flowDatas, planeIndex):
        """行列積処理"""
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock

        inputDataA = flowDatas[0]
        inputDataB = flowDatas[1]
        widthA, heightA = inputDataA.getDimensions()
        widthB, heightB = inputDataB.getDimensions()
        
        # データを読み込み
        planeDataA = nh.empty((heightA, widthB))
        
        for block in inputDataA.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), heightA - block.y)
            blockWidth  = min(block.getWidth() , widthB  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeDataA[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        
        planeDataB = nh.empty((heightB, widthB))
        
        for block in inputDataB.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), heightB - block.y)
            blockWidth  = min(block.getWidth() , widthB  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeDataB[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        
        result = planeDataA @ planeDataB
        
        blocks = []
        for y in range(0, heightA, BLOCK_SIZE):
            for x in range(0, widthB, BLOCK_SIZE):
                blockHeight = min(BLOCK_SIZE, heightA - y)
                blockWidth  = min(BLOCK_SIZE, widthB  - x)
                endY = y + blockHeight
                endX = x + blockWidth
                dataBlock = DataBlock(result[y:endY, x:endX], planeIndex=planeIndex, x=x, y=y)
                blocks.append(dataBlock)
        
        return blocks
