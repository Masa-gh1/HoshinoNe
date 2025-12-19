'''
ImageAlignmentNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import hashlib
import numpy as np
import tkinter as tk
from tkinter import messagebox, ttk
from base.NNBlockOperationNode import NNBlockOperationNode
from base.FlowData import FlowData
from base.DataBlock import DataBlock
from config import BLOCK_SIZE

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

class AlignmentResult:
    def __init__(self, dx=0, dy=0, rotation=0, confidence=0, method="", extra_info=None):
        self.dx = dx
        self.dy = dy
        self.rotation = rotation
        self.confidence = confidence
        self.method = method
        self.extra_info = extra_info or {}

class ImageAlignmentNode(NNBlockOperationNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "image_alignment", "画像位置合わせ")
        
        # 設定パラメータ
        # 基準画像選択
        self.referenceIndex = 0  # 基準画像のインデックス
        self.usePreviousOffset = True  # 前回画像のズレを考慮する
        # オフセット計算
        self.alignmentPlane = 1  # 位置合わせ用プレーン（0:R, 1:G, 2:B）
        # オフセット計算 優先順位1: 星点検出法
        self.starThreshold = 95  # 星検出閾値（%）
        self.starMinDiameter = 2  # 星最小直径（ピクセル）
        self.starMaxDiameter = 16  # 星最大直径（ピクセル）
        self.gridRows = 3  # グリッド行数
        self.gridCols = 3  # グリッド列数
        self.starsPerGrid = 8  # グリッド当たりの選択星数
        self.starSampleRadius = 100  # 星サンプル半径（ピクセル）
        self.ransacIterations = 100  # RANSAC試行回数
        # オフセット計算 優先順位2: 位相相関法
        self.phaseCorrelationMaxOffset = 100  # 位相相関最大オフセット（ピクセル）
        # オフセット計算 優先順位3: テンプレートマッチング法
        self.templateSearchRange = 150  # テンプレート検索範囲（ピクセル）
        # 拡張領域計算
        # 位置合わせ実行
        # 余白処理
        self.cropMode = "none"  # 余白処理: "none", "common", "fill"
        
        self.lastConfigHash = None
        
        if not CV2_AVAILABLE:
            messagebox.showerror(f"{self.text} エラー", "OpenCVライブラリがインストールされていません。\npip install opencv-python でインストールしてください。")
            return
    
    def getColor(self):
        return self._color_op
    
    def updateNodeText(self):
        displayText = f"{self.text}\n基準: {self.referenceIndex + 1}"
        self.editor.updateNodeText(self, displayText)
        
        newHash = self.getConfigHash()
        if newHash != self.lastConfigHash:
            self.lastConfigHash = newHash
            if hasattr(self.editor, 'onNodeConfigChanged'):
                self.editor.onNodeConfigChanged(self)
    
    def store(self, nodeData):
        nodeData["referenceIndex"] = self.referenceIndex
        nodeData["gridRows"] = self.gridRows
        nodeData["gridCols"] = self.gridCols
        nodeData["starsPerGrid"] = self.starsPerGrid
        nodeData["alignmentPlane"] = self.alignmentPlane
        nodeData["starThreshold"] = self.starThreshold
        nodeData["phaseCorrelationMaxOffset"] = self.phaseCorrelationMaxOffset
        nodeData["starSampleRadius"] = self.starSampleRadius
        nodeData["starMinDiameter"] = self.starMinDiameter
        nodeData["starMaxDiameter"] = self.starMaxDiameter
        nodeData["templateSearchRange"] = self.templateSearchRange
        nodeData["ransacIterations"] = self.ransacIterations
        nodeData["usePreviousOffset"] = self.usePreviousOffset
    
    def restore(self, nodeData):
        if "referenceIndex" in nodeData:
            self.referenceIndex = nodeData["referenceIndex"]
        if "gridRows" in nodeData:
            self.gridRows = nodeData["gridRows"]
        if "gridCols" in nodeData:
            self.gridCols = nodeData["gridCols"]
        if "starsPerGrid" in nodeData:
            self.starsPerGrid = nodeData["starsPerGrid"]
        if "alignmentPlane" in nodeData:
            self.alignmentPlane = nodeData["alignmentPlane"]
        if "starThreshold" in nodeData:
            self.starThreshold = nodeData["starThreshold"]
        if "phaseCorrelationMaxOffset" in nodeData:
            self.phaseCorrelationMaxOffset = nodeData["phaseCorrelationMaxOffset"]
        if "starSampleRadius" in nodeData:
            self.starSampleRadius = nodeData["starSampleRadius"]
        if "starMinDiameter" in nodeData:
            self.starMinDiameter = nodeData["starMinDiameter"]
        if "starMaxDiameter" in nodeData:
            self.starMaxDiameter = nodeData["starMaxDiameter"]
        if "templateSearchRange" in nodeData:
            self.templateSearchRange = nodeData["templateSearchRange"]
        if "ransacIterations" in nodeData:
            self.ransacIterations = nodeData["ransacIterations"]
        if "usePreviousOffset" in nodeData:
            self.usePreviousOffset = nodeData["usePreviousOffset"]
        self.updateNodeText()
    
    def preprocessInputs(self, inputDatas):
        """入力データの前処理：基準画像を決定"""
        if not inputDatas:
            return []
        
        # 基準画像のインデックスを調整
        if self.referenceIndex >= len(inputDatas):
            self.referenceIndex = 0
        
        return inputDatas
    
    def processBlock(self, block):
        """ブロック単位での位置合わせ処理"""
        if block is None:
            return None
        
        # 現在の実装では、全画像を一度に処理する必要があるため
        # ブロック処理は後の段階で実装
        return block
    
    def process(self, context=None):
        """画像位置合わせのメイン処理"""
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputDatas = []
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        if len(inputDatas) < 2:
            messagebox.showwarning("警告", "位置合わせには2枚以上の画像が必要です")
            self.flowDatas = inputDatas
            return
        
        # 基準画像を決定
        if self.referenceIndex >= len(inputDatas):
            self.referenceIndex = 0
        
        referenceData = inputDatas[self.referenceIndex]
        
        # 結果データを初期化
        resultFlowDatas = []
        
        # 全画像の総ブロック数を仮計算（ズレ計算も含む）
        width, height = referenceData.getDimensions()
        planeCount = inputDatas[0].getPlaneCount() if hasattr(inputDatas[0], 'getPlaneCount') else 1
        # 拡張サイズは仮で計算（後で更新）
        blocksPerImage = planeCount * ((width + BLOCK_SIZE - 1) // BLOCK_SIZE) * ((height + BLOCK_SIZE - 1) // BLOCK_SIZE)
        offsetCalculationBlocks = 1 + 2*(len(inputDatas) - 1)  # 基準画像処理(1) + 各非基準画像のズレ計算(2回ずつ)
        totalGlobalBlocks = len(inputDatas) * blocksPerImage + offsetCalculationBlocks
        globalProcessedBlocks = 0
        
        # 基準画像を一度だけ処理
        if context:
            self.reportProgress(context, "基準画像処理中", globalProcessedBlocks, totalGlobalBlocks)
        refGray = self._flowDataToImage(referenceData, planeIndex=self.alignmentPlane, normalize_for_detection=True)
        
        # 全オフセットと位置合わせ情報を収集
        all_results = []
        previous_result = AlignmentResult()  # 前画像の結果
        
        globalProcessedBlocks += 1
        if context:
            self.reportProgress(context, f"画像1のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)
        
        for i, inputData in enumerate(inputDatas):
            if i != self.referenceIndex:
                targetGray = self._flowDataToImage(inputData, planeIndex=self.alignmentPlane, normalize_for_detection=True)
                globalProcessedBlocks += 1
                if context:
                    self.reportProgress(context, f"画像{i+1}のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)

                result = self._findOffsetByStarDetection(refGray, targetGray, previous_result)
                if result is None:
                    result = self._findOffsetByPhaseCorrelation(refGray, targetGray, previous_result)
                    if result is None:
                        result = self._findOffsetByTemplateMatching(refGray, targetGray, previous_result)
                
                if result is None:
                    result = AlignmentResult()
                
                all_results.append(result)
                previous_result = result
                
                globalProcessedBlocks += 1
                if context:
                    self.reportProgress(context, f"画像{i+1}のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)
            else:
                all_results.append(AlignmentResult())
        
        # 拡張領域を計算
        min_dx = min(result.dx for result in all_results)
        min_dy = min(result.dy for result in all_results)
        max_dx = max(result.dx for result in all_results)
        max_dy = max(result.dy for result in all_results)
        
        # 元画像サイズ
        width, height = referenceData.getDimensions()
        
        # 拡張サイズを計算
        expand_left = int(max(0, -min_dx))
        expand_top = int(max(0, -min_dy))
        expand_right = int(max(0, max_dx))
        expand_bottom = int(max(0, max_dy))
        
        new_width = int(width + expand_left + expand_right)
        new_height = int(height + expand_top + expand_bottom)
        
        # 総ブロック数を正確なサイズで再計算
        blocksPerImage = planeCount * ((new_width + BLOCK_SIZE - 1) // BLOCK_SIZE) * ((new_height + BLOCK_SIZE - 1) // BLOCK_SIZE)
        totalGlobalBlocks = len(inputDatas) * blocksPerImage + offsetCalculationBlocks
        
        # 各画像を処理
        for i, inputData in enumerate(inputDatas):
            if i == self.referenceIndex:
                # 基準画像を拡張領域に配置
                expandedData = self._expandFlowData(inputData, expand_left, expand_top, new_width, new_height, context, [globalProcessedBlocks, totalGlobalBlocks])
                globalProcessedBlocks += blocksPerImage
                # 基準画像の情報を追加
                expandedData.headers['grid'] = {'columns': self.gridCols, 'rows': self.gridRows}
                expandedData.headers['grid_selection_counts'] = [0] * (self.gridCols * self.gridRows)
                expandedData.headers['grid_match_counts'] = [0] * (self.gridCols * self.gridRows)
                expandedData.headers['reference_image_movement'] = {'dx': 0, 'dy': 0, 'rotation': 0}
                resultFlowDatas.append(expandedData)
            else:
                # 位置合わせを実行
                result = all_results[i]
                alignedData = self._alignImageWithExpansion(inputData, int(result.dx + expand_left), int(result.dy + expand_top), new_width, new_height, context, [globalProcessedBlocks, totalGlobalBlocks])
                globalProcessedBlocks += blocksPerImage
                
                # 位置合わせ情報をheadersに追加
                alignedData.headers['grid'] = {'columns': self.gridCols, 'rows': self.gridRows}
                if result.extra_info:
                    alignedData.headers['grid_selection_counts'] = result.extra_info.get('grid_selected', [0] * (self.gridCols * self.gridRows))
                    alignedData.headers['grid_match_counts'] = result.extra_info.get('grid_matched', [0] * (self.gridCols * self.gridRows))
                else:
                    alignedData.headers['grid_selection_counts'] = [0] * (self.gridCols * self.gridRows)
                    alignedData.headers['grid_match_counts'] = [0] * (self.gridCols * self.gridRows)
                
                alignedData.headers['reference_image_movement'] = {'dx': result.dx, 'dy': result.dy, 'rotation': result.rotation}
                
                resultFlowDatas.append(alignedData)
        
        # 余白処理を適用
        if self.cropMode == "common":
            resultFlowDatas = self._cropToCommonArea(resultFlowDatas)
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def _findOffsetByTemplateMatching(self, refImage, targetImage, previous_result=None):
        """テンプレートマッチングでオフセットを検出"""
        if previous_result is None:
            previous_result = AlignmentResult()
        
        h, w = refImage.shape
        
        # 中央部分をテンプレートとして使用
        template_size = min(h, w) // 4
        center_y, center_x = h // 2, w // 2
        y1 = center_y - template_size // 2
        y2 = center_y + template_size // 2
        x1 = center_x - template_size // 2
        x2 = center_x + template_size // 2
        
        template = refImage[y1:y2, x1:x2]
        
        # 前画像のオフセットを中心とした検索範囲
        search_range = self.templateSearchRange  # 前画像位置からの検索範囲
        
        if self.usePreviousOffset:
            # 検索中心を前画像位置に設定
            search_center_x = x1 + previous_result.dx
            search_center_y = y1 + previous_result.dy
        else:
            # 検索中心をテンプレート中心に設定
            search_center_x = x1
            search_center_y = y1
        
        search_y1 = max(0, int(search_center_y - search_range))
        search_y2 = min(h, int(search_center_y + search_range))
        search_x1 = max(0, int(search_center_x - search_range))
        search_x2 = min(w, int(search_center_x + search_range))
        
        search_area = targetImage[search_y1:search_y2, search_x1:search_x2]
        
        # テンプレートマッチング
        result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val < 0.3:
            return None
        
        # オフセットを計算
        match_x, match_y = max_loc
        actual_x = search_x1 + match_x
        actual_y = search_y1 + match_y
        
        dx = actual_x - x1
        dy = actual_y - y1
        
        return AlignmentResult(dx=dx, dy=dy, confidence=max_val, method="template")
    
    def _findOffsetByPhaseCorrelation(self, refImage, targetImage, previous_result=None):
        """位相相関法でオフセットを検出"""
        if previous_result is None:
            previous_result = AlignmentResult()
        
        max_offset = self.phaseCorrelationMaxOffset
        # エッジ強化で特徴を明確化
        ref_edges = cv2.Laplacian(refImage, cv2.CV_64F)
        target_edges = cv2.Laplacian(targetImage, cv2.CV_64F)
        
        # エッジと元画像を組み合わせ
        ref_combined = 0.7 * refImage.astype(np.float64) + 0.3 * np.abs(ref_edges)
        target_combined = 0.7 * targetImage.astype(np.float64) + 0.3 * np.abs(target_edges)
        
        # コントラスト正規化
        ref_combined = (ref_combined - ref_combined.mean()) / (ref_combined.std() + 1e-10)
        target_combined = (target_combined - target_combined.mean()) / (target_combined.std() + 1e-10)
        
        # ウィンドウ関数を適用
        h, w = ref_combined.shape
        window_y = np.hanning(h).reshape(-1, 1)
        window_x = np.hanning(w).reshape(1, -1)
        window = window_y * window_x
        
        ref_windowed = ref_combined * window
        target_windowed = target_combined * window
        
        # FFTで位相相関を計算
        f_ref = np.fft.fft2(ref_windowed)
        f_target = np.fft.fft2(target_windowed)
        
        # 位相相関を計算
        cross_power_spectrum = f_ref * np.conj(f_target)
        magnitude = np.abs(cross_power_spectrum)
        magnitude[magnitude < 1e-10] = 1e-10
        cross_power_spectrum = cross_power_spectrum / magnitude
        
        correlation = np.fft.ifft2(cross_power_spectrum)
        correlation = np.abs(correlation)
        
        # FFTシフトして中央にピークを移動
        correlation = np.fft.fftshift(correlation)
        
        # ピークを検出
        peak_y, peak_x = np.unravel_index(np.argmax(correlation), correlation.shape)
        
        # 中央からのオフセットを計算
        center_y, center_x = h // 2, w // 2
        dy = peak_y - center_y
        dx = peak_x - center_x
        
        # 高精度サブピクセル推定
        if 2 <= peak_x < correlation.shape[1] - 2 and 2 <= peak_y < correlation.shape[0] - 2:
            # 5点フィッティングでより高精度に
            x_vals = np.array([-2, -1, 0, 1, 2])
            y_vals = np.array([-2, -1, 0, 1, 2])
            
            x_corr = correlation[peak_y, peak_x-2:peak_x+3]
            y_corr = correlation[peak_y-2:peak_y+3, peak_x]
            
            # 重心計算でサブピクセル推定
            if np.sum(x_corr) > 0:
                dx_sub = np.sum(x_vals * x_corr) / np.sum(x_corr)
                if abs(dx_sub) < 2.0:
                    dx += dx_sub
            
            if np.sum(y_corr) > 0:
                dy_sub = np.sum(y_vals * y_corr) / np.sum(y_corr)
                if abs(dy_sub) < 2.0:
                    dy += dy_sub
        
        # 信頼性評価
        max_corr = np.max(correlation)
        mean_corr = np.mean(correlation)
        std_corr = np.std(correlation)
        
        # ピークの銕さを評価
        peak_sharpness = max_corr / (mean_corr + std_corr)
        
        if self.usePreviousOffset:
            # ピークの鋭さと前画像位置からの距離をチェック
            distance_from_prev = np.sqrt((dx - previous_result.dx)**2 + (dy - previous_result.dy)**2)
            if peak_sharpness < 1.5 or distance_from_prev > max_offset:
                return None
        else:
            # ピークの鋭さのみで判定
            if peak_sharpness < 1.5:
                return None
        
        confidence = min(1.0, peak_sharpness / 10.0)  # 正規化した信頼度
        return AlignmentResult(dx=dx, dy=dy, confidence=confidence, method="phase")
    
    def _findOffsetByStarDetection(self, refImage, targetImage, previous_result=None):
        """星点検出による天体写真用位置合わせ"""
        if previous_result is None:
            previous_result = AlignmentResult()
        # 星点を検出
        ref_stars = self._detectStars(refImage)
        target_stars = self._detectStars(targetImage)
        
        if len(ref_stars) < 3 or len(target_stars) < 3:
            return None
        
        # 画像全体に分散した星を選択
        ref_bright, ref_grid_counts = self._selectDistributedStars(ref_stars, refImage.shape)
        target_bright, target_grid_counts = self._selectDistributedStars(target_stars, targetImage.shape)
        
        # 前画像のオフセット・回転を考慮した対応点探索
        matches = []
        for i, (rx, ry, _) in enumerate(ref_bright):
            for j, (tx, ty, _) in enumerate(target_bright):
                if self.usePreviousOffset:
                    # 前画像位置からの予測位置を計算
                    expected_tx = tx + previous_result.dx
                    expected_ty = ty + previous_result.dy
                else:
                    # 前回ズレを考慮しない
                    expected_tx = tx
                    expected_ty = ty
                
                # 前画像の回転も考慮（簡易回転補正）
                if abs(previous_result.rotation) > 0.1:  # 0.1度以上の回転がある場合
                    angle_rad = np.radians(previous_result.rotation)
                    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
                    cx, cy = refImage.shape[1] // 2, refImage.shape[0] // 2
                    # 回転中心からの相対位置
                    rel_x, rel_y = tx - cx, ty - cy
                    # 回転適用
                    rot_x = rel_x * cos_a - rel_y * sin_a
                    rot_y = rel_x * sin_a + rel_y * cos_a
                    expected_tx = rot_x + cx + previous_result.dx
                    expected_ty = rot_y + cy + previous_result.dy
                
                # 予測位置との距離をチェック
                dist = np.sqrt((rx - expected_tx)**2 + (ry - expected_ty)**2)
                if dist < self.starSampleRadius:  # 設定値ピクセル以内
                    matches.append(((rx, ry), (tx, ty)))
        
        if len(matches) < 5:
            return None
        
        # RANSACでロバストなオフセットを計算
        best_offset = None
        best_inliers = 0
        
        for _ in range(self.ransacIterations):  # RANSAC試行回数
            # ランダムに3点選択
            sample = np.random.choice(len(matches), min(3, len(matches)), replace=False)
            
            # オフセットを計算（基準画像に向かって対象画像を動かす方向）
            dx_sum, dy_sum = 0, 0
            for idx in sample:
                ref_pt, target_pt = matches[idx]
                dx_sum += ref_pt[0] - target_pt[0]
                dy_sum += ref_pt[1] - target_pt[1]
            
            dx = dx_sum / len(sample)
            dy = dy_sum / len(sample)
            
            # インライアをカウント
            inliers = 0
            for ref_pt, target_pt in matches:
                expected_x = target_pt[0] + dx
                expected_y = target_pt[1] + dy
                error = np.sqrt((ref_pt[0] - expected_x)**2 + (ref_pt[1] - expected_y)**2)
                if error < 1.5:  # 1.5ピクセル以内
                    inliers += 1
            
            if inliers > best_inliers:
                best_inliers = inliers
                best_offset = (dx, dy)
        
        if best_inliers >= 5:  # 5個以上のインライア
            # グリッド別マッチ数を計算
            grid_match_counts = self._calculateGridMatches(matches, best_offset, refImage.shape)
            
            # インライアを使って回転も含めた変換を計算
            inlier_matches = []
            for ref_pt, target_pt in matches:
                expected_x = target_pt[0] + best_offset[0]
                expected_y = target_pt[1] + best_offset[1]
                error = np.sqrt((ref_pt[0] - expected_x)**2 + (ref_pt[1] - expected_y)**2)
                if error < 2.0:
                    inlier_matches.append((ref_pt, target_pt))
            
            dx, dy = best_offset
            rotation = 0
            confidence = min(1.0, best_inliers / 20.0)  # 正規化した信頼度
            
            if len(inlier_matches) >= 3:
                transform_result = self._calculateAffineTransform(inlier_matches)
                if isinstance(transform_result, tuple):
                    dx, dy = transform_result
                else:
                    dx, dy = transform_result[0, 2], transform_result[1, 2]
                    rotation = np.arctan2(transform_result[1, 0], transform_result[0, 0]) * 180 / np.pi
            
            extra_info = {
                'grid_selected': ref_grid_counts,
                'grid_matched': grid_match_counts
            }
            
            return AlignmentResult(dx=dx, dy=dy, rotation=rotation, confidence=confidence, method="star", extra_info=extra_info)
        
        return None
    
    def _calculateAffineTransform(self, matches):
        """対応点からアフィン変換を計算"""
        ref_pts = np.array([match[0] for match in matches], dtype=np.float32)
        target_pts = np.array([match[1] for match in matches], dtype=np.float32)
        
        # アフィン変換行列を計算
        M = cv2.estimateAffinePartial2D(target_pts, ref_pts, method=cv2.RANSAC, 
                                        ransacReprojThreshold=2.0)[0]
        
        if M is not None:
            # 平行移動成分を抽出
            dx, dy = M[0, 2], M[1, 2]
            
            # 回転角を計算
            rotation_angle = np.arctan2(M[1, 0], M[0, 0]) * 180 / np.pi
            

            
            # 小さな回転のみ適用（天体写真では通常数度以内）
            if abs(rotation_angle) < 10.0:
                return M
            else:
                # 大きな回転は平行移動のみ適用
                return (dx, dy)
        
        # アフィン変換が失敗した場合は平行移動のみ
        dx_sum = sum(ref_pt[0] - target_pt[0] for ref_pt, target_pt in matches)
        dy_sum = sum(ref_pt[1] - target_pt[1] for ref_pt, target_pt in matches)
        return (dx_sum / len(matches), dy_sum / len(matches))
    
    def _calculateGridMatches(self, matches, offset, image_shape):
        """グリッド別のマッチ数を計算"""
        h, w = image_shape
        grid_rows, grid_cols = self.gridRows, self.gridCols
        cell_h = h // grid_rows
        cell_w = w // grid_cols
        
        grid_match_counts = [0] * (grid_rows * grid_cols)
        
        for ref_pt, target_pt in matches:
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
    
    def _cropToCommonArea(self, flowDatas):
        """全画像の共通領域を計算してクロップ"""
        if not flowDatas:
            return flowDatas
        
        # 各画像の有効領域を計算
        valid_regions = []
        for flowData in flowDatas:
            width, height = flowData.getDimensions()
            # 黒い部分とNaN値（余白）を除いた有効領域を検出
            image = self._flowDataToImage(flowData, planeIndex=0)
            mask = (image > 0) & ~np.isnan(image)
            
            if np.any(mask):
                coords = np.where(mask)
                y_min, y_max = coords[0].min(), coords[0].max()
                x_min, x_max = coords[1].min(), coords[1].max()
                valid_regions.append((x_min, y_min, x_max, y_max))
            else:
                valid_regions.append((0, 0, width-1, height-1))
        
        # 共通領域を計算
        x_min = max(region[0] for region in valid_regions)
        y_min = max(region[1] for region in valid_regions)
        x_max = min(region[2] for region in valid_regions)
        y_max = min(region[3] for region in valid_regions)
        
        if x_min >= x_max or y_min >= y_max:
            return flowDatas  # 共通領域がない場合はそのまま
        
        # 各画像をクロップ
        cropped_datas = []
        for flowData in flowDatas:
            cropped_data = self._cropFlowData(flowData, x_min, y_min, x_max, y_max)
            cropped_datas.append(cropped_data)
        

        return cropped_datas
    
    def _cropFlowData(self, flowData, x_min, y_min, x_max, y_max):
        """指定範囲でFlowDataをクロップ"""
        
        crop_width = x_max - x_min + 1
        crop_height = y_max - y_min + 1
        
        headers = flowData.headers.copy() if flowData.headers else {}
        cropped_data = FlowData(headers)
        cropped_data.setDimensions(crop_width, crop_height)
        
        planeCount = flowData.getPlaneCount() if hasattr(flowData, 'getPlaneCount') else 1
        
        for planeIndex in range(planeCount):
            plane_image = self._flowDataToImage(flowData, planeIndex)
            cropped_plane = plane_image[y_min:y_max+1, x_min:x_max+1]
            
            for y in range(0, crop_height, BLOCK_SIZE):
                for x in range(0, crop_width, BLOCK_SIZE):
                    blockHeight = min(BLOCK_SIZE, crop_height - y)
                    blockWidth = min(BLOCK_SIZE, crop_width - x)
                    
                    blockData = cropped_plane[y:y+blockHeight, x:x+blockWidth]
                    block = DataBlock(planeIndex, x, y, blockData)
                    cropped_data.setBlock(block)
        
        return cropped_data
    
    def _expandFlowData(self, flowData, offset_x, offset_y, new_width, new_height, context=None, globalProgress=None):
        """拡張領域にFlowDataを配置"""
        
        headers = flowData.headers.copy() if flowData.headers else {}
        expanded_data = FlowData(headers)
        expanded_data.setDimensions(new_width, new_height)
        
        planeCount = flowData.getPlaneCount() if hasattr(flowData, 'getPlaneCount') else 1
        
        for planeIndex in range(planeCount):
            # 元画像を取得
            original_image = self._flowDataToImage(flowData, planeIndex)
            
            # 拡張領域に配置（余白はNaN）
            expanded_image = np.full((new_height, new_width), np.nan, dtype=np.float64)
            h, w = original_image.shape
            expanded_image[offset_y:offset_y+h, offset_x:offset_x+w] = original_image.astype(np.float64)
            
            # ブロック化
            for y in range(0, new_height, BLOCK_SIZE):
                for x in range(0, new_width, BLOCK_SIZE):
                    blockHeight = min(BLOCK_SIZE, new_height - y)
                    blockWidth = min(BLOCK_SIZE, new_width - x)
                    
                    blockData = expanded_image[y:y+blockHeight, x:x+blockWidth]
                    block = DataBlock(planeIndex, x, y, blockData)
                    expanded_data.setBlock(block)
                    
                    if context and globalProgress:
                        globalProgress[0] += 1
                        if globalProgress[0] % 10 == 0:
                            self.reportProgress(context, "拡張処理中", globalProgress[0], globalProgress[1])
        
        return expanded_data
    
    def _alignImageWithExpansion(self, flowData, dx, dy, new_width, new_height, context=None, globalProgress=None):
        """拡張領域で位置合わせを実行"""
        
        headers = flowData.headers.copy() if flowData.headers else {}
        aligned_data = FlowData(headers)
        aligned_data.setDimensions(new_width, new_height)
        
        planeCount = flowData.getPlaneCount() if hasattr(flowData, 'getPlaneCount') else 1
        
        for planeIndex in range(planeCount):
            # 元画像を取得
            original_image = self._flowDataToImage(flowData, planeIndex)
            
            # 平行移動行列を作成
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            
            # 拡張領域で変換（余白はNaN）
            temp_image = cv2.warpAffine(original_image.astype(np.float64), M, (new_width, new_height))
            aligned_image = np.where(temp_image == 0, np.nan, temp_image)
            
            # ブロック化
            for y in range(0, new_height, BLOCK_SIZE):
                for x in range(0, new_width, BLOCK_SIZE):
                    blockHeight = min(BLOCK_SIZE, new_height - y)
                    blockWidth = min(BLOCK_SIZE, new_width - x)
                    
                    blockData = aligned_image[y:y+blockHeight, x:x+blockWidth]
                    block = DataBlock(planeIndex, x, y, blockData)
                    aligned_data.setBlock(block)
                    
                    if context and globalProgress:
                        globalProgress[0] += 1
                        if globalProgress[0] % 10 == 0:
                            self.reportProgress(context, "位置合わせ中", globalProgress[0], globalProgress[1])
        
        return aligned_data
    
    def _detectStars(self, image):
        """画像から星点を検出"""
        # ガウシアンブラーでノイズ除去
        blurred = cv2.GaussianBlur(image, (3, 3), 0)
        
        # メディアンフィルタでバックグラウンドを推定
        background = cv2.medianBlur(blurred, 51)
        
        # バックグラウンドを減算
        subtracted = cv2.subtract(blurred, background)
        
        # 閾値処理で星を抽出
        threshold = np.nanpercentile(subtracted[subtracted > 0], self.starThreshold)
        _, binary = cv2.threshold(subtracted, threshold, 255, cv2.THRESH_BINARY)
        
        # 連結成分で星点を検出
        contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        stars = []
        max_val = np.nanmax(image)
        saturation_threshold = max_val * 0.95
        
        # 直径から面積へ変換
        min_area = np.pi * (self.starMinDiameter / 2) ** 2
        max_area = np.pi * (self.starMaxDiameter / 2) ** 2
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area <= area <= max_area:  # 星直径閾値
                # 重心を計算
                M = cv2.moments(contour)
                if M['m00'] > 0:
                    cx = M['m10'] / M['m00']
                    cy = M['m01'] / M['m00']
                    
                    # その点の明度を取得
                    x, y = int(cx), int(cy)
                    if 0 <= x < subtracted.shape[1] and 0 <= y < subtracted.shape[0]:
                        brightness = float(subtracted[y, x])
                        # 白跳びしている恒星を除外
                        original_brightness = float(image[y, x]) if 0 <= x < image.shape[1] and 0 <= y < image.shape[0] else 0
                        if brightness > 0 and original_brightness < saturation_threshold:
                            stars.append((cx, cy, brightness))
        
        return stars
    
    def _selectDistributedStars(self, stars, image_shape):
        """画像全体に分散した星を選択"""
        if len(stars) < 10:
            return stars, []
        
        h, w = image_shape
        grid_rows, grid_cols = self.gridRows, self.gridCols
        
        # 各グリッド領域のサイズ
        cell_h = h // grid_rows
        cell_w = w // grid_cols
        
        distributed_stars = []
        grid_selected_counts = []
        
        # 各グリッドから最大5個の明るい星を選択
        for row in range(grid_rows):
            for col in range(grid_cols):
                y_min = row * cell_h
                y_max = (row + 1) * cell_h if row < grid_rows - 1 else h
                x_min = col * cell_w
                x_max = (col + 1) * cell_w if col < grid_cols - 1 else w
                
                # このグリッド内の星を抽出
                grid_stars = []
                for x, y, brightness in stars:
                    if x_min <= x < x_max and y_min <= y < y_max:
                        grid_stars.append((x, y, brightness))
                
                # 明度順でソートして上位指定数を選択
                selected_count = 0
                if grid_stars:
                    grid_stars.sort(key=lambda x: x[2], reverse=True)
                    selected = grid_stars[:self.starsPerGrid]
                    distributed_stars.extend(selected)
                    selected_count = len(selected)
                
                grid_selected_counts.append(selected_count)
        
        # 全体からも明るい星を追加（重複除去）
        max_total_stars = grid_rows * grid_cols * self.starsPerGrid + 20
        all_bright = sorted(stars, key=lambda x: x[2], reverse=True)
        for star in all_bright:
            if star not in distributed_stars and len(distributed_stars) < max_total_stars:
                distributed_stars.append(star)
        

        return distributed_stars[:max_total_stars], grid_selected_counts
    
    def _flowDataToImage(self, flowData, planeIndex=None, normalize_for_detection=False):
        """FlowDataから画像配列を構築"""
        width, height = flowData.getDimensions()
        
        if planeIndex is not None:
            # 特定プレーンのみを使用（RAW画像対応）
            image = np.zeros((height, width), dtype=np.float32)
            for block in flowData.iterateBlocks():
                if block and block.planeIndex == planeIndex:
                    y1, y2 = block.y, block.y + block.getHeight()
                    x1, x2 = block.x, block.x + block.getWidth()
                    if len(block.data.shape) == 3:
                        image[y1:y2, x1:x2] = block.data[:, :, 0].astype(np.float32)
                    else:
                        image[y1:y2, x1:x2] = block.data.astype(np.float32)
            
            # 星検出用の正規化処理
            if normalize_for_detection and np.nanmax(image) > 255:
                # RAW画像の正規化（より穏健な手法）
                mean_val = np.mean(image)
                std_val = np.std(image)
                image = (image - mean_val) / std_val
                image = np.clip((image + 3) / 6 * 255, 0, 255)
                image = image.astype(np.uint8)
            # それ以外は入力値域を維持
        else:
            # 全プレーンを使用（従来の動作）
            firstBlock = next(flowData.iterateBlocks())
            if firstBlock and len(firstBlock.data.shape) == 3:
                channels = firstBlock.data.shape[2]
                image = np.zeros((height, width, channels), dtype=np.uint8)
            else:
                image = np.zeros((height, width), dtype=np.uint8)
            
            for block in flowData.iterateBlocks():
                if block:
                    y1, y2 = block.y, block.y + block.getHeight()
                    x1, x2 = block.x, block.x + block.getWidth()
                    image[y1:y2, x1:x2] = block.data
        
        return image
    
    def onEdit(self):
        return ImageAlignmentSettingsDialog(self.editor.root, self)
    
    def getConfigHash(self):
        config = f"{self.referenceIndex}_{self.gridRows}_{self.gridCols}_{self.starsPerGrid}_{self.alignmentPlane}_{self.starThreshold}_{self.cropMode}_{self.phaseCorrelationMaxOffset}_{self.starSampleRadius}_{self.starMinDiameter}_{self.starMaxDiameter}_{self.templateSearchRange}_{self.ransacIterations}_{self.usePreviousOffset}"
        return hashlib.md5(config.encode()).hexdigest()

class ImageAlignmentSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.text}設定")
        self.geometry("450x650")
        
        self.createWidgets()
        
    def createWidgets(self):
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 基準画像選択
        tk.Label(mainFrame, text="■ 基準画像選択", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5,2))
        refFrame = tk.Frame(mainFrame)
        refFrame.pack(fill=tk.X, pady=2)
        tk.Label(refFrame, text="基準画像:").pack(side=tk.LEFT)
        self.refEntry = tk.Entry(refFrame, width=10)
        self.refEntry.insert(0, str(self.node.referenceIndex + 1))
        self.refEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(refFrame, text="番目 (基準となる画像)").pack(side=tk.LEFT)
        
        # 前回ズレ考慮機能
        prevOffsetFrame = tk.Frame(mainFrame)
        prevOffsetFrame.pack(fill=tk.X, pady=2)
        self.usePrevOffsetVar = tk.BooleanVar(value=self.node.usePreviousOffset)
        tk.Checkbutton(prevOffsetFrame, text="前回画像のズレを考慮する", variable=self.usePrevOffsetVar).pack(side=tk.LEFT)
        tk.Label(prevOffsetFrame, text="(検索範囲の中央を前回位置に設定)").pack(side=tk.LEFT, padx=5)
        
        # オフセット計算
        tk.Label(mainFrame, text="■ オフセット計算", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        
        # 位置合わせ用プレーン
        planeFrame = tk.Frame(mainFrame)
        planeFrame.pack(fill=tk.X, pady=2)
        tk.Label(planeFrame, text="位置合わせプレーン:").pack(side=tk.LEFT)
        self.planeEntry = tk.Entry(planeFrame, width=5)
        self.planeEntry.insert(0, str(self.node.alignmentPlane))
        self.planeEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(planeFrame, text="(0:R, 1:G, 2:B, 位置検出用)").pack(side=tk.LEFT)
        
        # 優先順位1: 星点検出法
        tk.Label(mainFrame, text="  □ 優先順位1: 星点検出法", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8,2))
        
        # 星検出閾値
        thresholdFrame = tk.Frame(mainFrame)
        thresholdFrame.pack(fill=tk.X, pady=2)
        tk.Label(thresholdFrame, text="    星検出閾値:").pack(side=tk.LEFT)
        self.thresholdEntry = tk.Entry(thresholdFrame, width=5)
        self.thresholdEntry.insert(0, str(self.node.starThreshold))
        self.thresholdEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(thresholdFrame, text="% (上位%の明るい星を選択)").pack(side=tk.LEFT)
        
        # 星直径閾値
        starSizeFrame = tk.Frame(mainFrame)
        starSizeFrame.pack(fill=tk.X, pady=2)
        tk.Label(starSizeFrame, text="    星直径閾値:").pack(side=tk.LEFT)
        self.starMinDiameterEntry = tk.Entry(starSizeFrame, width=5)
        self.starMinDiameterEntry.insert(0, str(self.node.starMinDiameter))
        self.starMinDiameterEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(starSizeFrame, text="~").pack(side=tk.LEFT)
        self.starMaxDiameterEntry = tk.Entry(starSizeFrame, width=5)
        self.starMaxDiameterEntry.insert(0, str(self.node.starMaxDiameter))
        self.starMaxDiameterEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(starSizeFrame, text="px (検出対象の星直径)").pack(side=tk.LEFT)
        
        # グリッド設定
        gridFrame = tk.Frame(mainFrame)
        gridFrame.pack(fill=tk.X, pady=2)
        tk.Label(gridFrame, text="    グリッド:").pack(side=tk.LEFT)
        self.gridRowsEntry = tk.Entry(gridFrame, width=5)
        self.gridRowsEntry.insert(0, str(self.node.gridRows))
        self.gridRowsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="x").pack(side=tk.LEFT)
        self.gridColsEntry = tk.Entry(gridFrame, width=5)
        self.gridColsEntry.insert(0, str(self.node.gridCols))
        self.gridColsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="(星選択用分割数)").pack(side=tk.LEFT)
        
        # グリッド当たりの選択星数
        starsFrame = tk.Frame(mainFrame)
        starsFrame.pack(fill=tk.X, pady=2)
        tk.Label(starsFrame, text="    グリッド当たり星数:").pack(side=tk.LEFT)
        self.starsEntry = tk.Entry(starsFrame, width=10)
        self.starsEntry.insert(0, str(self.node.starsPerGrid))
        self.starsEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから選ぶ星数)").pack(side=tk.LEFT)
        
        # 星サンプル半径
        starDistFrame = tk.Frame(mainFrame)
        starDistFrame.pack(fill=tk.X, pady=2)
        tk.Label(starDistFrame, text="    星サンプル半径:").pack(side=tk.LEFT)
        self.starDistEntry = tk.Entry(starDistFrame, width=5)
        self.starDistEntry.insert(0, str(self.node.starSampleRadius))
        self.starDistEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starDistFrame, text="px (統計処理用サンプル収集範囲)").pack(side=tk.LEFT)
        
        # RANSAC試行回数
        ransacFrame = tk.Frame(mainFrame)
        ransacFrame.pack(fill=tk.X, pady=2)
        tk.Label(ransacFrame, text="    RANSAC試行回数:").pack(side=tk.LEFT)
        self.ransacEntry = tk.Entry(ransacFrame, width=5)
        self.ransacEntry.insert(0, str(self.node.ransacIterations))
        self.ransacEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(ransacFrame, text="回 (外れ値耐性用繰り返し回数)").pack(side=tk.LEFT)
        
        # 優先順位2: 位相相関法
        tk.Label(mainFrame, text="  □ 優先順位2: 位相相関法", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8,2))
        
        # 位相相関最大オフセット
        phaseFrame = tk.Frame(mainFrame)
        phaseFrame.pack(fill=tk.X, pady=2)
        tk.Label(phaseFrame, text="    位相相関最大オフセット:").pack(side=tk.LEFT)
        self.phaseOffsetEntry = tk.Entry(phaseFrame, width=5)
        self.phaseOffsetEntry.insert(0, str(self.node.phaseCorrelationMaxOffset))
        self.phaseOffsetEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(phaseFrame, text="px (FFT位置合わせ上限)").pack(side=tk.LEFT)
        
        # 優先順位3: テンプレートマッチング法
        tk.Label(mainFrame, text="  □ 優先順位3: テンプレートマッチング法", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8,2))
        
        # テンプレート検索範囲
        templateFrame = tk.Frame(mainFrame)
        templateFrame.pack(fill=tk.X, pady=2)
        tk.Label(templateFrame, text="    テンプレート検索範囲:").pack(side=tk.LEFT)
        self.templateSearchEntry = tk.Entry(templateFrame, width=5)
        self.templateSearchEntry.insert(0, str(self.node.templateSearchRange))
        self.templateSearchEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(templateFrame, text="px (パターンマッチング検索範囲)").pack(side=tk.LEFT)
        
        # 拡張領域計算
        tk.Label(mainFrame, text="■ 拡張領域計算", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        tk.Label(mainFrame, text="パラメーターなし", fg="gray").pack(anchor=tk.W, pady=2)
        
        # 位置合わせ実行
        tk.Label(mainFrame, text="■ 位置合わせ実行", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        tk.Label(mainFrame, text="パラメーターなし", fg="gray").pack(anchor=tk.W, pady=2)
        
        # 余白処理
        tk.Label(mainFrame, text="■ 余白処理", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        cropFrame = tk.Frame(mainFrame)
        cropFrame.pack(fill=tk.X, pady=2)
        tk.Label(cropFrame, text="余白処理:").pack(side=tk.LEFT)
        self.cropVar = tk.StringVar(value=self.node.cropMode)
        cropCombo = ttk.Combobox(cropFrame, textvariable=self.cropVar, values=["none", "common"], width=10, state="readonly")
        cropCombo.pack(side=tk.LEFT, padx=5)
        tk.Label(cropFrame, text="(none:なし, common:共通領域)").pack(side=tk.LEFT)
        
        # ボタンフレーム
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        try:
            self.node.referenceIndex = max(0, int(self.refEntry.get()) - 1)
            self.node.gridRows = max(1, int(self.gridRowsEntry.get()))
            self.node.gridCols = max(1, int(self.gridColsEntry.get()))
            self.node.starsPerGrid = max(1, int(self.starsEntry.get()))
            self.node.alignmentPlane = max(0, min(2, int(self.planeEntry.get())))
            self.node.starThreshold = max(50, min(99, int(self.thresholdEntry.get())))
            self.node.cropMode = self.cropVar.get()
            self.node.phaseCorrelationMaxOffset = max(10, int(self.phaseOffsetEntry.get()))
            self.node.starSampleRadius = max(10, int(self.starDistEntry.get()))
            self.node.starMinDiameter = max(1, int(self.starMinDiameterEntry.get()))
            self.node.starMaxDiameter = max(self.node.starMinDiameter, int(self.starMaxDiameterEntry.get()))
            self.node.templateSearchRange = max(10, int(self.templateSearchEntry.get()))
            self.node.ransacIterations = max(10, min(1000, int(self.ransacEntry.get())))
            self.node.usePreviousOffset = self.usePrevOffsetVar.get()
            
            self.node.updateNodeText()
            
            newHash = self.node.getConfigHash()
            if newHash != self.node.lastConfigHash:
                self.node.lastConfigHash = newHash
                if hasattr(self.node.editor, 'onNodeConfigChanged'):
                    self.node.editor.onNodeConfigChanged(self.node)
                
        except ValueError:
            messagebox.showerror("エラー", "数値の入力が正しくありません")
    
    def onClose(self):
        self.destroy()