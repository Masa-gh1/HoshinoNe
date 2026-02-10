'''
CorrelationNode - 相関ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class CorrelationNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'correlation'
    # ノード名
    name      = '相関'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理"""
        from utils import numpy_helpers as nh

        primaryDatas = []
        auxiliaryTables = []

        for data in inputDatas:
            dataType = data.headers.get('type', 'table')
            category = data.headers.get('category', 'primary')
            if category == 'auxiliary':
                dataType = data.headers.get('type', 'table')
                if dataType in ('image','table'):
                    auxiliaryTables.append(data)
            else:
                if dataType in ('image','table'):
                    primaryDatas.append(data)
    
        # auxiliary tableを事前統合（最初のものをベースに加算）
        self._auxiliaryTable = None
        if auxiliaryTables:
            width, height = auxiliaryTables[0].getDimensions()
            planeCount = auxiliaryTables[0].getPlaneCount()
            planeData = [nh.empty((height, width)) for _ in range(planeCount)]
            
            for block in auxiliaryTables[0].iterateBlocks():
                x = block.x
                y = block.y
                planeIndex = block.planeIndex
                blockWidth  = min(block.getWidth() , width  - x)
                blockHeight = min(block.getHeight(), height - y)
                endX = block.x + blockWidth
                endY = block.y + blockHeight
                planeData[planeIndex][y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
            self._auxiliaryTable = planeData
        
        return primaryDatas
    
    def processPlane(self, flowData, planeIndex):
        """相関処理"""
        import scipy
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import FlowData
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
        
        if 1 == len(self._auxiliaryTable):
            # 補正データが 1 プレーンだけなので、全プレーンに同じ補正データを適用する
            auxiliaryTable = self._auxiliaryTable[0]
        else:
            auxiliaryTable = self._auxiliaryTable[planeIndex]

        result = scipy.signal.convolve(planeData, auxiliaryTable, mode='same')

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
