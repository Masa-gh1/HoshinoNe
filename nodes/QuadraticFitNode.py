'''
QuadraticFitNode class

@author: Masakazu Inoue
'''

import hashlib
import numpy as np
from base import FlowNode, FlowData, DataBlock
from config import BLOCK_SIZE

class QuadraticFitNode(FlowNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "quadratic_fit", "2次関数近似")
    
    def getColor(self):
        return self._color_func
    
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
        actualPlaneCount = len(planeNames)
        
        # データを読み込み
        planeData = [np.zeros((height, width), dtype=np.float64) for _ in range(actualPlaneCount)]
                
        self.reportProgress(context, "データ読み込み中")
        
        for blockY in range(0, height, BLOCK_SIZE):
            for blockX in range(0, width, BLOCK_SIZE):
                for planeIdx in range(actualPlaneCount):
                    block = flowData.getBlock(planeIdx, blockX, blockY)
                    if block:
                        endY = min(blockY + block.getHeight(), height)
                        endX = min(blockX + block.getWidth(), width)
                        planeData[planeIdx][blockY:endY, blockX:endX] = block.data[:endY-blockY, :endX-blockX]
        
        # 各プレーン毎に2次関数フィッティング
        coefficients = {}
        equations = []
        
        for planeIdx, planeName in enumerate(planeNames):
            self.reportProgress(context, f"{planeName}プレーン計算中", planeIdx + 1, actualPlaneCount)
            
            # 座標データを準備
            y_coords, x_coords = np.meshgrid(range(height), range(width), indexing='ij')
            x_flat = x_coords.flatten()
            y_flat = y_coords.flatten()
            z_flat = planeData[planeIdx].flatten()
            
            # 2次関数の係数行列を構築 (次数の少ない順)
            A = np.column_stack([
                np.ones(len(x_flat)),  # 0次: 1
                x_flat,                # 1次: x
                y_flat,                # 1次: y
                x_flat**2,             # 2次: x²
                x_flat*y_flat,         # 2次: xy
                y_flat**2              # 2次: y²
            ])
            
            # 最小二乗法で係数を求める
            coeffs, _, _, _ = np.linalg.lstsq(A, z_flat, rcond=None)
            c0, c1_x, c1_y, c2_x2, c2_xy, c2_y2 = coeffs
            
            coefficients[planeName] = [c0, c1_x, c1_y, c2_x2, c2_xy, c2_y2]
            equations.append(f'{planeName} = {c0:.6f} + {c1_x:.6f}x + {c1_y:.6f}y + {c2_x2:.6f}x² + {c2_xy:.6f}xy + {c2_y2:.6f}y²')
        
        # テンソル形式でデータを構築 (3x3の係数テンソル)
        headers = {
            'type': 'tensor',
            'mode': '2D',
            'axes': ['x_order', 'y_order'],
            'columns': ['x^0', 'x^1', 'x^2'],
            'lines': ['y^0', 'y^1', 'y^2'],
            'planes': planeNames,
            'max_orders': [2, 2],
            'equations': equations
        }
        
        outputFlowData = FlowData(headers)
        outputFlowData.setDimensions(3, 3)
        
        # 各プレーンに係数テンソルを設定
        for planeIdx, planeName in enumerate(planeNames):
            c0, c1_x, c1_y, c2_x2, c2_xy, c2_y2 = coefficients[planeName]
            tensorData = [
                [c0,   c1_x,  c2_x2],   # y^0: 1, x, x²
                [c1_y, c2_xy, 0],       # y^1: y, xy, 0
                [c2_y2, 0,    0]        # y^2: y², 0, 0
            ]
            dataBlock = DataBlock(planeIdx, 0, 0, tensorData)
            outputFlowData.setBlock(dataBlock)

        
        self.flowDatas = [outputFlowData]
        self.reportProgress(context, "完了")
