'''
RepositionNode - 再配置ノード (Roll, Flip, Rot90, Transpose, Scale)

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

import math
import hashlib

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import LazyNNOperationNode

if TYPE_CHECKING:
    from base import FlowData

class RepositionNode(LazyNNOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'reposition'
    # ノード名
    name      = '再配置'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def preprocessStreams(self, inputStreams:list[list[FlowData]]):
        """入力ストリームの前処理"""
        inputStreams = super().preprocessStreams(inputStreams)
        inputStream = inputStreams[0]
        param  = [d for s in inputStreams[1:] for d in s]
        
        self.inputStream = inputStream        
        # auxiliary データから変換パラメータを取得
        self._params = self._loadParams(param)
        
        return [inputStream]
    
    def createLazyFlowData(self, headers:dict, inputData:FlowData) -> LazyFlowData:
        """LazyFlowDataを作成"""
        # auxiliaryデータから変換パラメータを取得
        if not self._params:
            return inputData  # パラメータ未設定時はそのまま
        
        image_id = self._generateImageId(inputData)
        params = self._getRepositionParams(image_id, self._params)

        if not params:
            return inputData
        else:
            (shift_x, shift_y,
             dx, dy, d_plane, d_stream,
             flip_x, flip_y,
             rot90,
             transpose,
             scale_x, scale_y,
             left, top, front, begin,
             width, height, plane, stream) = params
            return RepositionLazyFlowData(headers,
                                          inputData,
                                          self,
                                          shift_x, shift_y,
                                          dx, dy, d_plane, d_stream,
                                          flip_x, flip_y,
                                          rot90,
                                          transpose,
                                          scale_x, scale_y,
                                          left, top, front, begin,
                                          width, height, plane, stream)

    def _loadParams(self, auxiliarys):
        """table 形式データを読み込み"""
        import numpy as np

        # 複数の auxiliary データから table 形式を探す
        lines   = []
        columns = None
        tabledatas = []
        for tableFlowData in auxiliarys:
            if 'table' == tableFlowData.headers.get('type'):
                lines.extend(tableFlowData.headers.get('lines', []))
                columnCur = tableFlowData.headers.get('columns', [])
                
                columns = columnCur if columns is None else columns

                if columns != columnCur:
                    pass # 列が違う場合は無視
                else:
                    # 縦1列のブロックのみを結合
                    for block in tableFlowData.iterateBlocks():
                        if not block or block.data is None or 0 != block.x:
                            pass
                        else:
                            tabledatas.append(block.data)
        
        if not tabledatas:
            raise ValueError("再配置パラメータが必要です")
        
        tabledata = np.vstack(tabledatas)

        if 1 != len(lines) and len(tabledata) != len(lines):
            raise ValueError("再配置パラメータの行数が不正です")
        
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
        dx        = int(row_data[columns.index('dx'       )]) if 'dx'       in columns else 0
        dy        = int(row_data[columns.index('dy'       )]) if 'dy'       in columns else 0
        d_plane   = int(row_data[columns.index('d_plane'  )]) if 'd_plane'  in columns else 0
        d_stream  = int(row_data[columns.index('d_stream' )]) if 'd_stream' in columns else 0
        flip_x    = int(row_data[columns.index('flip_x'   )]) if 'flip_x'   in columns else 0
        flip_y    = int(row_data[columns.index('flip_y'   )]) if 'flip_y'   in columns else 0
        rot90     = int(row_data[columns.index('rot90'    )]) if 'rot90'    in columns else 0
        transpose = int(row_data[columns.index('transpose')]) if 'transpose'in columns else 0
        scale_x   = int(row_data[columns.index('scale_x'  )]) if 'scale_x'  in columns else 1
        scale_y   = int(row_data[columns.index('scale_y'  )]) if 'scale_y'  in columns else 1
        left      = int(row_data[columns.index('left'     )]) if 'left'     in columns else None
        top       = int(row_data[columns.index('top'      )]) if 'top'      in columns else None
        front     = int(row_data[columns.index('front'    )]) if 'front'    in columns else None
        begin     = int(row_data[columns.index('begin'    )]) if 'begin'    in columns else None
        width     = int(row_data[columns.index('width'    )]) if 'width'    in columns else None
        height    = int(row_data[columns.index('height'   )]) if 'height'   in columns else None
        plane     = int(row_data[columns.index('plane'    )]) if 'plane'    in columns else None
        stream    = int(row_data[columns.index('stream'   )]) if 'stream'   in columns else None
        
        # scale の検証
        if scale_x < 1 or scale_y < 1:
            raise ValueError('scale_x/scale_y must be integers >= 1')
        
        return (shift_x, shift_y, dx, dy, d_plane, d_stream, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, front, begin, width, height, plane, stream)

class RepositionLazyFlowData(LazyFlowData):
    __slots__ = ()
    
    def __init__(self, headers:dict, flowData:FlowData, node:RepositionNode, shift_x, shift_y, dx, dy, d_plane, d_stream, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, front, begin, width, height, plane, stream):
        from utils import numpy_helpers as nh
        
        # 出力位置を計算
        w, h = flowData.getDimensions()
        p = flowData.getPlaneCount()
        s = len(node.inputStream)
        M = self.createAffine(w, h, 0, 0, 0, 0, flip_x, flip_y, rot90, transpose, scale_x, scale_y)
        o = M @ nh.array([[0, w-1], # ピクセル位置で最小位置を計算
                          [0, h-1],
                          [0, p-1],
                          [0, s-1],
                          [1,   1]])
        l = min(o[0]) # 左(x)
        t = min(o[1]) # 上(y)
        f = min(o[2]) # 前(plane)
        b = min(o[3]) # 始(stream)
        # left/top/front/begin が指定されていれば、その領域を切り出す
        l = left  if left  else l
        t = top   if top   else t
        f = front if front else f
        b = begin if begin else b
        M = self.createAffine(w, h, dx - l, dy - t, d_plane - f, d_stream - b,  flip_x, flip_y, rot90, transpose, scale_x, scale_y)
        super().__init__(headers, flowData, node, M, shift_x, shift_y, dx, dy, d_plane, d_stream, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, front, begin, width, height, plane, stream)
        
        # 出力サイズを計算
        o = M @ nh.array([[0, w], # 入力サイズで出力サイズを計算
                          [0, h],
                          [0, p],
                          [0, s],
                          [1, 1]])
        w = math.floor(max(o[0]) - min(o[0]))
        h = math.floor(max(o[1]) - min(o[1]))
        p = math.floor(max(o[2]) - min(o[2]))
        s = math.floor(max(o[3]) - min(o[3]))
        
        # width/height/plane/stream  が指定されていれば、その領域を切り出す
        w = width  if width  else w
        h = height if height else h
        p = plane  if plane  else o
        s = stream if stream else s
        self.setDimensions(w, h)
    
    def operation(self, flowData:FlowData, planeIndex:int, x:int, y:int, node:RepositionNode, M, shift_x, shift_y, dx, dy, d_plane, d_stream, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, front, begin, width, height, plane, stream):
        """再配置を実行
        処理順序は Scale -> Transpose -> Rot90 -> Flip -> Shift
        Resize は 出力結果の範囲
        """
        from config import BLOCK_SIZE
        from base import DataBlock
        from utils import numpy_helpers as nh
        
        if 0 == shift_x and 0 == shift_y:
            result = self._operation(flowData, planeIndex, x, y, node, M)
        else:
            # shift_x / shift_y がある
            dstW, dstH = self.getDimensions()
            dstBlockW = min(BLOCK_SIZE, dstW - x)
            dstBlockH = min(BLOCK_SIZE, dstH - y)
            shiftedX = (x - shift_x) % dstW
            shiftedY = (y - shift_y) % dstH
            shiftedW = min(dstBlockW, dstW - shiftedX)
            shiftedH = min(dstBlockH, dstH - shiftedY)

            # ロールシフトで縁を跨ぐ場合、2つ以上のブロックを取得して合成
            chunk, BX, BY, X, Y, W, H = [], 0, 1, 2, 3, 4, 5
            chunk.append([0       , 0       , shiftedX, shiftedY,             shiftedW,             shiftedH])
            chunk.append([shiftedW, 0       , 0       , shiftedY, dstBlockW - shiftedW,             shiftedH]) if shiftedW < dstBlockW                          else None
            chunk.append([0       , shiftedH, shiftedX, 0       ,             shiftedW, dstBlockH - shiftedH]) if                          shiftedH < dstBlockH else None
            chunk.append([shiftedW, shiftedH, 0       , 0       , dstBlockW - shiftedW, dstBlockH - shiftedH]) if shiftedW < dstBlockW and shiftedH < dstBlockH else None
            
            # 結果バッファ
            result = nh.nans((dstBlockH, dstBlockW), dtype=flowData.getVariableType())
            
            for c in chunk:
                tmp = self._operation(flowData, planeIndex, c[X], c[Y], node, M)
                result[c[BY]:c[BY]+c[H], c[BX]:c[BX]+c[W]] = tmp[:c[H], :c[W]]
        
        return DataBlock(result, planeIndex, x, y)
    
    def _operation(self, flowData:FlowData, planeIndex:int, x:int, y:int, node:RepositionNode, M):
        import numpy as np
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        
        streamIndex = node.flowDatas.index(self)
        dstW, dstH = self.getDimensions()
        
        # 要求された結果ブロックサイズ
        dstBlockW = min(BLOCK_SIZE, dstW - x)
        dstBlockH = min(BLOCK_SIZE, dstH - y)
        
        # 出力ブロック位置のコーナー座標
        l, r, t, b = x, x + dstBlockW - 1, y, y + dstBlockH - 1
        dst_corners = nh.array([
            [l, t, planeIndex, streamIndex, 1],
            [r, t, planeIndex, streamIndex, 1],
            [r, b, planeIndex, streamIndex, 1],
            [l, b, planeIndex, streamIndex, 1],
        ])
        
        # 逆算して読み込む Source 領域を計算
        # Un-Resize -> Un-Shift -> Un-Flip -> Un-Rot90 -> Un-Transpose -> Un-Scale
        Minv = np.linalg.inv(M)
        src_corners = dst_corners @ Minv.T[:, :4]
        
        # corners の境界跨ぎ(roll)を分解する
        minCorX = min([c[0] for c in src_corners])
        maxCorX = max([c[0] for c in src_corners])
        minCorY = min([c[1] for c in src_corners])
        maxCorY = max([c[1] for c in src_corners])
        minSrcX = math.floor(minCorX)
        endSrcX = math.floor(maxCorX) + 1
        minSrcY = math.floor(minCorY)
        endSrcY = math.floor(maxCorY) + 1
        srcP    = int(min([c[2] for c in src_corners]))
        srcS    = int(min([c[3] for c in src_corners]))

        # ソース取得
        srcFlowData = node.inputStream[srcS]
        srcW, srcH = srcFlowData.getDimensions()
        source = self._fetchRect(srcFlowData, srcP, minSrcX, minSrcY, endSrcX - minSrcX, endSrcY - minSrcY)
        
        # 結果バッファ
        result = nh.nans((dstBlockH, dstBlockW), dtype=srcFlowData.getVariableType())
        
        # 結果バッファに再配置
        sy, sx = np.mgrid[minSrcY:endSrcY, minSrcX:endSrcX].astype(nh.BDTYPE)
        sx = sx.ravel()
        sy = sy.ravel()
        pts = np.vstack([sx, sy, nh.full(sx.shape, srcP), nh.full(sx.shape, srcS), nh.ones(sx.shape)])
        dst_pts = M[:2, :] @ pts
        dx = (dst_pts[0] - x).astype(np.uint32)
        dy = (dst_pts[1] - y).astype(np.uint32)
        px = (sx - minSrcX).astype(np.uint32)
        py = (sy - minSrcY).astype(np.uint32)
        valid = (
            (0 <= dx) & (dx < dstBlockW) &
            (0 <= dy) & (dy < dstBlockH) &
            (0 <= px) & (px < source.shape[1]) &
            (0 <= py) & (py < source.shape[0])
        )
        if np.any(valid):
            result[dy[valid], dx[valid]] = source[py[valid], px[valid]]

        return result
    
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
    
    def createAffine(self, width, height, dx, dy, d_plane, d_stream, flip_x, flip_y, rot90, transpose, scale_x, scale_y):
        from utils import numpy_helpers as nh
        
        # 変換行列を計算
        # Scale -> Transpose -> Rot90 -> Flip -> move
        M = nh.eye(5) # x, y, planeIndex, streamIndex, 1
        
        # 左上座標系から中央座標系へ変換
        M = nh.array([[1, 0, 0, 0, -width /2.0],
                      [0, 1, 0, 0, -height/2.0],
                      [0, 0, 1, 0,           0],
                      [0, 0, 0, 1,           0],
                      [0, 0, 0, 0,           1]]) @ M
        
        # Scale
        M = nh.array([[scale_x,       0, 0, 0, 0],
                      [      0, scale_y, 0, 0, 0],
                      [      0,       0, 1, 0, 0],
                      [      0,       0, 0, 1, 0],
                      [      0,       0, 0, 0, 1]]) @ M
        
        # Transpose
        if transpose % 2 != 0:
            M = nh.array([[0, 1, 0, 0, 0],
                          [1, 0, 0, 0, 0],
                          [0, 0, 1, 0, 0],
                          [0, 0, 0, 1, 0],
                          [0, 0, 0, 0, 1]]) @ M
        
        # Rot90
        # k=1 (90 CW)  -> Inv (90 CCW)
        # k=2 (180)    -> Inv (180)
        # k=3 (270 CW) -> Inv (90 CW) = 270 CCW
        # rot90 は時計回り(CW)回数、逆変換は rot90 回の CCW 回転
        if rot90 % 4 == 1:
            M = nh.array([[ 0, -1, 0, 0, 0],
                          [ 1,  0, 0, 0, 0],
                          [ 0,  0, 1, 0, 0],
                          [ 0,  0, 0, 1, 0],
                          [ 0,  0, 0, 0, 1]]) @ M
        elif rot90 % 4 == 2:
            M = nh.array([[-1,  0, 0, 0, 0],
                          [ 0, -1, 0, 0, 0],
                          [ 0,  0, 1, 1, 0],
                          [ 0,  0, 0, 1, 0],
                          [ 0,  0, 0, 0, 1]]) @ M
        elif rot90 % 4 == 3:
            M = nh.array([[ 0, 1, 0, 0, 0],
                          [-1, 0, 0, 0, 0],
                          [ 0, 0, 1, 0, 0],
                          [ 0, 0, 0, 1, 0],
                          [ 0, 0, 0, 0, 1]]) @ M
        
        # Flip
        if flip_x % 2 != 0:
            M = nh.array([[-1, 0, 0, 0, 0],
                          [ 0, 1, 0, 0, 0],
                          [ 0, 0, 1, 0, 0],
                          [ 0, 0, 0, 1, 0],
                          [ 0, 0, 0, 0, 1]]) @ M
        if flip_y % 2 != 0:
            M = nh.array([[1,  0, 0, 0, 0],
                          [0, -1, 0, 0, 0],
                          [0,  0, 1, 0, 0],
                          [0,  0, 0, 1, 0],
                          [0,  0, 0, 0, 1]]) @ M
        
        # move
        M = nh.array([[1, 0, 0, 0, dx      ],
                      [0, 1, 0, 0, dy      ],
                      [0, 0, 1, 0, d_plane ],
                      [0, 0, 0, 1, d_stream],
                      [0, 0, 0, 0, 1       ]]) @ M
        
        # 中央座標系から左上座標系へ変換
        M = nh.array([[1, 0, 0, 0, width /2.0],
                      [0, 1, 0, 0, height/2.0],
                      [0, 0, 1, 0,          0],
                      [0, 0, 0, 1,          0],
                      [0, 0, 0, 0,          1]]) @ M
        
        return M
