'''
DWTNode - 離散ウェーブレット変換ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class DWTNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'dwt'
    # ノード名
    name      = 'DWT'
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
        h, w = self._auxiliaryTable[0].shape
        
        # headers を生成
        headers = inputData.headers.copy()
        
        # DWT 後のプレーンを設定
        if "DWT level" in headers:
            level = headers["DWT level"] + 1
            sizeL = headers["DWT size"]
            size  = [(sizeL[0] +w-1)//2, (sizeL[1]+w-1)//2]
            size.extend(sizeL)
        else:
            level = 1
            size  = [(width +w-1)//2, (height+w-1)//2]
        
        mode   = headers["mode"].rstrip(" (DWT)")
        planes = headers["planes"]
        newPlanes = []
        for plane in planes[0::1+((level-1)*3)]:
            newPlanes.append(plane)
            for i in range(level, 0, -1):
                newPlanes.append(plane+f" (da{i})")
                newPlanes.append(plane+f" (ad{i})")
                newPlanes.append(plane+f" (dd{i})")
        
        headers.update({"mode"     : mode + " (DWT)",
                        "planes"   : newPlanes,
                        "DWT level": level,
                        "DWT size" : size,
                       })
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)
        
        self.level = level
        self.size  = size
        
        return flowData

    def processPlane(self, flowData, planeIndex):
        """DWT処理"""
        import pywt
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        idx = planeIndex // (1+3*(self.level-1)) # 元画像プレーン
        sub = planeIndex %  (1+3*(self.level-1)) # 分解プレーン
        
        if 0 < sub:
            # 対象プレーンが前レベルの分解画像なのでプレーンを移動させる
            blocks = []
            for block in flowData.iterateBlocks(planeIndex):
                dataBlock = DataBlock(block.data, planeIndex=(idx*(1+3*(self.level))+3+sub), x=block.x, y=block.y)
                blocks.append(dataBlock)
            return blocks
        else:
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
                auxiliaryTable = self._auxiliaryTable[idx]
            
            filter_bank = pywt.orthogonal_filter_bank(auxiliaryTable.flatten())
            wavelet = pywt.Wavelet(name="custom", filter_bank=filter_bank)
            cA, detail = pywt.wavedecn(planeData, wavelet, level=1) # DWT
            result = {'cA':cA}
            result.update(detail)
            
            blocks = []
            for i,(key,res) in enumerate(result.items()):
                h, w = res.shape
                for y in range(0, h, BLOCK_SIZE):
                    for x in range(0, w, BLOCK_SIZE):
                        blockHeight = min(BLOCK_SIZE, h - y)
                        blockWidth  = min(BLOCK_SIZE, w - x)
                        endY = y + blockHeight
                        endX = x + blockWidth
                        dataBlock = DataBlock(res[y:endY, x:endX], planeIndex=idx*(1+3*(self.level))+i, x=x, y=y)
                        blocks.append(dataBlock)
            
            return blocks
