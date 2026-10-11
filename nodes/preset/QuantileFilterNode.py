'''
QuantileFilterNode - 分位数濾過

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode
from config import MAX_WORKERS

class QuantileFilterNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_NEIBR
    minorType = 'quantile_filter'
    # ノード名
    name      = '分位数濾過'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def planeOperation(self, flowDatas, planeIndex):
        """分位数濾過処理"""
        import numpy as np
        from config import BLOCK_SIZE
        from base import DataBlock
        from utils import numpy_helpers as nh
        
        flowData = flowDatas[0]
        auxData  = flowDatas[1]
        
        width, height = flowData.getDimensions()
        
        # データを読み込み
        planeData = nh.empty((height, width))
        
        for block in flowData.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), height - block.y)
            blockWidth  = min(block.getWidth() , width  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        
        # 補正データを読み込み
        auxW, auxH = auxData.getDimensions()
        auxPlanCnt = auxData.getPlaneCount()
        
        auxPlane = nh.empty((auxH, auxW))
        
        auxPlaneIdx = 0 if 1 == auxPlanCnt else planeIndex # 補正データが 1 プレーンだけの場合、全プレーンに同じ補正データを適用する
        auxName = auxData.headers["planes"][auxPlaneIdx]
        auxName = auxName.lower().split(" ")
        q = float(auxName[1]) if "quantile" == auxName[0] else 0.5
        approx = True if "quantile" == auxName[0] and ("approximation" in auxName or "approx" in auxName) else False
        for block in auxData.iterateBlocks(auxPlaneIdx):
            x = block.x
            y = block.y
            blockWidth  = min(block.getWidth() , auxW - x)
            blockHeight = min(block.getHeight(), auxH - y)
            endX = block.x + blockWidth
            endY = block.y + blockHeight
            auxPlane[y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
        
        if np.uint8 == planeData.dtype:
            import cv2
            result = cv2.medianBlur(planeData, auxPlane.shape[0]) # 分位数濾過
        elif 0.5 == q and approx:
            import cv2
            # uint8 にスケールして概算
            offset = np.min(planeData)
            endV   = np.max(planeData) + nh.epsilon
            scale  = (256.0 / (endV - offset))
            shift  = max(1, int(0.1/scale))
            cnt    = 16
            tmp        = nh.empty((height, width))
            planeUByte = np.empty((height, width), dtype=np.uint8)
            resUByte   = np.empty((height, width), dtype=np.uint8)
            result     = nh.zeros((height, width))
            for a in range(0, cnt*shift, shift): # 少しづつズラして中央値を得て誤差を分散させる
                np.add(planeData, -(offset + a), out=tmp)
                tmp *= scale
                planeUByte[:] = tmp # キャスト
                cv2.medianBlur(planeUByte, auxPlane.shape[0], dst=resUByte) # 分位数濾過
                tmp[:] = resUByte # キャスト
                tmp /= cnt * scale
                tmp += (offset + a) / cnt
                result += tmp
        elif False:
            # cv2.medianBlur を使って float32 を計算する。
            import cv2
            planeUlong = planeData.view(np.uint32).reshape((height, width))
            mask        = (0 == planeUlong & 0x80000000)
            planeUlong[ mask] ^= 0x80000000 # 符号ビットを反転
            planeUlong[~mask] ^= 0xFFFFFFFF # 符号ビットを反転
            planeUbyte = (planeUlong >> 24).astype(np.uint8)
            resultUbyte = cv2.medianBlur(planeUbyte, auxPlane.shape[0]) # 分位数濾過
            resultUlong = resultUbyte.astype(np.uint32) << 24
            mask         = (0 == resultUlong & 0x80000000)
            resultUlong[ mask] ^= 0xFFFFFFFF # 符号ビットを反転
            resultUlong[~mask] ^= 0x80000000 # 符号ビットを反転
            result = resultUlong.view(np.float32).reshape((height, width))
        else:
            kh, kw = auxPlane.shape
            result = nh.nans((height, width))
            size = int(np.floor(np.sqrt(8*1024*1204 // MAX_WORKERS // (planeData.itemsize * kh * kw))))
            if 0 == size: size = 1
            tmpA = nh.empty((size+(kh-1), size+(kw-1)))
            tmpB = nh.empty((size,size,kh*kw))
            
            for y in range(0, height, size):
                for x in range(0, width, size):
                    h = min(size, height - y)
                    w = min(size, width  - x)
                    ay, ah = y-(kh-1)//2, h+(kh-1)
                    ax, aw = x-(kw-1)//2, w+(kw-1)
                    by = max(ay, 0)
                    bx = max(ax, 0)
                    bh = min(ah-(by-ay), height - by)
                    bw = min(aw-(bx-ax), width  - bx)
                    if ay == by and ax == bx and ah == bh and aw == bw:
                        tmpA[:] = planeData[by:by+bh, bx:bx+bw]
                    else:
                        tmpA[:] = nh.nan
                        tmpA[by-ay:by-ay+bh, bx-ax:bx-ax+bw] = planeData[by:by+bh, bx:bx+bw]
                    window = np.lib.stride_tricks.sliding_window_view(tmpA, window_shape=(kh, kw), axis=(0,1))
                    window = window.reshape(*window.shape[:-2], kh * kw)
                    tmpB[:h,:w, :] = window[:h,:w, :]
                    window = tmpB[:h,:w, :]
                    if np.any(np.isnan(tmpA)):
                        mask = np.isnan(tmpA)
                        mask = np.lib.stride_tricks.sliding_window_view(mask, window_shape=(kh, kw), axis=(0,1))
                        mask = mask.reshape(*mask.shape[:-2], kh * kw)
                        mask = mask[:h,:w, :]
                        validCnt = (kh * kw) - np.sum(mask, axis=-1)
                        idx = np.maximum(0, (validCnt - 1) // 2)
                        window[mask] = nh.inf
                        window.sort(axis=-1)
                        qua = np.take_along_axis(window, idx[..., np.newaxis], axis=-1).squeeze(-1) # 分位数濾過
                        qua[validCnt == 0] = np.nan
                    else:
                        idx = int(0.5 * (kh * kw - 1))
                        window.partition(idx, axis=-1) # ソートの代わりに idx 位置でパーティション
                        qua = window[..., idx] # 分位数濾過
                    result[y:y+h, x:x+w] = qua[:h, :w]
        
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
