'''
QuadraticFitNode - 2次関数近似ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np

from config import BLOCK_SIZE
from base.FlowNode_CONST import *
from base import FlowNode, FlowData, DataBlock
from utils import numpy_helpers as nh

class QuadraticFitNode(FlowNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'quadratic_fit'
    # ノード名
    name      = '2次関数近似'
    # 入出力タイプ
    ioType    = _IO_TYPE_0N
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
    
    def process(self, context=None):
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        flowData = None
        for node in self.inputNodes:
            if node.flowDatas and node.flowDatas[0].headers.get('type') == 'image':
                flowData = node.flowDatas[0]
                break
        
        if not flowData:
            raise ValueError("画像データが見つかりません")
        
        width, height = flowData.getDimensions()
        planeCount = flowData.getPlaneCount()
        
        # planesヘッダーからプレーン情報を取得
        planeNames = flowData.headers.get('planes', ['L']) if flowData.headers else ['L']
        displayLevels = flowData.headers['display_levels']
        actualPlaneCount = len(planeNames)
        
        # データを読み込み
        planeData = [nh.zeros((height, width)) for _ in range(actualPlaneCount)]
                
        self.reportProgress(context, "データ読み込み中")
        
        for y in range(0, height, BLOCK_SIZE):
            for x in range(0, width, BLOCK_SIZE):
                for planeIndex in range(actualPlaneCount):
                    block = flowData.getBlock(planeIndex, x, y)
                    if block:
                        blockHeight = min(block.getHeight(), height - y)
                        blockWidth = min(block.getWidth(), width - x)
                        endY = y + blockHeight
                        endX = x + blockWidth
                        planeData[planeIndex][y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
        
        # 各プレーン毎に2次関数フィッティング
        coefficients = {}
        equations = []
        
        for planeIndex, planeName in enumerate(planeNames):
            self.reportProgress(context, f"{planeName}プレーン計算中", planeIndex + 1, actualPlaneCount)
            
            # 座標データを準備（スレッドセーフ: np.meshgrid を置き換え）
            y_indices = nh.arange(height).reshape(-1, 1)
            x_indices = nh.arange(width)
            y_coords = np.broadcast_to(y_indices, (height, width))
            x_coords = np.broadcast_to(x_indices, (height, width))
            x_flat = x_coords.flatten()
            y_flat = y_coords.flatten()
            z_flat = planeData[planeIndex].flatten()
            
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
            
            coefficients[planeName] = [c0, c1_x, c1_y, c2_x2, c2_xy, c2_y2]
            equations.append(f'{planeName} = {c0:.6f} + {c1_x:.6f}x + {c1_y:.6f}y + {c2_x2:.6f}x² + {c2_xy:.6f}xy + {c2_y2:.6f}y²')
        
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
            'equations': equations
        }
        
        outputFlowData = FlowData(headers)
        outputFlowData.setDimensions(3, 3)
        
        # 各プレーンに係数Polynomialを設定
        for planeIndex, planeName in enumerate(planeNames):
            c0, c1_x, c1_y, c2_x2, c2_xy, c2_y2 = coefficients[planeName]
            result = [
                [c0,   c1_x,  c2_x2],   # y^0: 1, x, x²
                [c1_y, c2_xy, 0],       # y^1: y, xy, 0
                [c2_y2, 0,    0]        # y^2: y², 0, 0
            ]
            dataBlock = DataBlock(result, planeIndex=planeIndex, x=0, y=0)
            outputFlowData.setBlock(dataBlock)

        
        self.flowDatas = [outputFlowData]
        self.reportProgress(context, "完了")
