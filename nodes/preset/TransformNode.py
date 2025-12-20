'''
TransformNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import numpy as np
import hashlib
from tkinter import messagebox

from config import BLOCK_SIZE
from base.FlowNode_CONST import *
from base import FlowData
from base import LazyFlowData
from base import DataBlock
from nodes import LazyNNOperationNode
from utils import numpy_helpers as nh

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

class TransformNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'transform'
    # ノード名
    name      = '変形'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        self._tableData   = None
        self._extendParams = None

        if not CV2_AVAILABLE:
            messagebox.showerror(f"{self.name} エラー", "OpenCVライブラリがインストールされていません。\npip install opencv-python でインストールしてください。")
            return
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：primary/auxiliaryで分類"""
        primaryDatas = []
        auxiliaryDatas = []
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            if category == 'auxiliary':
                auxiliaryDatas.append(data)
            else:
                primaryDatas.append(data)
        
        # table 形式データを読み込み
        self._tableData = self._loadTableData(auxiliaryDatas)
        # 画像拡張を計算
        self._extendParams = self._calculateExpand(primaryDatas, self._tableData)
        
        return primaryDatas
    
    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        # auxiliaryデータから変換パラメータを取得
        if not self._tableData or not self._extendParams:
            return inputData  # パラメータ未設定時はそのまま
        
        image_id = self._generateImageId(inputData)
        transform_params = self._getTransformParams(image_id, self._tableData)
        
        lazyData = LazyFlowData(inputData)
        
        if transform_params:
            expand_left, expand_top, new_width, new_height = self._extendParams
            dx = transform_params['dx'] + expand_left
            dy = transform_params['dy'] + expand_top
            rotation = transform_params['rotation']
            
            lazyData.addOperation(self.transformAndExpand, dx, dy, rotation, new_width, new_height)
            lazyData.setDimensions(new_width, new_height)
        
        return lazyData
        
    def _loadTableData(self, auxiliaryDatas):
        """table 形式データを読み込み"""
        # 複数の auxiliary データから table 形式を探す
        lines   = []
        columns = None
        tabledatas = []
        for tableFlowData in auxiliaryDatas:
            if tableFlowData.headers.get('type') == 'table':
                lines.extend(tableFlowData.headers.get('lines', []))
                columnCur = tableFlowData.headers.get('columns', [])
                
                # 縦1列のブロックのみを結合
                for block in tableFlowData.iterateBlocks():
                    if not block or block.data is None or 0 != block.x:
                        pass
                    elif not columns:
                        columns = columnCur
                        tabledatas.append(block.data)
                    elif columns == columnCur:
                        tabledatas.append(block.data)
        
        if not tabledatas:
            raise ValueError("変形パラメータが必要です")
        
        tabledata = np.vstack(tabledatas)
        
        return {
            'columns': columns,
            'lines': lines,
            'data': tabledata
        }
    
    def _calculateExpand(self, inputDatas, tableData):
        """拡張領域計算"""
        if not inputDatas or not tableData:
            return None
        
        width, height = inputDatas[0].getDimensions()
        all_corners = []
        
        # table データから各画像の変換パラメータを取得
        for inputData in inputDatas:
            image_id = self._generateImageId(inputData)
            transform_params = self._getTransformParams(image_id, tableData)
            
            if transform_params:
                corners = self._calculateTransformedCorners(width, height,
                    transform_params['dx'], transform_params['dy'], transform_params['rotation'])
                all_corners.extend(corners)
        
        if not all_corners:
            return (0, 0, width, height)
        
        min_x = min(corner[0] for corner in all_corners)
        min_y = min(corner[1] for corner in all_corners)
        max_x = max(corner[0] for corner in all_corners)
        max_y = max(corner[1] for corner in all_corners)
        
        expand_left = int(max(0, -min_x))
        expand_top = int(max(0, -min_y))
        new_width = int(np.ceil(max_x - min_x))
        new_height = int(np.ceil(max_y - min_y))
        
        return (expand_left, expand_top, new_width, new_height)
    
    def _calculateTransformedCorners(self, width, height, dx, dy, rotation):
        """画像の4隅の変換後座標を計算（画像中心回転）"""
        corners = nh.array([[0, 0], [width, 0], [width, height], [0, height]])
        
        if rotation != 0:
            center = (width / 2, height / 2)
            M = cv2.getRotationMatrix2D(center, rotation, 1.0)
            M[0, 2] += dx
            M[1, 2] += dy
            transformed = cv2.transform(corners.reshape(-1, 1, 2), M).reshape(-1, 2)
        else:
            transformed = corners + nh.array([dx, dy])
        
        return transformed
    
    def _generateImageId(self, flowData):
        """画像識別子を生成"""
        source_file = flowData.headers.get('source_file')
        if source_file:
            return source_file
        
        datetime_str = flowData.headers.get('datetime')
        if datetime_str:
            return f"datetime_{datetime_str}"
        
        data_hash = hashlib.md5(str(flowData.headers).encode()).hexdigest()[:8]
        return f"hash_{data_hash}"
    
    def _getTransformParams(self, image_id, tableData):
        """画像識別子から変換パラメータを取得"""
        lines = tableData['lines']
        columns = tableData['columns']
        data = tableData['data']
        
        row_index = lines.index(image_id)
        row_data = data[row_index]
        
        dx_idx = columns.index('dx') if 'dx' in columns else 0
        dy_idx = columns.index('dy') if 'dy' in columns else 1
        rotation_idx = columns.index('rotation') if 'rotation' in columns else 2
        
        return {
            'dx': float(row_data[dx_idx]),
            'dy': float(row_data[dy_idx]),
            'rotation': float(row_data[rotation_idx])
        }
        
    @staticmethod
    def transformAndExpand(flowData, planeIndex, x, y, dx, dy, rotation, new_width, new_height):
        """変形 + 拡張を一度に実行"""
        
        orig_width, orig_height = flowData.getDimensions()
        
        # 出力ブロックの4隅を逆変換して必要な入力範囲を計算
        corners = nh.array([[x, y], [x+BLOCK_SIZE, y], [x+BLOCK_SIZE, y+BLOCK_SIZE], [x, y+BLOCK_SIZE]])
        
        if rotation != 0:
            # 回転ありの場合は逆変換行列で計算
            center = (orig_width / 2, orig_height / 2)
            M_inv = cv2.getRotationMatrix2D(center, -rotation, 1.0)
            M_inv[0, 2] -= dx
            M_inv[1, 2] -= dy
            source_corners = cv2.transform(corners.reshape(-1, 1, 2), M_inv).reshape(-1, 2)
        else:
            # 平行移動のみ
            source_corners = corners - nh.array([dx, dy])
        
        # 必要な入力範囲を計算
        min_x = int(np.floor(np.min(source_corners[:, 0])))
        max_x = int(np.ceil(np.max(source_corners[:, 0])))
        min_y = int(np.floor(np.min(source_corners[:, 1])))
        max_y = int(np.ceil(np.max(source_corners[:, 1])))
        
        # ブロック境界に拡張
        min_block_x = (min_x // BLOCK_SIZE) * BLOCK_SIZE
        max_block_x = (max_x // BLOCK_SIZE) * BLOCK_SIZE + BLOCK_SIZE
        min_block_y = (min_y // BLOCK_SIZE) * BLOCK_SIZE
        max_block_y = (max_y // BLOCK_SIZE) * BLOCK_SIZE + BLOCK_SIZE
        
        min_block_x = max(min_block_x, 0)
        max_block_x = min(max_block_x, orig_width)
        min_block_y = max(min_block_y, 0)
        max_block_y = min(max_block_y, orig_height)

        if max_block_x <= min_block_x or max_block_y <= min_block_y:
            # 移動元が画像外なので NaN を返す
            return DataBlock(nh.nans((BLOCK_SIZE, BLOCK_SIZE)), planeIndex, x, y)
        else:
            # 移動に必要な範囲の部分画像を構築
            region_width  = max(x+BLOCK_SIZE, max_block_x) - min(x, min_block_x)
            region_height = max(y+BLOCK_SIZE, max_block_y) - min(y, min_block_y)
            region_image = nh.nans((region_height, region_width))
            
            # 必要なブロックを取得して部分画像に配置
            isAnyNaN = False # 必要なブロックに NaN が含まれているか
            for by in range(min_block_y, max_block_y, BLOCK_SIZE):
                for bx in range(min_block_x, max_block_x, BLOCK_SIZE):
                    block = flowData.getBlock(planeIndex, bx, by)
                    if block and block.data is not None:
                        if len(block.data.shape) == 3:
                            block_data = block.data[:, :, 0]
                        else:
                            block_data = block.data
                        
                        # 部分画像内の位置に配置
                        rel_x = bx - min_block_x
                        rel_y = by - min_block_y
                        h, w = block_data.shape
                        region_image[rel_y:rel_y+h, rel_x:rel_x+w] = block_data

                        if np.isnan(block_data).any():
                            # 必要なブロックに NaN が含まれていた
                            isAnyNaN = True
            
            # 変換行列を作成（部分画像座標系）
            if rotation != 0:
                # 元画像の中心を部分画像座標系に変換
                orig_center_x = orig_width  / 2 - min_block_x
                orig_center_y = orig_height / 2 - min_block_y
                M = cv2.getRotationMatrix2D((orig_center_x, orig_center_y), rotation, 1.0)
                M[0, 2] += dx
                M[1, 2] += dy
            else:
                M = nh.BDTYPE([[1, 0, dx], [0, 1, dy]])
            
            # 変換後に必要なサイズを計算
            transform_output_width = min(region_width, new_width - (x - min_block_x))
            transform_output_height = min(region_height, new_height - (y - min_block_y))
            
            # 部分画像を変形
            if not isAnyNaN:
                transformed_region = cv2.warpAffine(region_image, M, (transform_output_width, transform_output_height),
                                                    flags=cv2.INTER_LINEAR,
                                                    borderMode=cv2.BORDER_CONSTANT,
                                                    borderValue=np.nan)
            else:
                # NaN対応の補間変形
                validMask = ~np.isnan(region_image)              # 有効データマスクを作成
                imageData = np.where(validMask, region_image, 0) # 無効データを 0 にした画像
                imageMask = np.where(validMask, nh.nan, 0)       # 有効データを NaN に、無効データを 0 にした画像
                transformed_data = cv2.warpAffine(imageData, M, (transform_output_width, transform_output_height),  # データを変形
                                                flags=cv2.INTER_LINEAR,
                                                borderMode=cv2.BORDER_CONSTANT,
                                                borderValue=0)
                transformed_mask = cv2.warpAffine(imageMask, M, (transform_output_width, transform_output_height),  # 重みを変形
                                                flags=cv2.INTER_LINEAR,
                                                borderMode=cv2.BORDER_CONSTANT,
                                                borderValue=0)
                # 有効データを NaN に、無効データを 0 にしたマスク画像を用いているから
                # NaN = NaN * 0 なので NaN のある場所が有効なデータとなる
                transformed_region =  np.where( np.isnan(transformed_mask), transformed_data, nh.nan)
            
            # 出力ブロック位置を部分画像座標系に変換
            output_x_in_region = x - min_block_x
            output_y_in_region = y - min_block_y
            
            # 画面端での適切なブロックサイズを計算
            actual_block_width = min(BLOCK_SIZE, new_width - x)
            actual_block_height = min(BLOCK_SIZE, new_height - y)
            
            # 出力ブロック部分を切り出し
            end_y = min(output_y_in_region + actual_block_height, transformed_region.shape[0])
            end_x = min(output_x_in_region + actual_block_width, transformed_region.shape[1])
            
            result = transformed_region[output_y_in_region:end_y, output_x_in_region:end_x]
            
            # サイズが足りない場合はNaNでパディング
            if result.shape != (actual_block_height, actual_block_width):
                padded_block = nh.nans((actual_block_height, actual_block_width))
                h, w = result.shape
                padded_block[:h, :w] = result
                result = padded_block
            
            return DataBlock(result, planeIndex, x, y)
