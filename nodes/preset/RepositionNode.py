'''
RepositionNode - 再配置ノード (Roll, Flip, Rot90, Transpose, Scale)

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import math
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

    def preprocessStreams(self, inputStreams):
        """入力ストリームの前処理：primary/auxiliaryで分類"""
        primaryStreams = []
        auxiliarys     = []
        
        for stream in inputStreams:
            if stream:
                category = stream[0].headers.get('category', 'primary')
                if category == 'auxiliary':
                    auxiliarys.extend(stream)
                else:
                    primaryStreams.append(stream)
        
        # auxiliary データから変換パラメータを取得
        self._params = self._loadParams(auxiliarys)
        
        return primaryStreams

    def createLazyFlowData(self, inputData):
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
             flip_x, flip_y,
             rot90,
             transpose,
             scale_x, scale_y,
             left, top, width, height) = params
            return RepositionLazyFlowData(inputData,
                                          shift_x, shift_y,
                                          flip_x, flip_y,
                                          rot90,
                                          transpose,
                                          scale_x, scale_y, left, top, width, height)

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
        flip_x    = int(row_data[columns.index('flip_x'   )]) if 'flip_x'   in columns else 0
        flip_y    = int(row_data[columns.index('flip_y'   )]) if 'flip_y'   in columns else 0
        rot90     = int(row_data[columns.index('rot90'    )]) if 'rot90'    in columns else 0
        transpose = int(row_data[columns.index('transpose')]) if 'transpose'in columns else 0
        scale_x   = int(row_data[columns.index('scale_x'  )]) if 'scale_x'  in columns else 1
        scale_y   = int(row_data[columns.index('scale_y'  )]) if 'scale_y'  in columns else 1
        left      = int(row_data[columns.index('left'     )]) if 'left'     in columns else None
        top       = int(row_data[columns.index('top'      )]) if 'top'      in columns else None
        width     = int(row_data[columns.index('width'    )]) if 'width'    in columns else None
        height    = int(row_data[columns.index('height'   )]) if 'height'   in columns else None
        
        # scale の検証
        if scale_x < 1 or scale_y < 1:
            raise ValueError('scale_x/scale_y must be integers >= 1')
        
        return (shift_x, shift_y, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, width, height)

class RepositionLazyFlowData(LazyFlowData):
    def __init__(self, flowData, shift_x, shift_y, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, width, height):
        from utils import numpy_helpers as nh
        
        # 出力位置を計算
        w, h = flowData.getDimensions()
        M = self.createAffine(w, h, 0, 0, flip_x, flip_y, rot90, transpose, scale_x, scale_y)
        p = M @ nh.array([[0, w-1], # ピクセル位置で最小位置を計算
                          [0, h-1],
                          [1,   1]])
        l = min(p[0])
        t = min(p[1])

        # width/height が指定されていれば、その領域を切り出す
        l = left if left else l
        t = top  if top  else t
        M = self.createAffine(w, h, shift_x - l, shift_y - t, flip_x, flip_y, rot90, transpose, scale_x, scale_y)
        super().__init__(flowData, M, shift_x, shift_y, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, width, height)
        
        # 出力サイズを計算
        p = M @ nh.array([[0, w], # 入力サイズで出力サイズを計算
                          [0, h],
                          [1, 1]])
        w = math.floor(max(p[0]) - min(p[0]))
        h = math.floor(max(p[1]) - min(p[1]))
        
        # left/top が指定されていれば、その領域を切り出す
        w = width  if width  else w
        h = height if height else h
        self.setDimensions(w, h)
    
    def operation(self, flowData, planeIndex, x, y, M, shift_x, shift_y, flip_x, flip_y, rot90, transpose, scale_x, scale_y, left, top, width, height):
        """再配置を実行
        処理順序は Scale -> Transpose -> Rot90 -> Flip -> Shift
        Resize は 出力結果の範囲
        """
        import numpy as np
        from config import BLOCK_SIZE
        from base import DataBlock
        from utils import numpy_helpers as nh
        
        srcW, srcH = flowData.getDimensions()
        dstW, dstH = self.getDimensions()
        if 0==planeIndex and 0==x and 0==y:
            print("src", (srcW, srcH), "dst", (dstW, dstH))
        
        # 要求された結果ブロックサイズ
        dstBlockW = min(BLOCK_SIZE, dstW - x)
        dstBlockH = min(BLOCK_SIZE, dstH - y)
        
        # 出力ブロック位置のコーナー座標
        l, r, t, b = x, x + dstBlockW - 1, y, y + dstBlockH - 1
        dst_corners = nh.array([
            [l, t],
            [r, t],
            [r, b],
            [l, b],
        ])
        print("dst_corners", "[" + ", ".join([f"({x:.3f}, {y:.3f})" for x,y in dst_corners]) + "]")
        
        # 逆算して読み込む Source 領域を計算
        # Un-Resize -> Un-Shift -> Un-Flip -> Un-Rot90 -> Un-Transpose -> Un-Scale
        Minv = np.linalg.inv(M)
        src_corners = (np.hstack((dst_corners, nh.ones((dst_corners.shape[0], 1)))) @ Minv.T[:, :2])
        print("src_corners", "[" + ", ".join([f"({x:.3f}, {y:.3f})" for x,y in src_corners]) + "]")
        
        # corners の境界跨ぎ(roll)を分解する
        minCorX = min([c[0] for c in src_corners])
        maxCorX = max([c[0] for c in src_corners])
        minCorY = min([c[1] for c in src_corners])
        maxCorY = max([c[1] for c in src_corners])
        minSrcX = math.floor(minCorX)
        endSrcX = math.floor(maxCorX) + 1
        minSrcY = math.floor(minCorY)
        endSrcY = math.floor(maxCorY) + 1
        print("source", f"({minSrcX:.3f}, {minSrcY:.3f}) ({endSrcX:.3f}, {endSrcY:.3f})")
        
        if 0 <= minSrcX and 0 <= minSrcY and endSrcX <= srcW and endSrcY <= srcH:
            source = self._fetchRect(flowData, planeIndex, minSrcX, minSrcY, endSrcX - minSrcX, endSrcY - minSrcY)
        else:
            source = None
            for sy in [minSrcY] + ([0] if minSrcY < 0 else []) + list(range(srcH, endSrcY, srcH)):
                yfrag = None
                for sx in [minSrcX] + ([0] if minSrcX < 0 else []) + list(range(srcW, endSrcX, srcW)):
                    psx = sx % srcW
                    psy = sy % srcH
                    pw = min(srcW - psx, endSrcX - sx)
                    ph = min(srcH - psy, endSrcY - sy)
                    xfrag = self._fetchRect(flowData, planeIndex, psx, psy, pw, ph)
                    if yfrag is None:
                        yfrag = xfrag
                    else:
                        yfrag = np.hstack([yfrag, xfrag])
                if source is None:
                    source = yfrag
                else:
                    source = np.vstack([source, yfrag])
        
        print(source)

        # 結果バッファ
        result = nh.nans((dstBlockH, dstBlockW), dtype=flowData.getVariableType())
        
        # 結果バッファに配置
        for sy in range(minSrcY, endSrcY):
            debug_s = ""
            debug_d = ""
            try:
                for sx in range(minSrcX, endSrcX):
                    ((dx,), (dy,), (_,),) = M @ (nh.array([[sx], [sy], [1]]))
                    dx -= x
                    dy -= y
                    px  = sx - minSrcX
                    py  = sy - minSrcY
                    if (dx < 5 and dy < 5) or (250 < dx and dy < 5):
                        debug_s += "(%.1f, %.1f)"%(sx, sy) + " "
                        debug_d += "(%.1f, %.1f)"%(dx, dy) + " "
                    if(   0 <= dx and dx < dstBlockW       and 0 <= dy and dy < dstBlockH
                      and 0 <= px and px < source.shape[1] and 0 <= py and py < source.shape[0]
                      ):
                        result[int(dy), int(dx)] = source[py, px]
            finally:
                if dy < 8:
                    print(debug_s,debug_d)
            
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
    
    def createAffine(self, width, height, dx, dy, flip_x, flip_y, rot90, transpose, scale_x, scale_y):
        from utils import numpy_helpers as nh
        
        # 変換行列を計算
        # Scale -> Transpose -> Rot90 -> Flip -> move
        M = nh.eye(3)
        
        # 左上座標系から中央座標系へ変換
        M = nh.array([[1, 0, -width /2.0],
                      [0, 1, -height/2.0],
                      [0, 0,           1]]) @ M
        
        # Scale
        M = nh.array([[scale_x,       0, 0],
                      [      0, scale_y, 0],
                      [      0,       0, 1]]) @ M
        
        # Transpose
        if transpose % 2 != 0:
            M = nh.array([[0, 1, 0],
                          [1, 0, 0],
                          [0, 0, 1]]) @ M
        
        # Rot90
        # k=1 (90 CW)  -> Inv (90 CCW)
        # k=2 (180)    -> Inv (180)
        # k=3 (270 CW) -> Inv (90 CW) = 270 CCW
        # rot90 は時計回り(CW)回数、逆変換は rot90 回の CCW 回転
        if rot90 % 4 == 1:
            M = nh.array([[ 0, -1, 0],
                          [ 1,  0, 0],

                          [ 0,  0, 1]]) @ M
        elif rot90 % 4 == 2:
            M = nh.array([[-1, 0, 0],
                          [ 0,-1, 0],
                          [ 0, 0, 1]]) @ M
        elif rot90 % 4 == 3:
            M = nh.array([[ 0, 1, 0],
                          [-1, 0, 0],
                          [ 0, 0, 1]]) @ M
        
        # Flip
        if flip_x % 2 != 0:
            M = nh.array([[-1, 0, 0],
                          [ 0, 1, 0],
                          [ 0, 0, 1]]) @ M
        if flip_y % 2 != 0:
            M = nh.array([[1,  0, 0],
                          [0, -1, 0],
                          [0,  0, 1]]) @ M
        
        # move
        M = nh.array([[1, 0, dx],
                      [0, 1, dy],
                      [0, 0,  1]]) @ M
        
        # 中央座標系から左上座標系へ変換
        M = nh.array([[1, 0, width /2.0],
                      [0, 1, height/2.0],
                      [0, 0,          1]]) @ M
        
        return M
