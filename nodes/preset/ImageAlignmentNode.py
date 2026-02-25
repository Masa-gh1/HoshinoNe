'''
ImageAlignmentNode class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
from types import SimpleNamespace
import hashlib
import tkinter as tk
from tkinter import messagebox, ttk

from base.FlowNode_CONST import *
from base import LazyFlowData
from nodes import NNBlockOperationNode
from nodes import ConfigurableNode

class AlignmentResult:
    def __init__(self, success=False, dx=0, dy=0, rotation=0, confidence=0, method="", extra_info={}):
        self.success = success
        self.dx = dx
        self.dy = dy
        self.rotation = rotation
        self.confidence = confidence
        self.method = method
        self.extra_info = extra_info

class ImageAlignmentNode(NNBlockOperationNode, ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'image_alignment'
    # ノード名
    name      = '画像位置合わせ'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # 設定パラメータ
        # 基準画像選択（auxiliaryでマークされた画像を使用）
        self.usePreviousOffset = True  # 前の画像のズレを考慮する
        # オフセット計算
        self.alignmentPlane = 1  # 位置合わせ用プレーン（0:R, 1:G, 2:B）
        self.saturationThreshold = 95  # 飽和閾値（%）
        # オフセット計算 優先順位1: 星点検出法
        self.star = SimpleNamespace()
        self.star.threshold = 95  # 星検出閾値（パーセンタイル）
        self.star.useSaturationMask = False #  飽和マスクを使用する
        self.star.minDiameter = 2  # 星最小直径（ピクセル）
        self.star.maxDiameter = 16  # 星最大直径（ピクセル）
        self.star.maxAspectRatio = 2.0  # 星の最大アスペクト比（形状フィルタ）
        self.star.grid = SimpleNamespace()
        self.star.grid.rows = 3  # グリッド行数
        self.star.grid.cols = 3  # グリッド列数
        self.star.grid.starsPerGrid = 8  # グリッド当たりの選択星数
        self.star.ransac = SimpleNamespace()
        self.star.ransac.sampleRadius = 100  # RANSAC対応点サンプル半径（ピクセル）
        self.star.ransac.iterations = 100  # RANSAC試行回数
        self.star.ransac.seed = 2725  # RANSAC乱数シード（１以上）
        # オフセット計算 優先順位2: 位相相関法
        self.phase = SimpleNamespace()
        self.phase.maxOffset = 100  # 位相相関最大オフセット（ピクセル）
        # オフセット計算 優先順位3: テンプレートマッチング法
        self.template = SimpleNamespace()
        self.template.searchRange = 150  # テンプレート検索範囲（ピクセル）
        # 拡張領域計算
        # 位置合わせ実行
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("cv2"):
            messagebox.showerror(f"{self.name} エラー", "ライブラリ OpenCV がインストールされていません。\npip install opencv-python でインストールしてください。")
            return
    
    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nG:{self.star.grid.cols}x{self.star.grid.rows} S:{self.star.ransac.sampleRadius}"
        return displayText
    
    def store(self, nodeData):
        nodeData["usePreviousOffset"] = self.usePreviousOffset
        nodeData["alignmentPlane"] = self.alignmentPlane
        nodeData["starThreshold"] = self.star.threshold
        nodeData["starMinDiameter"] = self.star.minDiameter
        nodeData["starMaxDiameter"] = self.star.maxDiameter
        nodeData["starSampleRadius"] = self.star.ransac.sampleRadius
        nodeData["saturationThreshold"] = self.saturationThreshold
        nodeData["useSaturationMask"] = self.star.useSaturationMask
        nodeData["maxAspectRatio"] = self.star.maxAspectRatio
        nodeData["gridRows"] = self.star.grid.rows
        nodeData["gridCols"] = self.star.grid.cols
        nodeData["starsPerGrid"] = self.star.grid.starsPerGrid
        nodeData["ransacIterations"] = self.star.ransac.iterations
        nodeData["ransacSeed"] = self.star.ransac.seed
        nodeData["phaseMaxOffset"] = self.phase.maxOffset
        nodeData["templateSearchRange"] = self.template.searchRange
    
    def restore(self, nodeData):
        if "usePreviousOffset" in nodeData:
            self.usePreviousOffset = nodeData["usePreviousOffset"]
        if "alignmentPlane" in nodeData:
            self.alignmentPlane = nodeData["alignmentPlane"]
        if "starThreshold" in nodeData:
            self.star.threshold = nodeData["starThreshold"]
        if "starMinDiameter" in nodeData:
            self.star.minDiameter = nodeData["starMinDiameter"]
        if "starMaxDiameter" in nodeData:
            self.star.maxDiameter = nodeData["starMaxDiameter"]
        if "starSampleRadius" in nodeData:
            self.star.ransac.sampleRadius = nodeData["starSampleRadius"]
        if "saturationThreshold" in nodeData:
            self.saturationThreshold = nodeData["saturationThreshold"]
        if "useSaturationMask" in nodeData:
            self.star.useSaturationMask = nodeData["useSaturationMask"]
        if "maxAspectRatio" in nodeData:
            self.star.maxAspectRatio = nodeData["maxAspectRatio"]
        if "gridRows" in nodeData:
            self.star.grid.rows = nodeData["gridRows"]
        if "gridCols" in nodeData:
            self.star.grid.cols = nodeData["gridCols"]
        if "starsPerGrid" in nodeData:
            self.star.grid.starsPerGrid = nodeData["starsPerGrid"]
        if "ransacIterations" in nodeData:
            self.star.ransac.iterations = nodeData["ransacIterations"]
        if "ransacSeed" in nodeData:
            self.star.ransac.seed = nodeData["ransacSeed"]
        if "phaseMaxOffset" in nodeData:
            self.phase.maxOffset = nodeData["phaseMaxOffset"]
        if "templateSearchRange" in nodeData:
            self.template.searchRange = nodeData["templateSearchRange"]
    
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
        
        if 0 == len(auxiliaryDatas):
            # 基準画像（auxiliary）が必要
            self._referenceData = None
            raise ValueError("基準画像（補正値）が必要です")
        else:
            # 複数ある場合は最初のものを採用
            self._referenceData = auxiliaryDatas[0]
        
        return primaryDatas
    
    def processBlock(self, block, planeIndex, x, y):
        """ブロック単位での位置合わせ処理"""
        if block is None:
            return None
        
        # 現在の実装では、全画像を一度に処理する必要があるため
        # ブロック処理は後の段階で実装
        return block
    
    def process(self, context=None):
        """画像位置合わせのメイン処理（LazyFlowData対応）"""
        self.reportProgress(context, "開始")
        
        # 入力データを収集
        inputDatas = []
        for node in self.inputNodes:
            inputDatas.extend(node.flowDatas)
        
        # primary/auxiliaryで分類
        primaryDatas = self.preprocessInputs(inputDatas)
        if self._referenceData is None:
            self.flowDatas = inputDatas
            return
        
        # 移動/回転計算のみを実行
        alignment_metadata = self._calculateAlignmentMetadata(primaryDatas, context)
        
        # LazyFlowDataを生成
        self.flowDatas = self._createLazyOutputs(primaryDatas, alignment_metadata)
        
        self.reportProgress(context, "完了")
    
    def _calculateAlignmentMetadata(self, inputDatas, context):
        """移動/回転計算のみを実行"""
        import numpy as np
        
        # 基準画像
        referenceData = self._referenceData

        # 経過報告用全画像のズレ計算ステップ数
        totalGlobalBlocks = 1 + 2*(len(inputDatas) - 1)  # 基準画像処理(1) + 各非基準画像のズレ計算(2回ずつ)
        globalProcessedBlocks = 0
        
        # 基準画像を検出用に処理
        if context:
            self.reportProgress(context, "基準画像処理中", globalProcessedBlocks, totalGlobalBlocks)
        refGray = self._flowDataToImage(referenceData, planeIndex=self.alignmentPlane, normalize_for_detection=True)
        
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
            targetGray = self._flowDataToImage(inputData, planeIndex=self.alignmentPlane, normalize_for_detection=True)
            globalProcessedBlocks += 1
            if context:
                self.reportProgress(context, f"画像{i+1}のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)
            
            # 位置合わせ計算
            star_result = self._findOffsetByStarDetection(refGray, targetGray, previous_result)
            phase_result = self._findOffsetByPhaseCorrelation(refGray, targetGray, previous_result) if not star_result.success else None
            template_result = self._findOffsetByTemplateMatching(refGray, targetGray, previous_result) if not star_result.success and (phase_result is None or not phase_result.success) else None
            
            # 成功した結果を選択
            result = star_result if star_result.success else (phase_result if phase_result and phase_result.success else template_result)
            if result is None:
                result = AlignmentResult()
            
            # この画像の計算法毎の結果を保存
            method_results = {'star': star_result, 'phase': phase_result, 'template': template_result}
            
            all_results.append(result)
            all_method_results_list.append(method_results)
            previous_result = result
            
            globalProcessedBlocks += 1
            if context:
                self.reportProgress(context, f"画像{i+1}のズレ計算中", globalProcessedBlocks, totalGlobalBlocks)

        
        # 回転を考慮した拡張領域計算
        width, height = referenceData.getDimensions()
        all_corners = []
        
        for result in all_results:
            corners = self._calculateTransformedCorners(width, height, result.dx, result.dy, result.rotation)
            all_corners.extend(corners)
        
        min_x = min(corner[0] for corner in all_corners)
        min_y = min(corner[1] for corner in all_corners)
        max_x = max(corner[0] for corner in all_corners)
        max_y = max(corner[1] for corner in all_corners)
        
        expand_left = int(max(0, -min_x))
        expand_top = int(max(0, -min_y))
        new_width = int(np.ceil(max_x - min_x))
        new_height = int(np.ceil(max_y - min_y))
        
        return {
            'results': all_results,
            'method_results': all_method_results_list,
            'expand_params': (expand_left, expand_top, new_width, new_height)
        }
    
    def _calculateTransformedCorners(self, width, height, dx, dy, rotation):
        """画像の4隅の変換後座標を計算（画像中心回転）"""
        import cv2
        from utils import numpy_helpers as nh

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
    
    def _createLazyOutputs(self, inputDatas, metadata):
        """LazyFlowDataを生成"""
        flowDatas = metadata['results']
        method_results = metadata['method_results']
        expand_left, expand_top, new_width, new_height = metadata['expand_params']
        
        flowDatas = []
        
        for i, (inputData, result, method_result) in enumerate(zip(inputDatas, flowDatas, method_results)):
            # 画像移動量 = 検出移動量 + 拡張領域
            dx = result.dx + expand_left
            dy = result.dy + expand_top
            
            # 位置合わせ情報をheadersに追加
            alignment_info = {}
            alignment_info['method'] = result.method
            alignment_info['success'] = result.success
            alignment_info['confidence'] = result.confidence
            alignment_info['movement_from_reference'] = {'dx': result.dx, 'dy': result.dy, 'rotation': result.rotation}
            
            # 各処理法の結果を個別に記録
            for method, value in method_result.items():
                if value:
                    alignment_info[f'{method}_success'] = value.success
                    alignment_info[f'{method}_confidence'] = value.confidence
                    alignment_info[f'{method}_movement'] = {'dx': value.dx, 'dy': value.dy, 'rotation': value.rotation}
                    if value.extra_info:
                        alignment_info[f'{method}_extra_info'] = value.extra_info

            flowData = ImageAlignmentLazyFlowData(inputData, dx, dy, result.rotation, new_width, new_height)
            flowData.headers.update(alignment_info)
            flowData.setDimensions(new_width, new_height)
            flowDatas.append(flowData)
            
        return flowDatas
    
    def _flowDataToImage(self, flowData, planeIndex=None, normalize_for_detection=False):
        """FlowDataから画像配列を構築"""
        import numpy as np
        from utils import numpy_helpers as nh

        width, height = flowData.getDimensions()
        
        if planeIndex is not None:
            # 特定プレーンのみを使用
            image = nh.zeros((height, width))
            for block in flowData.iterateBlocks():
                if block and block.planeIndex == planeIndex:
                    y1, y2 = block.y, block.y + block.getHeight()
                    x1, x2 = block.x, block.x + block.getWidth()
                    if len(block.data.shape) == 3:
                        image[y1:y2, x1:x2] = block.data[:, :, 0]
                    else:
                        image[y1:y2, x1:x2] = block.data
            
            # 星検出用の正規化処理（統計的手法）
            if normalize_for_detection:
                min_val = np.min(image)
                max_val = np.max(image)
                margin = (max_val - min_val) * float(self.saturationThreshold) / 100
                saturation_threshold_l = min_val + margin
                saturation_threshold_h = max_val - margin
                valid_mask = (image > saturation_threshold_l) & (image < saturation_threshold_h)
                valid_pixels = image[valid_mask]
                if np.any(valid_mask):
                    mean_val = np.mean(valid_pixels)
                    std_val = np.std(valid_pixels)
                else:
                    mean_val = np.mean(image)
                    std_val = np.std(image)
                if std_val > 0:
                    image = (image - mean_val) / std_val
                    image = np.clip((image + 3) / 6 * 255, 0, 255)
                else:
                    image = np.zeros_like(image)
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
    
    def _findOffsetByTemplateMatching(self, refImage, targetImage, previous_result=None):
        """テンプレートマッチングでオフセットを検出"""
        import cv2

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
        search_range = self.template.searchRange  # 前画像位置からの検索範囲
        
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
            return AlignmentResult(success=False, method="template", extra_info={"max_correlation": max_val, "threshold": 0.3})
        
        # オフセットを計算
        match_x, match_y = max_loc
        actual_x = search_x1 + match_x
        actual_y = search_y1 + match_y
        
        dx = actual_x - x1
        dy = actual_y - y1
        
        return AlignmentResult( success=True, dx=dx, dy=dy, confidence=max_val, method="template")
    
    def _findOffsetByPhaseCorrelation(self, refImage, targetImage, previous_result=None):
        """位相相関法でオフセットを検出"""
        import numpy as np
        import cv2
        from utils import numpy_helpers as nh

        if previous_result is None:
            previous_result = AlignmentResult()
        
        max_offset = self.phase.maxOffset
        # エッジ強化で特徴を明確化
        ref_edges    = cv2.Laplacian(refImage   , cv2.CV_64F)
        target_edges = cv2.Laplacian(targetImage, cv2.CV_64F)
        
        # エッジと元画像を組み合わせ
        ref_combined    = 0.7 * refImage.astype(nh.BDTYPE)    + 0.3 * np.abs(ref_edges)
        target_combined = 0.7 * targetImage.astype(nh.BDTYPE) + 0.3 * np.abs(target_edges)
        
        # コントラスト正規化
        ref_combined    = (ref_combined    - ref_combined.mean()   ) / (ref_combined.std()    + 1e-10)
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
            x_vals = nh.array([-2, -1, 0, 1, 2])
            y_vals = nh.array([-2, -1, 0, 1, 2])
            
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
                return AlignmentResult(success=False, method="phase", extra_info={"peak_sharpness": peak_sharpness, "distance_from_prev": distance_from_prev, "max_offset": max_offset})
        else:
            # ピークの鋭さのみで判定
            if peak_sharpness < 1.5:
                return AlignmentResult(success=False, method="phase", extra_info={"peak_sharpness": peak_sharpness, "threshold": 1.5})
        
        confidence = min(1.0, peak_sharpness / 10.0)  # 正規化した信頼度
        return AlignmentResult( success=True, dx=dx, dy=dy, confidence=confidence, method="phase")
    
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
        rng = np.random.default_rng(self.star.ransac.seed)
        extra_info["star_ransac_seed"] = self.star.ransac.seed
        
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
        ref_bright, ref_grid_counts = self._selectDistributedStars(ref_stars, refImage.shape)
        target_bright, target_grid_counts = self._selectDistributedStars(target_stars, targetImage.shape)
        
        aspectRatioMedian = np.median([aspectRatio for _, _, _, aspectRatio in target_bright])
        extra_info["ref_grid_counts"] = ref_grid_counts
        extra_info["target_grid_counts"] = target_grid_counts
        extra_info["aspectRatioMedian"] = aspectRatioMedian
        
        # 前画像のオフセット・回転を考慮した対応点探索
        matches = []
        radius_sq = self.star.ransac.sampleRadius ** 2  # 二乗距離で比較
        
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
        for ransac_iteration in range(self.star.ransac.iterations): # RANSAC試行回数
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
        
        if inliers >= 5:  # 5個以上のインライア
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
            
            if len(inlier_matches) >= 3:
                transform_result = self._calculateAffineTransform(inlier_matches, currentImageShape)
                if isinstance(transform_result, tuple):
                    dx, dy = transform_result
                else:
                    dx, dy = transform_result[0, 2], transform_result[1, 2]
                    rotation = np.arctan2(transform_result[1, 0], transform_result[0, 0]) * 180 / np.pi
            
            from utils.Debug import Debug
            degug = f"dx,dy:{dx:.3f},{dy:.3f} rotation:{rotation:.3f}"
            degug += " " + f"len(target_bright):{len(extra_info['target_bright'])}" if 'target_bright' in extra_info else ""
            degug += " " + f"aspectRatioMedian:{extra_info['aspectRatioMedian']:.2f}" if 'aspectRatioMedian' in extra_info else ""
            degug += " " + f"inliers:{extra_info['inliers']}" if 'inliers' in extra_info else ""
            degug += " " + f"ransac_iteration:{extra_info['ransac_iteration']}" if 'ransac_iteration' in extra_info else ""
            Debug.log(type(self).__name__,f"{degug}")
            
            return AlignmentResult( success=True, dx=dx, dy=dy, rotation=rotation, confidence=confidence, method="star", extra_info=extra_info)
        
        return AlignmentResult(success=False, method="star", extra_info=extra_info)
    
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
        M = cv2.estimateAffinePartial2D(target_centered, ref_centered, method=cv2.RANSAC,
                                        ransacReprojThreshold=2.0)[0]
        
        if M is not None:
            # 回転角を計算
            rotation_angle = np.arctan2(M[1, 0], M[0, 0]) * 180 / np.pi
            
            # 小さな回転のみ適用（天体写真では通常数度以内）
            if abs(rotation_angle) < 10.0:
                # 画像中心回転用の変換行列を作成
                cos_r = M[0, 0]
                sin_r = M[1, 0]
                
                # 平行移動成分を画像中心回転に合わせて調整
                dx = M[0, 2] + image_center[0] * (1 - cos_r) + image_center[1] * sin_r
                dy = M[1, 2] + image_center[1] * (1 - cos_r) - image_center[0] * sin_r
                
                # 画像中心回転の変換行列を返す
                M_centered = nh.array([[cos_r, -sin_r, dx], [sin_r, cos_r, dy]])
                return M_centered
            else:
                # 大きな回転は平行移動のみ適用
                dx = M[0, 2]
                dy = M[1, 2]
                return (dx, dy)
        
        # アフィン変換が失敗した場合は平行移動のみ
        dx_sum = sum(ref_pt[0] - target_pt[0] for ref_pt, target_pt in matches)
        dy_sum = sum(ref_pt[1] - target_pt[1] for ref_pt, target_pt in matches)
        return (dx_sum / len(matches), dy_sum / len(matches))
    
    def _calculateGridMatches(self, matches, offset, image_shape):
        """グリッド別のマッチ数を計算"""
        import numpy as np

        h, w = image_shape
        grid_rows, grid_cols = self.star.grid.rows, self.star.grid.cols
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
    
    def _detectStars(self, image):
        """画像から星点を検出"""
        import numpy as np
        import cv2

        # ガウシアンブラーでノイズ除去
        blurred = cv2.GaussianBlur(image, (3, 3), 0)
        
        # メディアンフィルタでバックグラウンドを推定
        background = cv2.medianBlur(blurred, 51)
        
        # バックグラウンドを減算
        subtracted = cv2.subtract(blurred, background)
        
        if self.star.useSaturationMask:
            # 飽和領域マスク
            saturation_mask = self._createSaturationMask(subtracted)
            masked_subtracted = np.where(saturation_mask, subtracted, 0)
            
            # 閾値処理
            threshold = np.nanpercentile(masked_subtracted[masked_subtracted > 0], self.star.threshold)
            _, binary = cv2.threshold(masked_subtracted, threshold, 255, cv2.THRESH_BINARY)
        else:
            # 閾値処理
            threshold = np.nanpercentile(subtracted[subtracted > 0], self.star.threshold)
            _, binary = cv2.threshold(subtracted, threshold, 255, cv2.THRESH_BINARY)
        
        # 連結成分で星点を検出
        try:
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except (cv2.error, SystemError):
            # OpenCV 4.5.5以降のバグ対応
            from utils.Debug import Debug
            Debug.log(type(self).__name__,"Retry cv2.findContours")
            try:
                contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            except (cv2.error, SystemError):
                contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        stars = contours
        
        # 面積フィルタ
        min_area = np.pi * (self.star.minDiameter / 2) ** 2
        max_area = np.pi * (self.star.maxDiameter / 2) ** 2
        areaFiltered = [c for c in stars if min_area <= cv2.contourArea(c) <= max_area]
        stars = areaFiltered
        
        # アスペクト比フィルタ
        aspectFiltered = []
        aspectRatios = []
        for star in stars:
            # 最小外接矩形（回転考慮）
            (center), (width, height), angle = cv2.minAreaRect(star)
            
            # アスペクト比計算
            if width > 0 and height > 0:
                aspectRatio = max(width, height) / min(width, height)
                if aspectRatio <= self.star.maxAspectRatio:
                    aspectFiltered.append(star)
                    aspectRatios.append(aspectRatio)
        stars = aspectFiltered
        
        # 星の位置と明るさを取得
        positions = []
        brightnesses = []
        for star in stars:
            area = cv2.contourArea(star)
            # 重心を計算
            M = cv2.moments(star)
            if M['m00'] <= 0:
                positions.append(None)
                brightnesses.append(None)
            else:
                cx = M['m10'] / M['m00']
                cy = M['m01'] / M['m00']
                positions.append((cx,cy))
                
                # その点の明度を取得
                x, y = int(cx), int(cy)
                if 0 <= x < subtracted.shape[1] and 0 <= y < subtracted.shape[0]:
                    brightness = float(subtracted[y, x])
                    brightnesses.append(brightness)
                else:
                    brightnesses.append(None)
        
        ret = []
        for pos, brightness, aspectRatio in zip(positions,brightnesses,aspectRatios):
            if pos:
                cx, cy = pos
                ret.append((cx, cy, brightness, aspectRatio))
        
        return ret
    
    def _createSaturationMask(self, image):
        """飽和領域のマスクを作成"""
        import numpy as np
        import cv2

        max_val = np.max(image)
        saturated = image > (max_val * self.saturationThreshold / 100)
        
        # 飽和領域を膨張させて周辺も除外
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
        mask = cv2.dilate(saturated.astype(np.uint8), kernel, iterations=2)
        
        return mask == 0  # 有効領域のマスク
    
    def _selectDistributedStars(self, stars, image_shape):
        """画像全体に分散した星を選択"""
        if len(stars) < 10:
            return stars, []
        
        h, w = image_shape
        grid_rows, grid_cols = self.star.grid.rows, self.star.grid.cols
        
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
                for x, y, brightness, aspectRatio in stars:
                    if x_min <= x < x_max and y_min <= y < y_max:
                        grid_stars.append((x, y, brightness, aspectRatio))
                
                # 明度順でソートして上位指定数を選択
                selected_count = 0
                if grid_stars:
                    grid_stars.sort(key=lambda x: x[2], reverse=True)
                    selected = grid_stars[:self.star.grid.starsPerGrid]
                    distributed_stars.extend(selected)
                    selected_count = len(selected)
                
                grid_selected_counts.append(selected_count)
        
        # 全体からも明るい星を追加（重複除去）
        max_total_stars = grid_rows * grid_cols * self.star.grid.starsPerGrid + 20
        all_bright = sorted(stars, key=lambda x: x[2], reverse=True)
        for star in all_bright:
            if star not in distributed_stars and len(distributed_stars) < max_total_stars:
                distributed_stars.append(star)
        
        return distributed_stars[:max_total_stars], grid_selected_counts
    

    
    def createSettingWindow(self):
        return ImageAlignmentSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config = f"{self.usePreviousOffset}_{self.alignmentPlane}_{self.star.threshold}_{self.star.minDiameter}_{self.star.maxDiameter}_{self.star.maxAspectRatio}_{self.star.ransac.sampleRadius}_{self.saturationThreshold}_{self.star.useSaturationMask}_{self.star.grid.rows}_{self.star.grid.cols}_{self.star.grid.starsPerGrid}_{self.star.ransac.iterations}_{self.star.ransac.seed}_{self.phase.maxOffset}_{self.template.searchRange}"
        return hashlib.md5(config.encode()).hexdigest()

class ImageAlignmentLazyFlowData(LazyFlowData):
    def operation(self, flowData, planeIndex, x, y, dx, dy, rotation, new_width, new_height):
        """位置合わせ + 拡張を一度に実行"""
        import numpy as np
        import cv2
        
        from config import BLOCK_SIZE
        from utils import numpy_helpers as nh
        from base import DataBlock
        
        orig_width, orig_height = flowData.getDimensions()
        
        # 出力ブロックの4隅を逆変換して必要な入力範囲を計算
        corners = nh.array([[x, y], [x+BLOCK_SIZE, y], [x+BLOCK_SIZE, y+BLOCK_SIZE], [x, y+BLOCK_SIZE]], dtype=np.float64)
        
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
            
            # 変換行列を作成（部分画像座標系）
            if rotation != 0:
                # 元画像の中心を部分画像座標系に変換
                orig_center_x = orig_width  / 2 - min_block_x
                orig_center_y = orig_height / 2 - min_block_y
                M = cv2.getRotationMatrix2D((orig_center_x, orig_center_y), rotation, 1.0)
                M[0, 2] += dx
                M[1, 2] += dy
            else:
                M = np.float64([[1, 0, dx], [0, 1, dy]])
            
            # 変換後に必要なサイズを計算
            transform_output_width = min(region_width, new_width - (x - min_block_x))
            transform_output_height = min(region_height, new_height - (y - min_block_y))
            
            # 部分画像を変換
            transformed_region = cv2.warpAffine(region_image, M, (transform_output_width, transform_output_height),
                                            flags=cv2.INTER_LINEAR,
                                            borderMode=cv2.BORDER_CONSTANT,
                                            borderValue=np.nan)
            
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

class ImageAlignmentSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name}設定")
        self.geometry("450x700")
        
        self.createWidgets()
        
    def createWidgets(self):
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 基準画像選択
        tk.Label(mainFrame, text="■ 基準画像", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5,2))
        
        # 前回ズレ考慮機能
        prevOffsetFrame = tk.Frame(mainFrame)
        prevOffsetFrame.pack(fill=tk.X, pady=2)
        self.usePrevOffsetVar = tk.BooleanVar(value=self.node.usePreviousOffset)
        tk.Checkbutton(prevOffsetFrame, text="前の画像のズレを考慮する", variable=self.usePrevOffsetVar).pack(side=tk.LEFT)
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
        self.thresholdEntry.insert(0, str(self.node.star.threshold))
        self.thresholdEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(thresholdFrame, text="% (上位%の明るい星を選択)").pack(side=tk.LEFT)
        
        # 飽和マスクを使用
        useSaturationMaskFrame = tk.Frame(mainFrame)
        useSaturationMaskFrame.pack(fill=tk.X, pady=2)
        tk.Label(useSaturationMaskFrame, text="    飽和マスクを使用する:").pack(side=tk.LEFT)
        self.useSaturationMaskVar = tk.BooleanVar(value=self.node.star.useSaturationMask)
        tk.Checkbutton(useSaturationMaskFrame, text="飽和領域を除いて星検出閾値を適用", variable=self.useSaturationMaskVar).pack(side=tk.LEFT)
        
        # 星直径閾値
        starSizeFrame = tk.Frame(mainFrame)
        starSizeFrame.pack(fill=tk.X, pady=2)
        tk.Label(starSizeFrame, text="    星直径閾値:").pack(side=tk.LEFT)
        self.starMinDiameterEntry = tk.Entry(starSizeFrame, width=5)
        self.starMinDiameterEntry.insert(0, str(self.node.star.minDiameter))
        self.starMinDiameterEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(starSizeFrame, text="~").pack(side=tk.LEFT)
        self.starMaxDiameterEntry = tk.Entry(starSizeFrame, width=5)
        self.starMaxDiameterEntry.insert(0, str(self.node.star.maxDiameter))
        self.starMaxDiameterEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(starSizeFrame, text="px (検出対象の星直径)").pack(side=tk.LEFT)
        
        # 除外する最大アスペクト比
        aspectRatioFrame = tk.Frame(mainFrame)
        aspectRatioFrame.pack(fill=tk.X, pady=2)
        tk.Label(aspectRatioFrame, text="    除外する最大アスペクト比:").pack(side=tk.LEFT)
        self.aspectRatioEntry = tk.Entry(aspectRatioFrame, width=5)
        self.aspectRatioEntry.insert(0, str(self.node.star.maxAspectRatio))
        self.aspectRatioEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(aspectRatioFrame, text="(この比以上の細長い物体を除外)").pack(side=tk.LEFT)
        
        # グリッド設定
        gridFrame = tk.Frame(mainFrame)
        gridFrame.pack(fill=tk.X, pady=2)
        tk.Label(gridFrame, text="    グリッド:").pack(side=tk.LEFT)
        self.gridRowsEntry = tk.Entry(gridFrame, width=5)
        self.gridRowsEntry.insert(0, str(self.node.star.grid.rows))
        self.gridRowsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="x").pack(side=tk.LEFT)
        self.gridColsEntry = tk.Entry(gridFrame, width=5)
        self.gridColsEntry.insert(0, str(self.node.star.grid.cols))
        self.gridColsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="(星選択用分割数)").pack(side=tk.LEFT)
        
        # グリッド当たりの選択星数
        starsFrame = tk.Frame(mainFrame)
        starsFrame.pack(fill=tk.X, pady=2)
        tk.Label(starsFrame, text="    グリッド当たり星数:").pack(side=tk.LEFT)
        self.starsEntry = tk.Entry(starsFrame, width=10)
        self.starsEntry.insert(0, str(self.node.star.grid.starsPerGrid))
        self.starsEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから選ぶ星数)").pack(side=tk.LEFT)
        
        # 星サンプル半径
        starDistFrame = tk.Frame(mainFrame)
        starDistFrame.pack(fill=tk.X, pady=2)
        tk.Label(starDistFrame, text="    星サンプル半径:").pack(side=tk.LEFT)
        self.starDistEntry = tk.Entry(starDistFrame, width=5)
        self.starDistEntry.insert(0, str(self.node.star.ransac.sampleRadius))
        self.starDistEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starDistFrame, text="px (統計処理用サンプル収集範囲)").pack(side=tk.LEFT)
        
        # RANSAC試行回数
        ransacFrame = tk.Frame(mainFrame)
        ransacFrame.pack(fill=tk.X, pady=2)
        tk.Label(ransacFrame, text="    RANSAC試行回数:").pack(side=tk.LEFT)
        self.ransacEntry = tk.Entry(ransacFrame, width=5)
        self.ransacEntry.insert(0, str(self.node.star.ransac.iterations))
        self.ransacEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(ransacFrame, text="回 (外れ値耐性用繰り返し回数)").pack(side=tk.LEFT)
        
        # RANSAC乱数シード
        seedFrame = tk.Frame(mainFrame)
        seedFrame.pack(fill=tk.X, pady=2)
        tk.Label(seedFrame, text="    RANSAC乱数シード:").pack(side=tk.LEFT)
        self.ransacSeedEntry = tk.Entry(seedFrame, width=5)
        self.ransacSeedEntry.insert(0, str(self.node.star.ransac.seed))
        self.ransacSeedEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(seedFrame, text="(1以上、結果が悪い場合は変更)").pack(side=tk.LEFT)
        
        # 優先順位2: 位相相関法
        tk.Label(mainFrame, text="  □ 優先順位2: 位相相関法", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8,2))
        
        # 位相相関最大オフセット
        phaseFrame = tk.Frame(mainFrame)
        phaseFrame.pack(fill=tk.X, pady=2)
        tk.Label(phaseFrame, text="    位相相関最大オフセット:").pack(side=tk.LEFT)
        self.phaseOffsetEntry = tk.Entry(phaseFrame, width=5)
        self.phaseOffsetEntry.insert(0, str(self.node.phase.maxOffset))
        self.phaseOffsetEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(phaseFrame, text="px (FFT位置合わせ上限)").pack(side=tk.LEFT)
        
        # 優先順位3: テンプレートマッチング法
        tk.Label(mainFrame, text="  □ 優先順位3: テンプレートマッチング法", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8,2))
        
        # テンプレート検索範囲
        templateFrame = tk.Frame(mainFrame)
        templateFrame.pack(fill=tk.X, pady=2)
        tk.Label(templateFrame, text="    テンプレート検索範囲:").pack(side=tk.LEFT)
        self.templateSearchEntry = tk.Entry(templateFrame, width=5)
        self.templateSearchEntry.insert(0, str(self.node.template.searchRange))
        self.templateSearchEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(templateFrame, text="px (パターンマッチング検索範囲)").pack(side=tk.LEFT)
        
        # 拡張領域計算
        tk.Label(mainFrame, text="■ 拡張領域計算", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        tk.Label(mainFrame, text="パラメーターなし", fg="gray").pack(anchor=tk.W, pady=2)
        
        # 位置合わせ実行
        tk.Label(mainFrame, text="■ 位置合わせ実行", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10,2))
        tk.Label(mainFrame, text="パラメーターなし", fg="gray").pack(anchor=tk.W, pady=2)
        

        
        # ボタンフレーム
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        try:
            self.node.star.grid.rows = max(1, int(self.gridRowsEntry.get()))
            self.node.star.grid.cols = max(1, int(self.gridColsEntry.get()))
            self.node.star.grid.starsPerGrid = max(1, int(self.starsEntry.get()))
            self.node.alignmentPlane = max(0, min(2, int(self.planeEntry.get())))
            self.node.star.threshold = max(50, min(99, int(self.thresholdEntry.get())))

            self.node.phase.maxOffset = max(10, int(self.phaseOffsetEntry.get()))
            self.node.star.ransac.sampleRadius = max(10, int(self.starDistEntry.get()))
            self.node.star.minDiameter = max(1, int(self.starMinDiameterEntry.get()))
            self.node.star.maxDiameter = max(self.node.star.minDiameter, int(self.starMaxDiameterEntry.get()))
            self.node.template.searchRange = max(10, int(self.templateSearchEntry.get()))
            self.node.star.ransac.iterations = max(10, min(1000, int(self.ransacEntry.get())))
            self.node.star.ransac.seed = max(1, int(self.ransacSeedEntry.get()))
            self.node.usePreviousOffset = self.usePrevOffsetVar.get()
            self.node.star.useSaturationMask = self.useSaturationMaskVar.get()
            self.node.star.maxAspectRatio = max(1.0, float(self.aspectRatioEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
                
        except ValueError:
            messagebox.showerror("エラー", "数値の入力が正しくありません")
    
    def onClose(self):
        self.destroy()