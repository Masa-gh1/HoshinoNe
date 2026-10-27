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
        """シフト検出のメイン処理"""
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputStreams = []
        for node in self.inputNodes:
            inputStreams.append(node.flowDatas)
        
        # primary/auxiliaryで分類
        primaryStreams = self.preprocessStreams(inputStreams)
        if self._referenceData is None:
            self.flowDatas = []
            return
        
        inputStream = primaryStreams[0]
        
        # シフト検出を実行
        results = self._calculateShifts(self._referenceData, inputStream, context)
        
        # table形式でFlowDataを生成
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
    
    def _calculateShifts(self, referenceData, inputDatas, context):
        """シフト検出を実行"""
        # 経過報告用全画像のズレ計算ステップ数
        totalGlobalBlocks = 1 + 2*(len(inputDatas) - 1)  # 基準画像処理(1) + 各非基準画像のズレ計算(2回ずつ)
        globalProcessedBlocks = 0
        
        # 基準画像の星を一度だけ検出して保存
        self._cached_ref_stars = self._detectStars(refGray)
        
        globalProcessedBlocks += 1
        if context:
            self.reportProgress(context, f"画像1のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)
        
        # 各画像の移動/回転を計算
        all_results = []
        all_method_results_list = []  # 各画像の計算法毎の結果を保存
        previous_result = AlignmentResult()  # 前画像の結果
        
        for i, inputData in enumerate(inputDatas):
            # 対象画像を検出用に処理
            targetGray = self._flowDataToImage(inputData, planeIndex=alignmentPlane, normalizeForDetection=True)
            globalProcessedBlocks += 1
            if context:
                self.reportProgress(context, f"画像{i+1}のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)
            
            # 位置合わせ計算
            result = None
            result = self._findOffsetByStarDetection(refGray, targetGray, previous_result)
            if result:
                star_result = result
            
            # 成功した結果を選択
            if result is None:
                result = AlignmentResult()
            
            # この画像の計算法毎の結果を保存
            method_results = {'star': star_result}
            
            all_results.append(result)
            all_method_results_list.append(method_results)
            previous_result = result
            
            globalProcessedBlocks += 1
            if context:
                self.reportProgress(context, f"画像{i+1}のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)
        
        # 結果を返す
        results = []
        refDatetime = self._referenceData.headers.get('datetime', '')
        refDatetime = datetime.datetime.fromisoformat(refDatetime)
        for i, (inputData, result, method_results) in enumerate(zip(inputDatas, all_results, all_method_results_list)):
            imageId = self._generateImageId(inputData)
            dt = inputData.headers.get('datetime', '')
            time = (datetime.datetime.fromisoformat(dt) - refDatetime).total_seconds()
            result.time = time
            results.append({
                'image_id': imageId,
                'datetime': dt,
                'result'  : result,
                'methods' : method_results
            })
        
        return results
    
    def _generateImageId(self, flowData):
        """画像識別子を生成"""
        source_file = flowData.headers.get('source_file', '')
        datetime_str = flowData.headers.get('datetime', '')
        
        if source_file:
            return source_file
        elif datetime_str:
            return f"datetime_{datetime_str}"
        else:
            data_hash = hashlib.md5(str(flowData.headers).encode()).hexdigest()[:8]
            return f"hash_{data_hash}"
    
    def _selectDistributedStars(self, stars:np.ndarray, imageShape) -> tuple[np.ndarray, list[int]]:
        """画像全体に分散した星を選択"""
        if 0 == len(stars):
            return stars, []
        
        h, w = imageShape
        gridRows, gridCols = self.grid.rows, self.grid.cols
        
        # 各グリッド領域のサイズ
        cellH = h // gridRows
        cellW = w // gridCols
        
        distributedStars = []
        gridSelectedCounts = []
        
        # 各グリッドから最大 n 個の明るい星を選択
        for row in range(gridRows):
            for col in range(gridCols):
                yMin = row * cellH
                yEnd = (row + 1) * cellH if row < gridRows - 1 else h
                xMin = col * cellW
                xEnd = (col + 1) * cellW if col < gridCols - 1 else w
                
                # このグリッド内の星を抽出
                gridStars = [(x, y, br, ar) for x, y, br, ar in stars if xMin <= x < xEnd and yMin <= y < yEnd]
                
                # 明度順でソートして上位指定数を選択
                gridStars.sort(key=lambda x: x[2], reverse=True)
                selected = gridStars[:self.grid.starsPerGrid]
                distributedStars.extend(selected)
                gridSelectedCounts.append(len(selected))
        
        # 全体からも明るい星を追加（重複除去）
        maxTotalStars = gridRows * gridCols * self.grid.starsPerGrid + 20
        all_bright = sorted(stars, key=lambda x: x[2], reverse=True)
        for star in all_bright:
            if star not in distributedStars and len(distributedStars) < maxTotalStars:
                distributedStars.append(star)
        distributedStars = distributedStars[:maxTotalStars]
        
        return distributedStars, gridSelectedCounts
    
    def _findOffsetByStarDetection(self, refImage, targetImage, previous_result=None):
        """星点検出による天体写真用位置合わせ"""
        import numpy as np
        from utils import numpy_helpers as nh

        if previous_result is None:
            previous_result = AlignmentResult()
        
        extra_info = {}
        
        # 現在の画像サイズを保存（_calculateAffineTransformで使用）
        currentImageShape = refImage.shape
        
        # RANSAC用固定シードを設定
        rng = np.random.default_rng(self.ransac.seed)
        extra_info["star_ransac_seed"] = self.ransac.seed
        
        # 星点を検出（基準画像の星はキャッシュから取得）
        if hasattr(self, '_cached_ref_stars') and self._cached_ref_stars:
            ref_stars = self._cached_ref_stars
        else:
            ref_stars = self._detectStars(refImage)
        target_stars = self._detectStars(targetImage)
        
        extra_info["ref_stars_count"] = len(ref_stars)
        extra_info["target_stars_count"] = len(target_stars)
        extra_info["target_stars_min_required"] = 3
        
        if len(ref_stars) < 3 or len(target_stars) < 3:
            return AlignmentResult(success=False, method="star", extra_info=extra_info)
        
        # 画像全体に分散した星を選択
        ref_bright,    ref_grid_counts    = self._selectDistributedStars(ref_stars, refImage.shape)
        target_bright, target_grid_counts = self._selectDistributedStars(target_stars, targetImage.shape)
        
        aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in target_bright])
        extra_info["ref_bright_count"]    = len(ref_bright)
        extra_info["ref_grid_counts"]     = ref_grid_counts
        extra_info["target_bright_count"] = len(target_bright)
        extra_info["target_grid_counts"]  = target_grid_counts
        extra_info["aspectRatioMedian"]   = aspectRatioMedian
        
        # 前画像のオフセット・回転を考慮した対応点探索
        matches = []
        radius_sq = self.ransac.sampleRadius ** 2  # 二乗距離で比較
        
        # NumPy配列化で高速化
        ref_array = nh.array([(rx, ry) for rx, ry, _, _ in ref_bright])
        target_array = nh.array([(tx, ty) for tx, ty, _, _ in target_bright])
        
        for i, (rx, ry, _, _) in enumerate(ref_bright):
            # 予測位置計算
            if self.usePreviousOffset:
                expected_pos = target_array + nh.array([previous_result.dx, previous_result.dy])
            else:
                expected_pos = target_array
            
            # 距離計算（二乗距離）
            dist_sq = np.sum((expected_pos - nh.array([rx, ry]))**2, axis=1)
            valid_indices = np.where(dist_sq < radius_sq)[0]
            
            # マッチを追加
            for j in valid_indices:
                tx, ty, brightness, aspectRatio = target_bright[j]
                matches.append(((rx, ry), (tx, ty), brightness, aspectRatio))
        
        aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in matches])
        extra_info["matches_count"] = len(matches)
        extra_info["matches_count_min_required"] = 5
        extra_info["aspectRatioMedian"] = aspectRatioMedian

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
                ref_pt, target_pt, _, _ = matches[idx]
                dx_sum += ref_pt[0] - target_pt[0]
                dy_sum += ref_pt[1] - target_pt[1]
            
            dx = dx_sum / len(sample)
            dy = dy_sum / len(sample)
            
            # インライアをカウント
            cur_inliers = 0
            for ref_pt, target_pt, _, _ in matches:
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
        grid_match_counts = self._calculateGridMatches(matches, offset, refImage.shape)
        extra_info["grid_match_counts"] = grid_match_counts
        
        # インライアを使って回転も含めた変換を計算
        inlier_matches = []
        for ref_pt, target_pt, brightness, aspectRatio  in matches:
            expected_x = target_pt[0] + offset[0]
            expected_y = target_pt[1] + offset[1]
            error = np.sqrt((ref_pt[0] - expected_x)**2 + (ref_pt[1] - expected_y)**2)
            if error < 2.0:
                inlier_matches.append((ref_pt, target_pt, brightness, aspectRatio))
        
        dx, dy = offset
        rotation = 0
        confidence = min(1.0, inliers / 20.0)  # 正規化した信頼度
        
        aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in inlier_matches])
        extra_info["aspectRatioMedian"] = aspectRatioMedian
        
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
        
        for ref_pt, target_pt, _, _ in matches:
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
