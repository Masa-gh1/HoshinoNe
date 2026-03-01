'''
RepositionNode - 再配置ノード (Roll, Flip, Rot90, Transpose)

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode

class RepositionNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'reposition'
    # ノード名
    name      = '再配置'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        self._tableData = None

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
        
        return primaryDatas

    def createLazyFlowData(self, inputData):
        """LazyFlowDataを作成"""
        # auxiliaryデータから変換パラメータを取得
        if not self._tableData:
            return inputData  # パラメータ未設定時はそのまま
        
        image_id = self._generateImageId(inputData)
        params = self._getRepositionParams(image_id, self._tableData)

        if not params:
            return inputData
        else:
            shift_x, shift_y, rot90, flip_x, flip_y, transpose, left, top, width, height  = params
            return RepositionLazyFlowData(inputData, shift_x, shift_y, rot90, flip_x, flip_y, transpose, left, top, width, height)

    def _loadTableData(self, auxiliaryDatas):
        """table 形式データを読み込み"""
        import numpy as np

        # 複数の auxiliary データから table 形式を探す
        lines   = []
        columns = None
        tabledatas = []
        for tableFlowData in auxiliaryDatas:
            if 'table' == tableFlowData.headers.get('type'):
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
            raise ValueError("再配置パラメータが必要です")
        
        tabledata = np.vstack(tabledatas)
        
        return {
            'columns': columns,
            'lines': lines,
            'data': tabledata
        }

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

    def _getRepositionParams(self, image_id, tableData):
        """画像識別子から再配置パラメータを取得"""
        lines = tableData['lines']
        columns = tableData['columns']
        data = tableData['data']
        
        if 1 == len(lines):
            row_data = data[0]
        elif image_id in lines:
            row_data = data[lines.index(image_id)]
        elif "" in lines:
            row_data = data[lines.index("")]
        else:
            return None
        
        shift_x   = int(row_data[columns.index('shift_x'  )]) if 'shift_x'  in columns else 0
        shift_y   = int(row_data[columns.index('shift_y'  )]) if 'shift_y'  in columns else 0
        rot90     = int(row_data[columns.index('rot90'    )]) if 'rot90'    in columns else 0
        flip_x    = int(row_data[columns.index('flip_x'   )]) if 'flip_x'   in columns else 0
        flip_y    = int(row_data[columns.index('flip_y'   )]) if 'flip_y'   in columns else 0
        transpose = int(row_data[columns.index('transpose')]) if 'transpose'in columns else 0
        left      = int(row_data[columns.index('left'     )]) if 'left'     in columns else None
        top       = int(row_data[columns.index('top'      )]) if 'top'      in columns else None
        width     = int(row_data[columns.index('width'    )]) if 'width'    in columns else None
        height    = int(row_data[columns.index('height'   )]) if 'height'   in columns else None
        
        return (shift_x, shift_y, rot90, flip_x, flip_y, transpose, left, top, width, height)

class RepositionLazyFlowData(LazyFlowData):
    def __init__(self, flowData, shift_x, shift_y, rot90, flip_x, flip_y, transpose, left, top, width, height):
        super().__init__(flowData, shift_x, shift_y, rot90, flip_x, flip_y, transpose, left, top, width, height)
        
        # 出力サイズを計算
        w, h = flowData.getDimensions()
        w = w - left if left   else w
        h = h - top  if top    else h
        w = width    if width  else w
        h = height   if height else h
        
        # Transpose または Rot90(奇数回) の場合、幅と高さを入れ替え
        isTransposed = (transpose % 2 != 0)
        isRotOdd = (rot90 % 2 != 0)
        
        # Transpose Rot90 どちらか片方だけなら入れ替え、両方なら元に戻る
        if isTransposed ^ isRotOdd:
            self.setDimensions(h, w)
        else:
            self.setDimensions(w, h)

    def operation(self, flowData, planeIndex, x, y, shift_x, shift_y, rot90, flip_x, flip_y, transpose, left, top, width, height):
        """再配置を実行"""
        from config import BLOCK_SIZE
        from base import DataBlock
        from utils import numpy_helpers as nh
        
        srcW, srcH = flowData.getDimensions()
        dstW, dstH = self.getDimensions()
        
        # 要求されたブロックサイズ
        reqW = min(BLOCK_SIZE, dstW - x)
        reqH = min(BLOCK_SIZE, dstH - y)
        
        # Shift (Roll) の逆変換を行い、必要な領域を特定する
        # Shiftは循環するので、出力ブロックは最大4つの矩形領域に分割される可能性がある
        
        # X方向の分割
        srcX_start = (x - shift_x) % dstW
        srcX_end   = (x + reqW - shift_x) % dstW
        
        if srcX_start < srcX_end:
            xs = [(srcX_start, reqW, 0)] # (start, width, dst_offset)
        else:
            w1 = dstW - srcX_start
            w2 = reqW - w1
            xs = [(srcX_start, w1, 0), (0, w2, w1)]
        
        # Y方向の分割
        srcY_start = (y - shift_y) % dstH
        srcY_end   = (y + reqH - shift_y) % dstH
        
        if srcY_start < srcY_end:
            ys = [(srcY_start, reqH, 0)]
        else:
            h1 = dstH - srcY_start
            h2 = reqH - h1
            ys = [(srcY_start, h1, 0), (0, h2, h1)]
            
        # 結果バッファ
        result = nh.nans((reqH, reqW), dtype=flowData.getVariableType())
        
        # 各領域について処理
        for sy, h, dy in ys:
            for sx, w, dx in xs:
                # (sx, sy, w, h) を 逆順変換し Source データを取得し、順変換を適用する
                
                # 対応する Source 領域を計算
                # Un-Flip -> Un-Rot90 -> Un-Transpose -> Un-Resize
                
                # 矩形の4隅
                corners = [(sx, sy), (sx+w, sy), (sx+w, sy+h), (sx, sy+h)]
                
                # Un-Flip
                unflipped_corners = []
                for cx, cy in corners:
                    tx, ty = cx, cy
                    if flip_x % 2: tx = dstW - 1 - tx
                    if flip_y % 2: ty = dstH - 1 - ty
                    unflipped_corners.append((tx, ty))
                
                # Un-Rot90 (Inverse of k*90 deg CW)
                # k=1 (90 CW)  -> Inv (90 CCW)
                # k=2 (180)    -> Inv (180)
                # k=3 (270 CW) -> Inv (90 CW) = 270 CCW
                
                # 回転前の空間サイズ (Transpose後のサイズ)
                # 現在の dstW, dstH は回転後のサイズ
                
                # 回転シミュレーション (CCW)
                # rot90 は時計回り回数。逆変換は rot90 回の CCW 回転。
                k = rot90 % 4
                
                curW, curH = dstW, dstH
                unrotated_corners = unflipped_corners
                
                for _ in range(k):
                    next_corners = []
                    for cx, cy in unrotated_corners:
                        # 90 deg CCW: (x, y) -> (y, W-1-x)
                        nx = cy
                        ny = curW - 1 - cx
                        next_corners.append((nx, ny))
                    unrotated_corners = next_corners
                    curW, curH = curH, curW
                
                # Un-Transpose
                untranspose_corners = []
                for cx, cy in unrotated_corners:
                    tx, ty = cx, cy
                    if transpose % 2:
                        tx, ty = ty, tx
                    untranspose_corners.append((tx, ty))
                
                # 逆変換結果
                src_corners = untranspose_corners
                
                # Source 空間でのバウンディングボックス
                min_src_x = min(c[0] for c in src_corners)
                max_src_x = max(c[0] for c in src_corners)
                min_src_y = min(c[1] for c in src_corners)
                max_src_y = max(c[1] for c in src_corners)
                
                # Un-Resize (Add offset)
                off_x = left if left is not None else 0
                off_y = top  if top  is not None else 0
                
                min_src_x += off_x
                max_src_x += off_x
                min_src_y += off_y
                max_src_y += off_y
                
                # 整数座標に丸める (ピクセル中心ではなくインデックスとして扱うため)
                # 厳密には、回転によって矩形の頂点が入れ替わっているだけなので、
                # min/max で正しい範囲が得られる (ただし max は inclusive)
                
                # 範囲: [min_src_x, max_src_x + 1)
                # ただし、回転しているので width/height が入れ替わっている可能性がある
                
                fetch_w = max_src_x - min_src_x
                fetch_h = max_src_y - min_src_y
                source = self._fetchRect(flowData, planeIndex, min_src_x, min_src_y, fetch_w, fetch_h)
                
                # 取得したデータに対して順変換を適用
                # Source -> Resize -> Transpose -> Rot90 -> Flip -> Shift
                
                processed = source
                
                # Transpose
                if transpose % 2:
                    processed = np.transpose(processed)
                
                # Rot90
                k = rot90 % 4
                if k != 0:
                    # rot90 は時計回り(CW)指定、numpy.rot90 は反時計回り(CCW)
                    # そのため負の値を渡して時計回りにする
                    processed = np.rot90(processed, k=-k)
                
                # Flip
                if flip_x % 2:
                    processed = np.fliplr(processed)
                if flip_y % 2:
                    processed = np.flipud(processed)
                
                # 結果バッファに配置
                result[dy:dy+h, dx:dx+w] = processed
        
        return DataBlock(result, planeIndex, x, y)

    def _fetchRect(self, flowData, planeIndex, x, y, w, h):
        """指定された矩形領域のデータを取得（ブロック境界を跨ぐ場合に対応）"""
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        
        # 必要なブロックの範囲
        bx_start = (x // BLOCK_SIZE) * BLOCK_SIZE
        bx_end   = ((x + w - 1) // BLOCK_SIZE) * BLOCK_SIZE + BLOCK_SIZE
        by_start = (y // BLOCK_SIZE) * BLOCK_SIZE
        by_end   = ((y + h - 1) // BLOCK_SIZE) * BLOCK_SIZE + BLOCK_SIZE
        
        # 作業用バッファ
        buf_w = bx_end - bx_start
        buf_h = by_end - by_start
        buffer = nh.nans((buf_h, buf_w), dtype=flowData.getVariableType())
        
        # ブロックを取得してバッファに配置
        srcW, srcH = flowData.getDimensions()
        
        for by in range(by_start, by_end, BLOCK_SIZE):
            for bx in range(bx_start, bx_end, BLOCK_SIZE):
                # 画像範囲外チェック
                if bx >= srcW or by >= srcH:
                    continue
                    
                block = flowData.getBlock(planeIndex, bx, by)
                if block and block.data is not None:
                    # バッファ内の位置
                    dst_x = bx - bx_start
                    dst_y = by - by_start
                    
                    # ブロックデータサイズ (端の処理)
                    bw = block.getWidth()
                    bh = block.getHeight()
                    
                    buffer[dst_y:dst_y+bh, dst_x:dst_x+bw] = block.data
        
        # バッファから必要な領域を切り出し
        crop_x = x - bx_start
        crop_y = y - by_start
        return buffer[crop_y:crop_y+h, crop_x:crop_x+w]
