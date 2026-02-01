'''
TransformNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import hashlib

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode

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
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            from tkinter import messagebox
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
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
        transformParams = self._getTransformParams(image_id, self._tableData)
        
        if not transformParams:
            result = inputData
        else:
            expand_left, expand_top, new_width, new_height = self._extendParams
            dx, dy, rotation, scale = transformParams
            dx += expand_left
            dy += expand_top
            result = TransformLazyFlowData(inputData, dx, dy, rotation, scale, new_width, new_height)
        return result
        
    def _loadTableData(self, auxiliaryDatas):
        """table 形式データを読み込み"""
        import numpy as np

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
        import numpy as np

        if not inputDatas or not tableData:
            return None
        
        width, height = inputDatas[0].getDimensions()
        all_corners = []
        
        # table データから各画像の変換パラメータを取得
        for inputData in inputDatas:
            image_id = self._generateImageId(inputData)
            transformParams = self._getTransformParams(image_id, tableData)
            
            if transformParams:
                dx, dy, rotation, scale = transformParams
                corners  = self._calculateTransformedCorners(width, height, dx, dy, rotation, scale)
                all_corners.extend(corners)
        
        if not all_corners:
            return (0, 0, width, height)
        
        min_x = min(corner[0] for corner in all_corners)
        min_y = min(corner[1] for corner in all_corners)
        max_x = max(corner[0] for corner in all_corners)
        max_y = max(corner[1] for corner in all_corners)
        
        expand_left = int(-min_x)
        expand_top  = int(-min_y)
        new_width   = int(np.ceil(max_x - min_x))
        new_height  = int(np.ceil(max_y - min_y))
        
        return (expand_left, expand_top, new_width, new_height)
    
    def _calculateTransformedCorners(self, width, height, dx, dy, rotation, scale):
        """画像の4隅の変換後座標を計算（画像中心回転）"""
        import cv2
        from utils import numpy_helpers as nh

        corners = nh.array([[0, 0], [width, 0], [width, height], [0, height]])
        
        if rotation != 0 or scale != 1.0:
            M = TransformLazyFlowData.createAffine( width, height, 0, 0, dx, dy, rotation, scale)
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
    
    def _getTransformParams(self, image_id, tableData)  :
        """画像識別子から変換パラメータを取得"""
        lines = tableData['lines']
        columns = tableData['columns']
        data = tableData['data']
        
        if 1 == len(lines):
            row_data  = data[0]
        elif image_id in lines:
            row_data  = data[lines.index(image_id)]
        elif "" in lines:
            row_data  = data[lines.index("")]
        else:
            return None
        
        dx       = row_data[columns.index('dx'      )] if 'dx'       in columns else 0
        dy       = row_data[columns.index('dy'      )] if 'dy'       in columns else 0
        rotation = row_data[columns.index('rotation')] if 'rotation' in columns else 0
        scale    = row_data[columns.index('scale'   )] if 'scale'    in columns else 1
        
        return( float(dx), float(dy), float(rotation), float(scale))

class TransformLazyFlowData(LazyFlowData):
    def __init__(self, flowData, dx, dy, rotation, scale, new_width, new_height):
        super().__init__(flowData, dx, dy, rotation, scale, new_width, new_height)
        self.setDimensions(new_width, new_height)
    
    def operation(self, flowData, planeIndex, x, y, dx, dy, rotation, scale, new_width, new_height):
        """変形 + 拡張を一度に実行"""
        import numpy as np
        import cv2
        
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        orig_width, orig_height = flowData.getDimensions()
        
        # 出力ブロックの4隅を逆変換して必要な入力範囲を計算
        dst_min_x = x
        dst_max_x = x + BLOCK_SIZE
        dst_min_y = y
        dst_max_y = y + BLOCK_SIZE
        dst_corners = nh.array([[dst_min_x, dst_min_y],
                                [dst_max_x, dst_min_y],
                                [dst_max_x, dst_max_y],
                                [dst_min_x, dst_max_y]]
                              )
        
        # 順変換行列（target -> ref）を作成
        M = TransformLazyFlowData.createAffine( orig_width, orig_height, 0, 0, dx, dy, rotation, scale)
        M_inv = cv2.invertAffineTransform(M)
        src_corners = cv2.transform(dst_corners.reshape(-1, 1, 2), M_inv).reshape(-1, 2)

        # 必要な入力範囲を計算
        src_min_x = np.min(src_corners[:, 0])
        src_max_x = np.max(src_corners[:, 0])
        src_min_y = np.min(src_corners[:, 1])
        src_max_y = np.max(src_corners[:, 1])
        
        # サブピクセルの場合、隣のピクセルを含める
        src_min_x = int(np.floor(src_min_x - np.ceil(src_min_x % 1)))
        src_max_x = int(np.ceil( src_max_x + np.ceil(src_max_x % 1)))
        src_min_y = int(np.floor(src_min_y - np.ceil(src_min_y % 1)))
        src_max_y = int(np.ceil( src_max_y + np.ceil(src_max_y % 1)))
        
        # ブロック境界に拡張
        src_min_blockX = ((src_min_x                 ) // BLOCK_SIZE) * BLOCK_SIZE
        src_max_blockX = ((src_max_x + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE
        src_min_blockY = ((src_min_y                 ) // BLOCK_SIZE) * BLOCK_SIZE
        src_max_blockY = ((src_max_y + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE
        
        # オリジナルのサイズに切り詰め
        src_min_blockX = max(src_min_blockX, 0)
        src_max_blockX = min(src_max_blockX, orig_width)
        src_min_blockY = max(src_min_blockY, 0)
        src_max_blockY = min(src_max_blockY, orig_height)
        src_blockW = src_max_blockX - src_min_blockX
        src_blockH = src_max_blockY - src_min_blockY

        if src_blockW <= 0 or src_blockH <= 0:
            # 変形元が画像外なので NaN を返す
            return DataBlock(nh.nans((BLOCK_SIZE, BLOCK_SIZE)), planeIndex, x, y)
        else:
            # 変形に必要な範囲の部分元画像を構築
            src_image = nh.nans((src_blockH, src_blockW))
            
            # 必要なブロックを取得して部分元画像に配置
            isAnyNaN = False # 必要なブロックに NaN が含まれているか
            for by in range(src_min_blockY, src_max_blockY, BLOCK_SIZE):
                for bx in range(src_min_blockX, src_max_blockX, BLOCK_SIZE):
                    block = flowData.getBlock(planeIndex, bx, by)
                    if block and block.data is not None:
                        if len(block.data.shape) == 3:
                            block_data = block.data[:, :, 0]
                        else:
                            block_data = block.data
                        
                        # 部分元画像内の位置に配置
                        x1 = bx - src_min_blockX
                        y1 = by - src_min_blockY
                        h, w = block_data.shape
                        src_image[y1:y1+h, x1:x1+w] = block_data

                        if np.isnan(block_data).any():
                            # 必要なブロックに NaN が含まれていた
                            isAnyNaN = True

            # 部分画像を変形するアフィンを計算
            M = TransformLazyFlowData.createAffine( orig_width, orig_height, src_min_blockX, src_min_blockY, dx, dy, rotation, scale)
            
            # アフィン変形後を出力座標系にする
            M[0, 2] += src_min_blockX - dst_min_x
            M[1, 2] += src_min_blockY - dst_min_y
            
            if not isAnyNaN:
                # 部分画像を変形
                transformed_region = cv2.warpAffine(src_image, M, (BLOCK_SIZE, BLOCK_SIZE),
                                                    flags=cv2.INTER_LINEAR,
                                                    borderMode=cv2.BORDER_CONSTANT,
                                                    borderValue=np.nan)
            else:
                # NaN対応の補間変形
                validMask = ~np.isnan(src_image)              # 有効データマスクを作成
                imageData = np.where(validMask, src_image, 0) # 無効データを 0 にした画像
                imageMask = np.where(validMask, nh.nan, 0)    # 有効データを NaN に、無効データを 0 にした画像
                transformed_data = cv2.warpAffine(imageData, M, (BLOCK_SIZE, BLOCK_SIZE),  # データを変形
                                                  flags=cv2.INTER_LINEAR,
                                                  borderMode=cv2.BORDER_CONSTANT,
                                                  borderValue=0)
                transformed_mask = cv2.warpAffine(imageMask, M, (BLOCK_SIZE, BLOCK_SIZE),  # 2値マスクを変形
                                                  flags=cv2.INTER_LINEAR,
                                                  borderMode=cv2.BORDER_CONSTANT,
                                                  borderValue=0)
                # 有効データを NaN に、無効データを 0 にしたマスク画像を用いているから
                # NaN = NaN * 0 なので NaN のある場所が有効なデータとなる
                transformed_region =  np.where( np.isnan(transformed_mask), transformed_data, nh.nan)
            
            # 画面端での適切なブロックサイズを計算
            output_width  = min(BLOCK_SIZE, new_width  - dst_min_x)
            output_height = min(BLOCK_SIZE, new_height - dst_min_y)
            
            result = transformed_region[0:output_height, 0:output_width]
            
            # サイズが足りない場合はNaNでパディング
            if result.shape != (output_height, output_width):
                padded_block = nh.nans((output_height, output_width))
                h, w = result.shape
                padded_block[:h, :w] = result
                result = padded_block
            
            return DataBlock(result, planeIndex, x, y)
    
    @staticmethod
    def createAffine(worldW, worldH, objectX, objectY, dx, dy, rotation, scale):
        """Affine変換行列を作成"""
        import cv2
        
        # 中央を原点としオブジェクトの回転=>拡大=>平行移動する
        # cv2.getRotationMatrix2Dは正の角度で時計回り(CW)の回転行列を返すため、
        # 反時計回り(CCW)の回転角である rotation を負にして渡すことでCCW回転を適用する
        centerX = worldW / 2 - objectX
        centerY = worldH / 2 - objectY
        M = cv2.getRotationMatrix2D((centerX, centerY), -rotation, scale)
        M[0, 2] += dx
        M[1, 2] += dy
        return M
