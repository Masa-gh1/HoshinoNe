'''
PointShiftEstimationNode - 点像ズレ推定ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from types import SimpleNamespace
from itertools import zip_longest

import hashlib
import datetime

import tkinter as tk
from tkinter import messagebox

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

if TYPE_CHECKING:
    import numpy as np
    from base.DataBlock import DataBlock
    from base.FlowData import FlowData

# 配列 index 定義
X, Y, BRI         = 0, 1, 2    # 点像配列
U, V, W           = 0, 1, 2    # 単位ベクトル配列
DX, DY, ROT, TIME = 0, 1, 2, 3 # 結果配列

class Result:
    def __init__(self, success=False, dx=0, dy=0, rotation=0, confidence=0, time=None, extra_info={}):
        self.success = success
        self.dx = dx
        self.dy = dy
        self.rotation = rotation
        self.confidence = confidence
        self.time = time
        self.extra_info = extra_info

class PointShiftEstimationNode(FlowNode, ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'point_shift_estimation'
    # ノード名
    name      = '点像ズレ推定'
    # 入出力タイプ
    ioType    =_IO_TYPE_N1
    outputCat = _OUT_CAT_AUX

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # 設定パラメーター
        # 画像パラメーター
        self.usePreviousOffset   = True              # 前の画像のズレを考慮する
        # 点像検出法パラメーター
        self.grid                = SimpleNamespace()
        self.grid.rows           = 3                 # グリッド行数
        self.grid.cols           = 3                 # グリッド列数
        self.grid.searchPerGrid  = 8                 # グリッド当たりの選択点像数
        self.ransac              = SimpleNamespace()
        self.ransac.sampleRadius = 100               # RANSAC対応点サンプル半径（ピクセル）
        self.ransac.iterations   = 100               # RANSAC試行回数
        self.ransac.seed         = 2725              # RANSAC乱数シード（１以上）
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return
    
    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nG:{self.grid.cols}x{self.grid.rows} S:{self.ransac.sampleRadius}"
        return displayText
    
    def store(self, nodeData):
        nodeData["usePreviousOffset"] = self.usePreviousOffset
        nodeData["gridRows"] = self.grid.rows
        nodeData["gridCols"] = self.grid.cols
        nodeData["searchPerGrid"] = self.grid.searchPerGrid
        nodeData["ransacIterations"] = self.ransac.iterations
        nodeData["ransacSeed"] = self.ransac.seed
    
    def restore(self, nodeData):
        if "usePreviousOffset" in nodeData:
            self.usePreviousOffset = nodeData["usePreviousOffset"]
        if "gridRows" in nodeData:
            self.grid.rows = nodeData["gridRows"]
        if "gridCols" in nodeData:
            self.grid.cols = nodeData["gridCols"]
        if "searchPerGrid" in nodeData:
            self.grid.searchPerGrid = nodeData["searchPerGrid"]
        if "ransacIterations" in nodeData:
            self.ransac.iterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.ransac.seed = nodeData["ransacSeed"]
    
    def process(self, context=None):
        """点像ズレ推定のメイン処理"""
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)
        
        # primary/auxiliaryで分類
        primaryStreams = self.preprocessStreams(inputStreams)
        if 0 == len(primaryStreams) or not primaryStreams[0]:
            self.flowDatas = []
            return
        
        inputStream = primaryStreams[0]
        assert self._referenceStream
        if 1 == len(self._referenceStream):
            # 基準画像が1枚の場合は全体へブロードキャスト
            self._referenceStream = [self._referenceStream[0]] * len(inputStream)
        
        # 基準点像配列作成
        
        # 各画像の点像ズレ推定
        results = []
        resultL = Result()  # 前画像の結果
        
        for i, (flowData, ref) in enumerate(zip_longest(inputStream, self._referenceStream)):
            self.reportProgress(context, f"画像 {i + 1}/{len(inputStream)} 処理中", i, len(inputStream))
            
            # 点像配列作成
            import numpy as np
            refPoints, refPointsV = self.getPoints(ref)
            points   , pointsV    = self.getPoints(flowData)

            from utils import exif_helper as eh
            width, height = eh.getImageSize(flowData.headers)
            
            # 点像ズレ推定
            if self.usePreviousOffset:
                result, ransac = self.matchPoints(refPoints, points, width, height, resultL)
            else:
                result, ransac = self.matchPoints(refPoints, points, width, height)
            resultL = result
            
            # 結果を保存
            #aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in targetPoints])
            #extra_info["ref_points_count"] = len(refPoints)
            #extra_info["target_points_count"] = len(targetPoints)
            #extra_info["target_points_min_required"] = 3
            #extra_info["ref_bright_count"]    = len(refPoints)
            #extra_info["ref_grid_counts"]     = ref_grid_counts
            #extra_info["target_bright_count"] = len(targetPoints)
            #extra_info["target_grid_counts"]  = target_grid_counts
            #extra_info["aspectRatioMedian"]   = aspectRatioMedian
            
            refDatetime = ref.headers.get('datetime', '')
            refDatetime = datetime.datetime.fromisoformat(refDatetime)
            imageId = self._generateImageId(flowData)
            dt = flowData.headers.get('datetime', '')
            time = (datetime.datetime.fromisoformat(dt) - refDatetime).total_seconds()
            result.time = time
            results.append({
                'image_id': imageId,
                'datetime': dt,
                'result'  : result,
            #    'methods' : method_results
            })
            
            # デバッグ出力
        
        # 出力 Table の FlowData を作成
        self.flowDatas = [self.createFlowData(inputStream, results)]
        
        self.reportProgress(context, "完了")
    
    def preprocessStreams(self, inputStreams:list[list[FlowData]]) -> list[list[FlowData]]:
        """入力データの前処理：primary/auxiliaryで分類"""
        primaryStreams = []
        auxiliaryStreams = []
        
        for stream in inputStreams:
            category = stream[0].headers.get('category', _OUT_CAT_PRI)
            if _OUT_CAT_AUX == category:
                auxiliaryStreams.append(stream)
            else:
                primaryStreams.append(stream)
        
        if not auxiliaryStreams or not auxiliaryStreams[0]:
            # 基準画像（auxiliary）が必要
            self._referenceStream = None
            raise ValueError("基準画像（補正値）が必要です")
        else:
            # 複数ある場合は最初のものを採用
            self._referenceStream = auxiliaryStreams[0]
        
        return primaryStreams
    
    def getPoints(self, flowData:FlowData) -> tuple[np.ndarray,np.ndarray]:
        """
        点像の配列を読み出し
        
        Args:
            flowData: 入力 FlowData
            
        Returns:
            stars: 点像の配列 SHAPE=(N,M) [x, y, brightness,...],...]
            starsV: 点像への単位ベクトル SHAPE=(N,3) [[u, v, w],...]
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from utils import exif_helper as eh
        
        columnCnt, rowCnt = flowData.getDimensions()
        width, height = eh.getImageSize(flowData.headers)
        
        # 画像側の点像を読み込み
        stars = nh.nans((rowCnt, columnCnt)) #  SHAPE=(N,M) [x, y, brightness,...],...]
        for block in flowData.iterateBlocks():
            if block:
                x, y = block.x, block.y
                h, w = block.data.shape
                stars[y:y+h, x:x+w] = block.data
                
        select = []
        columns = flowData.headers["columns"]
        for name in ["x", "y", "brightness"]:
            idx = columns.index(name)
            select.append(stars[:,idx])
        select = np.stack(select, axis=1) # SHAPE=(N,3) [x, y, brightness],...]
        
        # 点像を絞り込み
        selectIdx, _  = self._selectDistributedPoints(select, width, height)
        select = select[selectIdx]
        
        # レンズ中心からの単位 vector を追加
        if True: # self.useHeaderFovDeg:
            # 画像のヘッダからレンズ中心と焦点距離を得て計算
            from utils import exif_helper as eh
            
            focalCenter_px   = eh.getFocalCenter(flowData.headers) # [px]
            focalLength_mm   = eh.getFocalLength(flowData.headers) # [mm]
            resolution_pxpmm = eh.getResolution(flowData.headers)  # [px/mm]
            if focalLength_mm is None or resolution_pxpmm is None:
                raise ValueError("画像のヘッダに焦点情報が設定されていません。")
            
            pointsX = (select[:, X] - focalCenter_px[0]) / resolution_pxpmm[0] # 中心を原点に [mm]
            pointsY = (select[:, Y] - focalCenter_px[1]) / resolution_pxpmm[1] # 中心を原点に [mm]
            f = float(focalLength_mm)                                        # 焦点距離 [mm]
            f = np.broadcast_to(f, pointsX.shape)
        else:
            # 設定値の画角から計算
            pointsX = select[:, X] - (width  / 2) # 中心を原点に [px]
            pointsY = select[:, Y] - (height / 2) # 中心を原点に [px]
            f = (width * width + height * height) ** 0.5 / (2.0 * np.tan(np.radians(self.fovDeg) / 2.0)) # 焦点距離を計算 [px]
            f = np.broadcast_to(f, pointsX.shape)
        pointsV = np.stack([pointsX, pointsY, f]).T
        pointsV = pointsV / np.linalg.norm(pointsV, axis=1, keepdims=True) # 単位ベクトルに変換 SHAPE=(N,3) [[u, v, w],...]
        
        return select, pointsV
        
    def _selectDistributedPoints(self, points:np.ndarray, width:int, height:int) -> tuple[np.ndarray, list[int]]:
        """
        画像全体に分散した点像を選択
        
        Args:
            stars: 点像の座標と明度の配列 SHAPE=(N,4) [[x, y, brightness, area],...]
            width: 画像の幅
            height: 画像の高さ
        
        Returns:
            distributedStars: 分散した点像の indx 配列 SHAPE=(N) [pidx,...]
            gridSelectedCounts: 各グリッドから選択された点像の数のリスト
        """
        import numpy as np
        
        if 0 == len(points):
            return points, []
        
        gridRows, gridCols = self.grid.rows, self.grid.cols
        
        # 各グリッド領域のサイズ
        cellH = height // gridRows
        cellW = width // gridCols
        
        distributedIdx   = []
        gridSelectedCounts = []
        
        # 各グリッドから最大 n 個の明るい点像を選択
        for row in range(gridRows):
            for col in range(gridCols):
                yMin = row * cellH
                yEnd = (row + 1) * cellH if row < gridRows - 1 else height
                xMin = col * cellW
                xEnd = (col + 1) * cellW if col < gridCols - 1 else width
                
                # このグリッド内の点像を抽出
                gridIdx = (np.where((xMin <= points[:,X]) & (points[:,X] < xEnd) & (yMin <= points[:,Y]) & (points[:,Y] < yEnd)))[0]
                
                # 明度順でソートして上位指定数を選択
                gridIdx = gridIdx[np.argsort(points[gridIdx, BRI])][::-1] # 明度順でソート
                selectIdx = gridIdx[:self.grid.searchPerGrid]
                distributedIdx.extend(selectIdx)
                gridSelectedCounts.append(len(selectIdx))
        
        # 全体からも明るい点像を追加 (重複を除く)
        maxTotalStars = gridRows * gridCols * self.grid.searchPerGrid + self.grid.searchPerGrid
        allIdx = np.argsort(points[:, BRI])[::-1] # 明度順でソート
        allIdx = allIdx[~np.isin(allIdx, distributedIdx)]
        distributedIdx.extend(allIdx[:maxTotalStars - len(distributedIdx)])
        
        distributedIdx = np.array(distributedIdx[:maxTotalStars])
        
        return distributedIdx, gridSelectedCounts
    
    def _generateImageId(self, flowData):
        """画像識別子を生成"""
        if "source_file" in flowData.headers:
            return flowData.headers["source_file"]
        elif "datetime" in flowData.headers:
            return f"datetime_{flowData.headers['datetime']}"
        else:
            data_hash = hashlib.md5(str(flowData.headers).encode()).hexdigest()[:8]
            return f"hash_{data_hash}"
    
    def matchPoints(self, refPoints:np.ndarray, targetPoints:np.ndarray, width:int, height:int, resultL=None) -> tuple[Result, dict]:
        """点像をマッチングしてオフセットを推定"""
        import numpy as np
        from utils import numpy_helpers as nh

        if resultL is None:
            resultL = Result()
        
        logging = {} # 実行記録
        
        # RANSAC用固定シードを設定
        rng = np.random.default_rng(self.ransac.seed)
        logging["ransac_seed"] = self.ransac.seed
        
        if len(refPoints) < 3 or len(targetPoints) < 3: # 最低でも3点必要
            logging["message"] = "Not enough points for matching"
            return Result(success=False), logging
        
        # 前画像のオフセット・回転を考慮した対応点探索
        matches = []
        radius_sq = self.ransac.sampleRadius ** 2  # 二乗距離で比較
        
        # 予測位置計算
        rad = np.radians(resultL.rotation)
        M = nh.array([[ np.cos(rad), np.sin(rad)],
                      [-np.sin(rad), np.cos(rad)],
                      [ resultL.dx , resultL.dy ],
                    ])
        expected_pos = np.concatenate([targetPoints[:, X:Y+1], nh.ones((targetPoints.shape[0], 1))], axis=1) @ M
        
        for ref in refPoints:
            # 距離計算（二乗距離）
            dist_sq = np.sum((expected_pos - nh.array(ref[X:Y+1]))**2, axis=1)
            indices = np.where(dist_sq < radius_sq)[0]
            
            # マッチを追加
            for idx in indices:
                matches.append((ref, targetPoints[idx]))
        
        matchTargetCnt = len(np.unique([match[1] for match in matches], axis=0))
        logging["matches_count"] = matchTargetCnt

        if matchTargetCnt < 5:
            logging["message"] = "Not enough matched points for robust estimation"
            return Result(success=False), logging
        
        # RANSACでロバストなオフセットを計算
        offset = None
        inliers = 0
        for iterations in range(self.ransac.iterations): # RANSAC試行回数
            # ランダムに3点選択
            indices = rng.choice(len(matches), min(3, len(matches)), replace=False)
            
            # オフセットを計算 (基準画像に向かって対象画像を動かす方向)
            dx_sum, dy_sum = 0, 0
            for idx in indices:
                ref_pt, target_pt = matches[idx]
                dx_sum += ref_pt[X] - target_pt[X]
                dy_sum += ref_pt[Y] - target_pt[Y]
            
            dx = dx_sum / len(indices)
            dy = dy_sum / len(indices)
            
            # インライアをカウント
            cur_inliers = 0
            for ref_pt, target_pt in matches:
                expected_x = target_pt[X] + dx
                expected_y = target_pt[Y] + dy
                error = np.sqrt((ref_pt[X] - expected_x)**2 + (ref_pt[Y] - expected_y)**2)
                if error < 1.5:  # 1.5ピクセル以内
                    cur_inliers += 1
            
            if cur_inliers > inliers:
                inliers = cur_inliers
                offset = (dx, dy)
                
                # 早期終了条件（十分良い結果）
                if inliers > len(matches) * 0.5 or inliers > 40:  # 50%以上または40個以上のインライア
                    break
        
        logging["ransac_iteration"] = iterations + 1
        logging["inliers"] = inliers
        logging["inliers_min_required"] = 5
        
        if inliers < 5:  # 5個未満のインライア
            logging["message"] = "Not enough inliers for robust estimation"
            return Result(success=False), logging
        
        # グリッド別マッチ数を計算
        grid_match_counts = self._calculateGridMatches(matches, offset, refPoints.shape)
        logging["grid_match_counts"] = grid_match_counts
        
        # インライアを使って回転も含めた変換を計算
        inlier_matches = []
        for ref_pt, target_pt in matches:
            expected_x = target_pt[X] + offset[X]
            expected_y = target_pt[Y] + offset[Y]
            error = np.sqrt((ref_pt[X] - expected_x)**2 + (ref_pt[Y] - expected_y)**2)
            if error < 2.0:
                inlier_matches.append((ref_pt, target_pt))
        
        dx, dy = offset
        rotation = 0
        confidence = min(1.0, inliers / 20.0)  # 正規化した信頼度
        
        #aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in inlier_matches])
        #extra_info["aspectRatioMedian"] = aspectRatioMedian
        
        if 3 <= len(inlier_matches):
            dx, dy, rotation = self._calculateAffineTransform(inlier_matches, width, height)
        
        from utils.Debug import Debug
        debug = f"dx,dy:{dx:.3f},{dy:.3f} rotation:{rotation:.3f} confidence:{confidence:.3f}"
        debug += f" target_bright_count:{logging['target_bright_count']  }" if 'target_bright_count' in logging else ""
        debug += f" aspectRatioMedian:{  logging['aspectRatioMedian']:.2f}" if 'aspectRatioMedian'   in logging else ""
        debug += f" inliers:{            logging['inliers']              }" if 'inliers'             in logging else ""
        debug += f" ransac_iteration:{   logging['ransac_iteration']     }" if 'ransac_iteration'    in logging else ""
        Debug.log(type(self).__name__, f"{debug}")
        
        return Result( success=True, dx=dx, dy=dy, rotation=rotation, confidence=confidence), logging
    
    def _calculateAffineTransform(self, matches, width, height):
        """対応点からアフィン変換を計算（画像中心回転）"""
        import numpy as np
        from utils import numpy_helpers as nh

        cx, cy = width / 2, height / 2
        
        N_in = len(matches)
        t = np.zeros((2 * N_in, 4))
        r = np.zeros(2 * N_in)
        for i in range(N_in):
            rx, ry = matches[i][0][X:Y+1] - [cx, cy]  # 基準 (Ref)
            tx, ty = matches[i][1][X:Y+1] - [cx, cy]  # 対象 (Target)
            
            # rx = a*tx - b*ty + dx
            t[2*i] = [tx, -ty, 1, 0]
            r[2*i] = rx
            # ry = b*tx + a*ty + dy
            t[2*i+1] = [ty, tx, 0, 1]
            r[2*i+1] = ry
        (a, b, dx, dy), _, _, _ = np.linalg.lstsq(t, r, rcond=None)
        rotation = np.degrees(np.arctan2(b, a))
        
        return (dx, dy, rotation)
    
    def _calculateGridMatches(self, matches, offset, image_shape):
        """グリッド別のマッチ数を計算"""
        import numpy as np

        h, w = image_shape
        grid_rows, grid_cols = self.grid.rows, self.grid.cols
        cell_h = h // grid_rows
        cell_w = w // grid_cols
        
        grid_match_counts = [0] * (grid_rows * grid_cols)
        
        for ref_pt, target_pt in matches:
            expected_x = target_pt[X] + offset[X]
            expected_y = target_pt[Y] + offset[Y]
            error = np.sqrt((ref_pt[X] - expected_x)**2 + (ref_pt[Y] - expected_y)**2)
            
            if error < 1.5:  # マッチした場合
                # 基準画像の点像がどのグリッドに属するか判定
                rx, ry, _ = ref_pt
                grid_row = min(int(ry // cell_h), grid_rows - 1)
                grid_col = min(int(rx // cell_w), grid_cols - 1)
                grid_index = grid_row * grid_cols + grid_col
                grid_match_counts[grid_index] += 1
        
        return grid_match_counts
    
    def createFlowData(self, inputDatas:list[FlowData], results) -> FlowData:
        """table形式のFlowDataを生成"""
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        from base import DataBlock
        from base import FlowData
        
        # データ行を作成
        table_data = []
        lines = []
        
        for result_data in results:
            imageId = result_data['image_id']
            result  = result_data['result']

            # データ行: [dx, dy, rotation, confidence, time]
            row = [result.dx, result.dy, result.rotation, result.confidence, result.time]
            table_data.append(row)
            lines.append(imageId)
        
        # numpy配列に変換
        if table_data:
            table_array = nh.array(table_data)
        else:
            table_array = nh.zeros((0, 5))
        
        # ヘッダー情報を設定
        headers = inputDatas[0].headers.copy()
        headers.update({
            'category': self.getOutputCategory(),
            'type'    : 'table',
            'mode'    : '2D',
            'columns' : ['dx', 'dy', 'rotation', 'confidence', 'time'],
            'lines'   : lines,
            'planes'  : ['shift_detection']
        })
                
        # FlowDataを作成
        flowData = FlowData(headers)
        
        # 複数ブロックに対応
        rows, cols = table_array.shape
        flowData.setDimensions(cols, rows)
        for y in range(0, rows, BLOCK_SIZE):
            block_height = min(BLOCK_SIZE, rows - y)
            result = table_array[y:y+block_height, :]
            flowData.setBlock(DataBlock(result, 0, 0, y))
        
        return flowData
    
    def createSettingWindow(self):
        """設定ダイアログを作成"""
        return PointShiftEstimationSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config =(f"{self.minorType}_"
                 f"{self._outputCat}_"
                 f"{self.usePreviousOffset}_"
                 f"{self.grid.rows}_"
                 f"{self.grid.cols}_"
                 f"{self.grid.searchPerGrid}_"
                 f"{self.ransac.sampleRadius}_"
                 f"{self.ransac.iterations}_"
                 f"{self.ransac.seed}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class PointShiftEstimationSettingsDialog(tk.Toplevel):
    """PointShiftEstimationNode 用設定ダイアログ"""
    def __init__(self, parent, node:PointShiftEstimationNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name}設定")
        self.geometry("450x700")
        
        self._createWidgets()
        
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 画像パラメーター
        tk.Label(mainFrame, text="■ 画像パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5,2))
        
        # 前の画像を参照
        prevOffsetFrame = tk.Frame(mainFrame)
        prevOffsetFrame.pack(fill=tk.X, pady=2)
        tk.Label(prevOffsetFrame, text="前の画像を参照:").pack(side=tk.LEFT)
        prevOffsetFrame.pack(fill=tk.X, pady=2)
        self.usePrevOffsetVar = tk.BooleanVar(value=self.node.usePreviousOffset)
        tk.Checkbutton(prevOffsetFrame, text="前の画像のズレを検索範囲の中央に設定", variable=self.usePrevOffsetVar).pack(side=tk.LEFT)
        
        # 点像検出法パラメーター
        tk.Label(mainFrame, text="■ 点像検出法パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        
        # グリッド設定
        gridFrame = tk.Frame(mainFrame)
        gridFrame.pack(fill=tk.X, pady=2)
        tk.Label(gridFrame, text="    グリッド:").pack(side=tk.LEFT)
        self.gridRowsEntry = tk.Entry(gridFrame, width=5)
        self.gridRowsEntry.insert(0, str(self.node.grid.rows))
        self.gridRowsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="x").pack(side=tk.LEFT)
        self.gridColsEntry = tk.Entry(gridFrame, width=5)
        self.gridColsEntry.insert(0, str(self.node.grid.cols))
        self.gridColsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="(点像選択用分割数)").pack(side=tk.LEFT)
        
        # グリッド当たりの選択点像数
        searchPerGridFrame = tk.Frame(mainFrame)
        searchPerGridFrame.pack(fill=tk.X, pady=2)
        tk.Label(searchPerGridFrame, text="    グリッド当たり点像数:").pack(side=tk.LEFT)
        self.searchPerGridEntry = tk.Entry(searchPerGridFrame, width=10)
        self.searchPerGridEntry.insert(0, str(self.node.grid.searchPerGrid))
        self.searchPerGridEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(searchPerGridFrame, text="個 (各グリッドから選ぶ点像数)").pack(side=tk.LEFT)
        
        # サンプル半径
        starDistFrame = tk.Frame(mainFrame)
        starDistFrame.pack(fill=tk.X, pady=2)
        tk.Label(starDistFrame, text="    サンプル半径:").pack(side=tk.LEFT)
        self.DistEntry = tk.Entry(starDistFrame, width=5)
        self.DistEntry.insert(0, str(self.node.ransac.sampleRadius))
        self.DistEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starDistFrame, text="px (統計処理用サンプル収集範囲)").pack(side=tk.LEFT)
        
        # RANSAC試行回数
        ransacFrame = tk.Frame(mainFrame)
        ransacFrame.pack(fill=tk.X, pady=2)
        tk.Label(ransacFrame, text="    RANSAC試行回数:").pack(side=tk.LEFT)
        self.ransacEntry = tk.Entry(ransacFrame, width=5)
        self.ransacEntry.insert(0, str(self.node.ransac.iterations))
        self.ransacEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(ransacFrame, text="回 (外れ値耐性用繰り返し回数)").pack(side=tk.LEFT)
        
        # RANSAC乱数シード
        seedFrame = tk.Frame(mainFrame)
        seedFrame.pack(fill=tk.X, pady=2)
        tk.Label(seedFrame, text="    RANSAC乱数シード:").pack(side=tk.LEFT)
        self.ransacSeedEntry = tk.Entry(seedFrame, width=5)
        self.ransacSeedEntry.insert(0, str(self.node.ransac.seed))
        self.ransacSeedEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(seedFrame, text="(1以上、結果が悪い場合は変更)").pack(side=tk.LEFT)
        
        # ボタンフレーム
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        try:
            self.node.usePreviousOffset        = self.usePrevOffsetVar.get()
            self.node.grid.rows                = max(1, int(self.gridRowsEntry.get()))
            self.node.grid.cols                = max(1, int(self.gridColsEntry.get()))
            self.node.grid.searchPerGrid       = max(1, int(self.searchPerGridEntry.get()))
            self.node.ransac.sampleRadius      = max(10, int(self.DistEntry.get()))
            self.node.ransac.iterations        = max(10, min(10000, int(self.ransacEntry.get())))
            self.node.ransac.seed              = max(1, int(self.ransacSeedEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
                
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
