'''
ConvolveNode - 畳み込みノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class DeconvolutionNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'deconvolution'
    # ノード名
    name      = '逆畳み込み'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def planeOperation(self, flowDatas, planeIndex):
        """相関処理"""
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
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
        
        for block in (auxData.iterateBlocks(0) if 1 == auxPlanCnt else auxData.iterateBlocks(planeIndex)):
            # 補正データが 1 プレーンだけの場合、全プレーンに同じ補正データを適用する
            x = block.x
            y = block.y
            blockWidth  = min(block.getWidth() , auxW - x)
            blockHeight = min(block.getHeight(), auxH - y)
            endX = block.x + blockWidth
            endY = block.y + blockHeight
            auxPlane[y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
        
        result = deconvolve(planeData, auxPlane) # 逆畳み込み
        
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

def deconvolve(data, psf, noise_power=0.01):
    """
    wiener を用いて逆畳み込みを行う
    data: 2次元計測データ配列
    psf:  ボケのカーネル (例: 3x3や5x5)
    noise_power: 正則化パラメータ (SNRの逆数に相当)
    """
    import numpy as np
    from scipy import fft

    # パディングサイズを計算
    opt_size = [fft.next_fast_len(s + p - 1) for s, p in zip(data.shape, psf.shape)]
    
    # PSFの「中心」を「左上(0,0)」移動
    psf_padded = np.zeros(opt_size)
    center0 = np.array(psf.shape) // 2
    ul = np.array(psf_padded.shape) // 2 - center0
    dr = ul + psf.shape
    psf_padded[ul[0]:dr[0], ul[1]:dr[1]] = psf
    psf_padded = fft.ifftshift(psf_padded, axes=(0, 1))
    
    # FFT
    data_fft = fft.fftn(data, s=opt_size)
    psf_fft  = fft.fftn(psf_padded)
    
    # ウィーナーフィルタ
    # 1/H (|H|^2)/(|H|^2+k) , |H|^2 = H H*
    # 1/H  (H H*)/(|H|^2+k)
    #         H* /(|H|^2+k)
    wiener_filter = np.conjugate(psf_fft) / (np.abs(psf_fft)**2 + noise_power)
    filtered = data_fft * wiener_filter

    # 逆FFT
    result = fft.ifftn(filtered)
    
    # 元のサイズを切り出し
    result = result[:data.shape[0], :data.shape[1]]
    np.abs(result, out=result)
    return result
