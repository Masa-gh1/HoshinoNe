'''
IDWTNode - 逆離散ウェーブレット変換ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class IDWTNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'idwt'
    # ノード名
    name      = 'IDWT'
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
    
    def createFlowData(self, inputData):
        from base import FlowData
        
        width, height = inputData.getDimensions()
        
        # headers を生成
        headers = inputData.headers.copy()
        
        # 逆 DWT 後のプレーンを設定
        level = headers.pop("DWT level")
        size  = headers.pop("DWT size")
        
        mode   = headers["mode"].rstrip(" (DWT)")
        planes = headers["planes"]
        newPlanes = []
        for plane in planes[0::1+(level*3)]:
            newPlanes.append(plane)
        
        headers.update({"mode"   : mode,
                        "planes" : newPlanes,
                       })
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)
        
        self.level = level
        self.size  = size
        
        print(width, height)
        return flowData

    def processPlane(self, flowData, planeIndex):
        """逆DWT処理"""
        import pywt
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        pln = planeIndex * (1+3*self.level) # 対象プレーン群の開始位置
        sub =              (1+3*self.level) # 対象プレーン群の枚数
        
        planeCount = flowData.getPlaneCount()
        width, height = flowData.getDimensions()
        
        if planeCount // sub <= planeIndex:
            return []
        
        # データを読み込み
        coeffs = []
        w = self.size[0]
        h = self.size[1]
        planeData = nh.empty((h, w))
        for block in flowData.iterateBlocks(pln):
            if block.x < w and block.y < h:
                blockHeight = min(block.getHeight(), h - block.y)
                blockWidth  = min(block.getWidth() , w - block.x)
                endY = block.y + blockHeight
                endX = block.x + blockWidth
                planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        coeffs.append(planeData)
        for l,(w,h) in enumerate(zip(self.size[0::2], self.size[1::2])):
            detail = {}
            for p,key in enumerate(['ad','da','dd']):
                planeData = nh.empty((h, w))
                for block in flowData.iterateBlocks(pln+1+3*l+p):
                    if block.x < w and block.y < h:
                        blockHeight = min(block.getHeight(), h - block.y)
                        blockWidth  = min(block.getWidth() , w - block.x)
                        endY = block.y + blockHeight
                        endX = block.x + blockWidth
                        planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
                detail[key] = planeData
            coeffs.append(detail)
        
        if 1 == len(self._auxiliaryTable):
            # 補正データが 1 プレーンだけなので、全プレーンに同じ補正データを適用する
            auxiliaryTable = self._auxiliaryTable[0]
        else:
            auxiliaryTable = self._auxiliaryTable[planeIndex]
        
        filter_bank = pywt.orthogonal_filter_bank(auxiliaryTable.flatten())
        wavelet = pywt.Wavelet(name="custom", filter_bank=filter_bank)
        data = pywt.waverecn(coeffs, wavelet) # 逆DWT
        
        blocks = []
        h, w = data.shape
        print(w,h)
        for y in range(0, h, BLOCK_SIZE):
            for x in range(0, w, BLOCK_SIZE):
                blockHeight = min(BLOCK_SIZE, h - y)
                blockWidth  = min(BLOCK_SIZE, w - x)
                endY = y + blockHeight
                endX = x + blockWidth
                dataBlock = DataBlock(data[y:endY, x:endX], planeIndex=planeIndex, x=x, y=y)
                blocks.append(dataBlock)
            
        return blocks
