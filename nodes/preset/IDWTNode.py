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
    
    def createFlowData(self, inputDatas):
        from base import FlowData
        
        width, height = inputDatas[0].getDimensions()
        
        # headers を生成
        headers = inputDatas[0].headers.copy()
        
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
        
        return flowData

    def planeOperation(self, flowDatas, planeIndex):
        """逆DWT処理"""
        import re
        import pywt
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        flowData = flowDatas[0]
        auxData  = flowDatas[1]

        planes = flowData.headers["planes"]
        level = flowData.headers["DWT level"]
        size  = flowData.headers["DWT size"]
        
        inum =              (1+3*level) # 入力DWTプレーン群の枚数
        iIdx = planeIndex * (1+3*level) # 入力DWTプレーン群の開始位置
        
        # データを読み込み
        coeffs = []
        w = size[0]
        h = size[1]
        planeData = nh.empty((h, w))
        for block in flowData.iterateBlocks(iIdx):
            if block.x < w and block.y < h:
                blockHeight = min(block.getHeight(), h - block.y)
                blockWidth  = min(block.getWidth() , w - block.x)
                endY = block.y + blockHeight
                endX = block.x + blockWidth
                planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        coeffs.append(planeData)
        
        detail = [{} for _ in range(level)]
        for i in range(inum-1):
            idx = iIdx+1+i
            # プレーン名 "r (ad1)" から ad, 1 を切り出す
            r = re.findall(r".+ \(([ad]+)([0-9]+)\)", planes[idx])
            key = r[0][0]
            l = int(r[0][1])
            w = size[2*(level-l)]
            h = size[2*(level-l)+1]
            planeData = nh.empty((h, w))
            for block in flowData.iterateBlocks(idx):
                if block.x < w and block.y < h:
                    blockHeight = min(block.getHeight(), h - block.y)
                    blockWidth  = min(block.getWidth() , w - block.x)
                    endY = block.y + blockHeight
                    endX = block.x + blockWidth
                    planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
            detail[level-l][key] = planeData
        coeffs.extend(detail)
        
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
        data = pywt.waverecn(coeffs, wavelet) # 逆DWT
        
        blocks = []
        h, w = data.shape
        for y in range(0, h, BLOCK_SIZE):
            for x in range(0, w, BLOCK_SIZE):
                blockHeight = min(BLOCK_SIZE, h - y)
                blockWidth  = min(BLOCK_SIZE, w - x)
                endY = y + blockHeight
                endX = x + blockWidth
                dataBlock = DataBlock(data[y:endY, x:endX], planeIndex=planeIndex, x=x, y=y)
                blocks.append(dataBlock)
            
        return blocks
