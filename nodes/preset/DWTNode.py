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
    
    def createFlowData(self, inputDatas):
        from base import FlowData
        
        inputData = inputDatas[0]
        auxData   = inputDatas[1]

        width, height = inputData.getDimensions()
        w, h  = auxData.getDimensions()
        
        # headers を生成
        headers = inputData.headers.copy()
        
        # DWT 後のプレーンを設定
        if "DWT level" in headers:
            level = headers["DWT level"] + 1
            sizeL = headers["DWT size"]
            size  = [(sizeL[0]+w-1)//2, (sizeL[1]+w-1)//2]
            size.extend(sizeL)
        else:
            level = 1
            size  = [(width+w-1)//2, (height+w-1)//2]
        
        mode   = headers["mode"].rstrip(" (DWT)")
        planes = headers["planes"]
        newPlanes = []
        for plane in planes[0::1+((level-1)*3)]:
            newPlanes.append(plane)
            for i in range(level, 0, -1):
                newPlanes.append(plane+f" (ad{i})")
                newPlanes.append(plane+f" (da{i})")
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

    def planeOperation(self, flowDatas, planeIndex):
        """DWT処理"""
        import pywt
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        flowData = flowDatas[0]
        auxData  = flowDatas[1]
        
        idx  = planeIndex // (1+3*(self.level  )) # 処理対象元プレーンidx
        oIdx = idx        *  (1+3*(self.level  )) # 出力DWTプレーン群の先頭
        oSub = planeIndex %  (1+3*(self.level  )) # 出力DWTプレーン相対位置
        iIdx = idx        *  (1+3*(self.level-1)) # 入力DWTプレーン群の先頭
        iSub = oSub-3                             # 入力DWTプレーン相対位置
        
        if 4 <= oSub:
            # 対象プレーンが前レベルの高周波プレーンなので移動させる
            blocks = []
            for block in flowData.iterateBlocks(iIdx+iSub):
                dataBlock = DataBlock(block.data, planeIndex=planeIndex, x=block.x, y=block.y)
                blocks.append(dataBlock)
            return blocks
        elif 1 <= oSub:
            # 今レベルの高周波プレーンなので何もかえさない
            # 今高周波プレーンは前低周波プレーンを分解して得られる
            return []
        else:
            # DWTを実行
            width, height = flowData.getDimensions()
            
            # データを読み込み
            planeData = nh.empty((height, width))
            
            for block in flowData.iterateBlocks(iIdx):
                blockHeight = min(block.getHeight(), height - block.y)
                blockWidth  = min(block.getWidth() , width  - block.x)
                endY = block.y + blockHeight
                endX = block.x + blockWidth
                planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
            
            # 補正データを読み込み
            auxW, auxH = auxData.getDimensions()
            auxPlanCnt = auxData.getPlaneCount()
            
            auxPlane = nh.empty((auxH, auxW))
            
            for block in (auxData.iterateBlocks(0) if 1 == auxPlanCnt else auxData.iterateBlocks(planeIndex)):
                # 補正データが 1 プレーンだけの場合、全プレーンに同じ補正データを適用する
                x = block.x
                y = block.y
                blockWidth  = min(block.getWidth() , auxW - x)
                blockHeight = min(block.getHeight(), auxH - y)
                endX = block.x + blockWidth
                endY = block.y + blockHeight
                auxPlane[y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
            
            filter_bank = pywt.orthogonal_filter_bank(auxPlane.ravel())
            wavelet = pywt.Wavelet(name="custom", filter_bank=filter_bank)
            cA, detail = pywt.wavedecn(planeData, wavelet, level=1) # DWT
            result = {'cA':cA}
            result.update(detail)
            
            blocks = []
            for key,res in result.items():
                i = ["cA", "ad", "da", "dd"].index(key)
                h, w = res.shape
                for y in range(0, h, BLOCK_SIZE):
                    for x in range(0, w, BLOCK_SIZE):
                        blockHeight = min(BLOCK_SIZE, h - y)
                        blockWidth  = min(BLOCK_SIZE, w - x)
                        endY = y + blockHeight
                        endX = x + blockWidth
                        dataBlock = DataBlock(res[y:endY, x:endX], planeIndex=oIdx+i, x=x, y=y)
                        blocks.append(dataBlock)
            
            return blocks
