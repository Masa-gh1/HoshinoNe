'''
QuadraticFitNode - 2次関数近似ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode

class QuadraticFitNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'quadratic_fit'
    # ノード名
    name      = '2次関数近似'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    outputCat = _OUT_CAT_AUX
    
    def createFlowData(self, inputData):
        """FlowData を作成"""
        from base import FlowData

        # header を取得
        planeNames    = inputData.headers['planes']
        displayLevels = inputData.headers['display_levels']
        
        # Polynomial形式でデータを構築 (3x3の係数Polynomial)
        headers = {
            'category': 'auxiliary',
            'type': 'polynomial',
            'mode': '2D',
            'axes': ['x_order', 'y_order'],
            'columns': ['x^0', 'x^1', 'x^2'],
            'lines': ['y^0', 'y^1', 'y^2'],
            'planes': planeNames,
            'display_levels': displayLevels,
            'max_orders': [2, 2],
        }
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(3, 3)

        return flowData

    def planeOperation(self, flowData, planeIndex):
        """2次関数近似処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from base import FlowData
        from base import DataBlock

        width, height = flowData.getDimensions()
        
        # 座標データを準備（スレッドセーフ: np.meshgrid を置き換え）
        y_indices = nh.arange(height).reshape(-1, 1)
        x_indices = nh.arange(width)
        y_coords = np.broadcast_to(y_indices, (height, width))
        x_coords = np.broadcast_to(x_indices, (height, width))
        x_flat = x_coords.flatten()
        y_flat = y_coords.flatten()
        
        # データを読み込み
        planeData = nh.nans((height, width))
        
        for block in flowData.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), height - block.y)
            blockWidth  = min(block.getWidth() , width  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        
        z_flat = planeData.flatten()
        
        # NaN値を除外して有効なピクセルのみ使用
        valid_mask = ~np.isnan(z_flat)
        if not np.any(valid_mask):
            # 全てNaNの場合はゼロ係数
            coeffs = nh.zeros(6)
        else:
            x_valid = x_flat[valid_mask]
            y_valid = y_flat[valid_mask]
            z_valid = z_flat[valid_mask]
            
            # 2次関数の係数行列を構築 (次数の少ない順)
            A = np.column_stack([
                nh.ones(len(x_valid)),  # 0次: 1
                x_valid,                # 1次: x
                y_valid,                # 1次: y
                x_valid**2,             # 2次: x²
                x_valid*y_valid,        # 2次: xy
                y_valid**2              # 2次: y²
            ])
            
            # 最小二乗法で係数を求める
            coeffs, _, _, _ = np.linalg.lstsq(A, z_valid, rcond=None)
        c0, c1_x, c1_y, c2_x2, c2_xy, c2_y2 = coeffs
        
        # dataBlock を作成
        result = [
            [c0,   c1_x,  c2_x2],   # y^0: 1, x, x²
            [c1_y, c2_xy, 0],       # y^1: y, xy, 0
            [c2_y2, 0,    0]        # y^2: y², 0, 0
        ]
        dataBlock = DataBlock(result, planeIndex=planeIndex, x=0, y=0)

        planeName = flowData.headers['planes'][planeIndex]
        equations = f'{planeName} = {c0:.6f} + {c1_x:.6f}x + {c1_y:.6f}y + {c2_x2:.6f}x² + {c2_xy:.6f}xy + {c2_y2:.6f}y²'

        return [dataBlock]
