'''
PointShiftEstimationNode - 点像ズレ推定ノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from types import SimpleNamespace

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
X, Y, BRI    = 0, 1, 2 # 点像配列
U, V, W      = 0, 1, 2 # 単位ベクトル配列

class AlignmentResult:
    def __init__(self, success=False, dx=0, dy=0, rotation=0, confidence=0, time=None, method="", extra_info={}):
        self.success = success
        self.dx = dx
        self.dy = dy
        self.rotation = rotation
        self.confidence = confidence
        self.time = time
        self.method = method
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
        
        # 設定パラメータ
        # 画像パラメータ
        self.usePreviousOffset   = True              # 前の画像のズレを考慮する
        # オフセット計算 優先順位1: 星点検出法
        self.grid                = SimpleNamespace()
        self.grid.rows           = 3                 # グリッド行数
        self.grid.cols           = 3                 # グリッド列数
        self.grid.starsPerGrid   = 8                 # グリッド当たりの選択星数
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
        nodeData["starsPerGrid"] = self.grid.starsPerGrid
        nodeData["ransacIterations"] = self.ransac.iterations
        nodeData["ransacSeed"] = self.ransac.seed
    
    def restore(self, nodeData):
        if "usePreviousOffset" in nodeData:
            self.usePreviousOffset = nodeData["usePreviousOffset"]
        if "gridRows" in nodeData:
            self.grid.rows = nodeData["gridRows"]
        if "gridCols" in nodeData:
            self.grid.cols = nodeData["gridCols"]
        if "starsPerGrid" in nodeData:
            self.grid.starsPerGrid = nodeData["starsPerGrid"]
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
        
        # 基準点像配列作成
        refPoints, refPointsV = self.getPoints(self._referenceData)
        
        # 各画像の点像ズレ推定
        results = []
        previous_result = AlignmentResult()  # 前画像の結果
        
        for i, flowData in enumerate(inputStream):
            self.reportProgress(context, f"画像 {i + 1}/{len(inputStream)} 処理中", i, len(inputStream))
            
            # 点像配列作成
            import numpy as np
            points, pointsV = self.getPoints(flowData)
            
            # 点像ズレ推定
            result = self._findOffsetByStarDetection(refPoints, points, previous_result)
            previous_result = result
            
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
            
            refDatetime = self._referenceData.headers.get('datetime', '')
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
            self._referenceData = None
            raise ValueError("基準画像（補正値）が必要です")
        else:
            # 複数ある場合は最初のものを採用
            self._referenceData = auxiliaryStreams[0][0]
        
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
        画像全体に分散した星を選択
        
        Args:
            stars: 点像の座標と明度の配列 SHAPE=(N,4) [[x, y, brightness, area],...]
            width: 画像の幅
            height: 画像の高さ
        
        Returns:
            distributedStars: 分散した星の indx 配列 SHAPE=(N) [pidx,...]
            gridSelectedCounts: 各グリッドから選択された星の数のリスト
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
        
        # 各グリッドから最大 n 個の明るい星を選択
        for row in range(gridRows):
            for col in range(gridCols):
                yMin = row * cellH
                yEnd = (row + 1) * cellH if row < gridRows - 1 else height
                xMin = col * cellW
                xEnd = (col + 1) * cellW if col < gridCols - 1 else width
                
                # このグリッド内の星を抽出
                gridIdx = (np.where((xMin <= points[:,X]) & (points[:,X] < xEnd) & (yMin <= points[:,Y]) & (points[:,Y] < yEnd)))[0]
                
                # 明度順でソートして上位指定数を選択
                gridIdx = gridIdx[np.argsort(points[gridIdx, BRI])][::-1] # 明度順でソート
                selectIdx = gridIdx[:self.grid.starsPerGrid]
                distributedIdx.extend(selectIdx)
                gridSelectedCounts.append(len(selectIdx))
        
        # 全体からも明るい星を追加 (重複を除く)
        maxTotalStars = gridRows * gridCols * self.grid.starsPerGrid + self.grid.starsPerGrid
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
    
    def _findOffsetByStarDetection(self, refPoints, targetPoints, previous_result=None):
        """星点検出による天体写真用位置合わせ"""
        import numpy as np
        from utils import numpy_helpers as nh

        if previous_result is None:
            previous_result = AlignmentResult()
        
        extra_info = {}
        
        # 現在の画像サイズを保存（_calculateAffineTransformで使用）
        currentImageShape = refPoints.shape
        
        # RANSAC用固定シードを設定
        rng = np.random.default_rng(self.ransac.seed)
        extra_info["ransac_seed"] = self.ransac.seed
        
        if len(refPoints) < 3 or len(targetPoints) < 3:
            return AlignmentResult(success=False, method="points", extra_info=extra_info)
        
        # 前画像のオフセット・回転を考慮した対応点探索
        matches = []
        radius_sq = self.ransac.sampleRadius ** 2  # 二乗距離で比較
        
        # 予測位置計算
        if self.usePreviousOffset:
            expected_pos = targetPoints[:, X:Y+1] + nh.array([previous_result.dx, previous_result.dy])
        else:
            expected_pos = targetPoints[:, X:Y+1]
        
        for i, (rx, ry) in enumerate(refPoints[:, X:Y+1]):
            # 距離計算（二乗距離）
            dist_sq = np.sum((expected_pos - nh.array([rx, ry]))**2, axis=1)
            valid_indices = np.where(dist_sq < radius_sq)[0]
            
            # マッチを追加
            for j in valid_indices:
                tx, ty, brightness = targetPoints[j]
                matches.append(((rx, ry), (tx, ty), brightness))
        
        #aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in matches])
        extra_info["matches_count"] = len(matches)
        extra_info["matches_count_min_required"] = 5
        #extra_info["aspectRatioMedian"] = aspectRatioMedian

        if len(matches) < 5:
            return AlignmentResult(success=False, method="star", extra_info=extra_info)
        
        # RANSACでロバストなオフセットを計算
        offset = None
        inliers = 0
        for ransac_iteration in range(self.ransac.iterations): # RANSAC試行回数
            # ランダムに3点選択
            sample = rng.choice(len(matches), min(3, len(matches)), replace=False)
            
            # オフセットを計算（基準画像に向かって対象画像を動かす方向）
            dx_sum, dy_sum = 0, 0
            for idx in sample:
                ref_pt, target_pt, _ = matches[idx]
                dx_sum += ref_pt[0] - target_pt[0]
                dy_sum += ref_pt[1] - target_pt[1]
            
            dx = dx_sum / len(sample)
            dy = dy_sum / len(sample)
            
            # インライアをカウント
            cur_inliers = 0
            for ref_pt, target_pt, _ in matches:
                expected_x = target_pt[0] + dx
                expected_y = target_pt[1] + dy
                error = np.sqrt((ref_pt[0] - expected_x)**2 + (ref_pt[1] - expected_y)**2)
                if error < 1.5:  # 1.5ピクセル以内
                    cur_inliers += 1
            
            if cur_inliers > inliers:
                inliers = cur_inliers
                offset = (dx, dy)
                
                # 早期終了条件（十分良い結果）
                if inliers > len(matches) * 0.5 or inliers > 40:  # 50%以上または40個以上のインライア
                    break
        
        extra_info["ransac_iteration"] = ransac_iteration + 1
        extra_info["inliers"] = inliers
        extra_info["inliers_min_required"] = 5
        
        if inliers < 5:  # 5個未満のインライア
            return AlignmentResult(success=False, method="star", extra_info=extra_info)
        
        # グリッド別マッチ数を計算
        grid_match_counts = self._calculateGridMatches(matches, offset, refPoints.shape)
        extra_info["grid_match_counts"] = grid_match_counts
        
        # インライアを使って回転も含めた変換を計算
        inlier_matches = []
        for ref_pt, target_pt, brightness  in matches:
            expected_x = target_pt[0] + offset[0]
            expected_y = target_pt[1] + offset[1]
            error = np.sqrt((ref_pt[0] - expected_x)**2 + (ref_pt[1] - expected_y)**2)
            if error < 2.0:
                inlier_matches.append((ref_pt, target_pt, brightness))
        
        dx, dy = offset
        rotation = 0
        confidence = min(1.0, inliers / 20.0)  # 正規化した信頼度
        
        #aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in inlier_matches])
        #extra_info["aspectRatioMedian"] = aspectRatioMedian
        
        if 3 <= len(inlier_matches):
            dx, dy, rotation = self._calculateAffineTransform(inlier_matches, currentImageShape)
        
        from utils.Debug import Debug
        debug = f"dx,dy:{dx:.3f},{dy:.3f} rotation:{rotation:.3f} confidence:{confidence:.3f}"
        debug += f" target_bright_count:{extra_info['target_bright_count']  }" if 'target_bright_count' in extra_info else ""
        debug += f" aspectRatioMedian:{  extra_info['aspectRatioMedian']:.2f}" if 'aspectRatioMedian'   in extra_info else ""
        debug += f" inliers:{            extra_info['inliers']              }" if 'inliers'             in extra_info else ""
        debug += f" ransac_iteration:{   extra_info['ransac_iteration']     }" if 'ransac_iteration'    in extra_info else ""
        Debug.log(type(self).__name__, f"{debug}")
        
        return AlignmentResult( success=True, dx=dx, dy=dy, rotation=rotation, confidence=confidence, method="star", extra_info=extra_info)
    
    def _calculateAffineTransform(self, matches, shape):
        """対応点からアフィン変換を計算（画像中心回転）"""
        import numpy as np
        import cv2
        from utils import numpy_helpers as nh

        ref_pts = nh.array([match[0] for match in matches])
        target_pts = nh.array([match[1] for match in matches])
        
        # 画像中心を回転中心として使用
        h, w = shape
        image_center = nh.array([w/2, h/2])
        
        # 画像中心を原点とした座標系に変換
        ref_centered = ref_pts - image_center
        target_centered = target_pts - image_center
        
        # 中心座標系でアフィン変換を計算
        M = cv2.estimateAffinePartial2D(target_centered, ref_centered, method=cv2.RANSAC, ransacReprojThreshold=2.0)[0]
        
        if M is not None:
            # 回転角を計算
            cos_r = M[0, 0]
            sin_r = M[1, 0]
            rotation_angle = np.arctan2(sin_r, cos_r) * 180 / np.pi
            
            # 平行移動成分
            dx = M[0, 2]
            dy = M[1, 2]
            
            return (dx, dy, rotation_angle)
        else:
            # アフィン変換が失敗した場合は平行移動のみ
            dx_sum = sum(ref_pt[0] - target_pt[0] for ref_pt, target_pt in matches)
            dy_sum = sum(ref_pt[1] - target_pt[1] for ref_pt, target_pt in matches)
            return (dx_sum / len(matches), dy_sum / len(matches), 0.0)
    
    def _calculateGridMatches(self, matches, offset, image_shape):
        """グリッド別のマッチ数を計算"""
        import numpy as np

        h, w = image_shape
        grid_rows, grid_cols = self.grid.rows, self.grid.cols
        cell_h = h // grid_rows
        cell_w = w // grid_cols
        
        grid_match_counts = [0] * (grid_rows * grid_cols)
        
        for ref_pt, target_pt, _ in matches:
            expected_x = target_pt[0] + offset[0]
            expected_y = target_pt[1] + offset[1]
            error = np.sqrt((ref_pt[0] - expected_x)**2 + (ref_pt[1] - expected_y)**2)
            
            if error < 1.5:  # マッチした場合
                # 基準画像の星がどのグリッドに属するか判定
                rx, ry = ref_pt
                grid_row = min(int(ry // cell_h), grid_rows - 1)
                grid_col = min(int(rx // cell_w), grid_cols - 1)
                grid_index = grid_row * grid_cols + grid_col
                grid_match_counts[grid_index] += 1
        
        return grid_match_counts
    
    def createFlowData(self, inputDatas:FlowData, results) -> FlowData:
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
        headers = {
            'category': self.getOutputCategory(),
            'type'    : 'table',
            'mode'    : '2D',
            'columns' : ['dx', 'dy', 'rotation', 'confidence', 'time'],
            'lines'   : lines,
            'planes'  : ['shift_detection']
        }
                
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
                 f"{self.grid.starsPerGrid}_"
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
        
        # 画像パラメータ
        tk.Label(mainFrame, text="■ 画像パラメータ", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5,2))
        
        # 前の画像を参照
        prevOffsetFrame = tk.Frame(mainFrame)
        prevOffsetFrame.pack(fill=tk.X, pady=2)
        tk.Label(prevOffsetFrame, text="前の画像を参照:").pack(side=tk.LEFT)
        prevOffsetFrame.pack(fill=tk.X, pady=2)
        self.usePrevOffsetVar = tk.BooleanVar(value=self.node.usePreviousOffset)
        tk.Checkbutton(prevOffsetFrame, text="前の画像のズレを検索範囲の中央に設定", variable=self.usePrevOffsetVar).pack(side=tk.LEFT)
        
        # オフセット計算
        tk.Label(mainFrame, text="■ オフセット計算", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        
        # 優先順位1: 星点検出法
        tk.Label(mainFrame, text="  □ 優先順位1: 星点検出法", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8,2))
        
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
        tk.Label(gridFrame, text="(星選択用分割数)").pack(side=tk.LEFT)
        
        # グリッド当たりの選択星数
        starsFrame = tk.Frame(mainFrame)
        starsFrame.pack(fill=tk.X, pady=2)
        tk.Label(starsFrame, text="    グリッド当たり星数:").pack(side=tk.LEFT)
        self.PerGridEntry = tk.Entry(starsFrame, width=10)
        self.PerGridEntry.insert(0, str(self.node.grid.starsPerGrid))
        self.PerGridEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから選ぶ星数)").pack(side=tk.LEFT)
        
        # 星サンプル半径
        starDistFrame = tk.Frame(mainFrame)
        starDistFrame.pack(fill=tk.X, pady=2)
        tk.Label(starDistFrame, text="    星サンプル半径:").pack(side=tk.LEFT)
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
            self.node.grid.starsPerGrid        = max(1, int(self.PerGridEntry.get()))
            self.node.ransac.sampleRadius      = max(10, int(self.DistEntry.get()))
            self.node.ransac.iterations        = max(10, min(10000, int(self.ransacEntry.get())))
            self.node.ransac.seed              = max(1, int(self.ransacSeedEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
                
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
