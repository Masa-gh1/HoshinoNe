'''
TensorOperationMixin - tensor 操作の共通機能

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

class TensorOperationMixin:
    """tensor 操作の共通機能を提供するMixin"""
    
    @classmethod
    def computeCombinedTensor(cls, tensorDatas, operation):
        """
        複数 tensor を統合
        
        Args:
            tensorDatas: tensor データのリスト
            operation: 係数演算関数
        """
        import numpy as np
        import utils.numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import FlowData
        from base import DataBlock
        
        if not tensorDatas:
            return None
        if 1 == len(tensorDatas):
            return tensorDatas[0]
        
        # 最初の tensor をベースとしてコピー
        result = FlowData(tensorDatas[0].headers.copy())

        # サイズを決定
        planeCount = max([tensor.getPlaneCount() for tensor in tensorDatas])
        width  = max([tensor.getDimensions()[0] for tensor in tensorDatas])
        height = max([tensor.getDimensions()[1] for tensor in tensorDatas])
        result.setDimensions(width, height)
        
        for planeIndex in range(planeCount):
            if   np.add      == operation:
                resultData = nh.zeros((height, width))
            elif np.multiply == operation:
                resultData = nh.ones((height, width))
            else:
                resultData = nh.zeros((height, width))
            
            for tensor in tensorDatas:
                w, h = tensor.getDimensions()
                for block in tensor.iterateBlocks(planeIndex):
                    x = block.x
                    y = block.y
                    data = block.data
                    if 1 == w and 1 == h:
                        ret = resultData
                    elif 1 == w:
                        ret = resultData[y:y+data.shape[0], :]
                    elif 1 == h:
                        ret = resultData[:, x:x+data.shape[1]]
                    else:
                        ret = resultData[y:y+data.shape[0], x:x+data.shape[1]]
                    operation(ret, block.data, out=ret)
            
            for x in range(0, width, BLOCK_SIZE):
                for y in range(0, height, BLOCK_SIZE):
                    result.setBlock(DataBlock(resultData, planeIndex, x, y))
        
        return result
    
    @classmethod
    def calculateTensorRange(cls, tensor, width, height):
        """tensor の範囲を計算"""
        import numpy as np
        
        if tensor is None:
            return 0.0, 0.0
        
        # tensorの各成分の最小値と最大値を計算
        minVal = np.min(tensor)
        maxVal = np.max(tensor)
        
        # tensorの各成分の最小値と最大値を計算
        return minVal, maxVal
    
    @classmethod
    def calculateTensorBlock(cls, tensorData, planeIndex, x, y, blockShape, defaultValue=0.0):
        """Tensor データからブロック内の各座標に対応する値を計算"""
        import numpy as np
        import utils.numpy_helpers as nh

        planeCount = tensorData.getPlaneCount()
        width, height = tensorData.getDimensions()
        if width <= 0 or height <= 0 or planeCount <= planeIndex:
            if 0.0 == defaultValue:
                return nh.zeros(blockShape)
            elif 1.0 == defaultValue:
                return nh.ones(blockShape)
            else:
                return nh.full(blockShape, defaultValue)
        
        # 指定プレーンの数列を取得
        if 1 == width and 1 == height:
            return tensorData.getBlock(planeIndex, 0, 0).data
        elif 1 == width:
            return tensorData.getBlock(planeIndex, 0, y).data
        elif 1 == height:
            return tensorData.getBlock(planeIndex, x, 0).data
        else:
            return tensorData.getBlock(planeIndex, x, y).data

