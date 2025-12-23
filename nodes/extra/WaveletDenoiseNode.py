'''
WaveletDenoiseNode class - 星保護付きウェーブレットノイズ除去

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

from base.FlowNode_CONST import *
from nodes import NNBlockOperationNode, ConfigurableNode

class WaveletDenoiseNode(NNBlockOperationNode,ConfigurableNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'wavelet_denoise'
    # ノード名
    name      = 'ウェーブレットノイズ除去'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # デフォルト設定
        self.wavelet = "db4"
        self.levels = 4
        self.sigma = 0.1
        self.star_threshold = 99.0  # パーセンタイル
        self.star_protection = True
        self.protection_radius = 3
        
        import importlib.util
        import sys
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("pywt"):
            messagebox.showerror(f"{self.name} エラー", "PyWaveletsライブラリが必要です\npip install PyWavelets")
        
        if not getattr(sys, 'frozen', False) and not importlib.util.find_spec("skimage"):
            messagebox.showerror(f"{self.name} エラー", "scikit-imageライブラリが必要です\npip install scikit-image")
    
    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\n{self.wavelet}\nL:{self.levels} S:{self.sigma}"
        if self.star_protection:
            displayText += f" 星保護ON"
        else:
            displayText += f" 星保護OFF"
        return displayText
    
    def createSettingWindow(self):
        return WaveletDenoiseSettingsDialog(self.view.editor.root, self)
    
    def store(self, nodeData):
        nodeData["wavelet"] = self.wavelet
        nodeData["levels"] = self.levels
        nodeData["sigma"] = self.sigma
        nodeData["star_threshold"] = self.star_threshold
        nodeData["star_protection"] = self.star_protection
        nodeData["protection_radius"] = self.protection_radius
    
    def restore(self, nodeData):
        self.wavelet = nodeData.get("wavelet", "db4")
        self.levels = nodeData.get("levels", 4)
        self.sigma = nodeData.get("sigma", 0.1)
        self.star_threshold = nodeData.get("star_threshold", 99.0)
        self.star_protection = nodeData.get("star_protection", True)
        self.protection_radius = nodeData.get("protection_radius", 3)
    
    def getConfigHash(self):
        config = f"{self.wavelet}_{self.levels}_{self.sigma}_{self.star_threshold}_{self.star_protection}_{self.protection_radius}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def processBlock(self, block):
        """ウェーブレットノイズ除去処理"""
        import numpy as np
        import pywt
        from utils import numpy_helpers as nh
        from base import DataBlock

        data = nh.array(block.data)
        
        # NaN値を事前に検出
        nan_mask = np.isnan(data)
        if np.all(nan_mask):
            return block  # 全てNaNの場合はそのまま返す
        
        # 結果を初期化（NaN値を保持）
        result = data.copy()
        
        # 有効値（NaN以外）のみ処理
        if np.any(~nan_mask):
            # NaNを一時的に0で置換して処理
            temp_data = np.where(nan_mask, 0, data)
            
            # 星マスクを作成（星保護が有効な場合）
            star_mask = None
            if self.star_protection:
                star_mask = self._create_star_mask(data)
            
            # 適切な分解レベルを計算
            max_levels = self._calculate_max_levels(temp_data.shape)
            actual_levels = min(self.levels, max_levels)
            
            # ウェーブレット変換
            coeffs = pywt.wavedec2(temp_data, self.wavelet, level=actual_levels)
            
            # ノイズ除去（詳細係数のみ）
            denoised_coeffs = list(coeffs)
            for i in range(1, len(coeffs)):
                # 各レベルの詳細係数 (cH, cV, cD)
                cH, cV, cD = coeffs[i]
                
                # ソフト閾値処理
                threshold = self.sigma * np.sqrt(2 * np.log(cH.size))
                denoised_coeffs[i] = (
                    pywt.threshold(cH, threshold, mode='soft'),
                    pywt.threshold(cV, threshold, mode='soft'),
                    pywt.threshold(cD, threshold, mode='soft')
                )
            
            # 逆ウェーブレット変換
            denoised = pywt.waverec2(denoised_coeffs, self.wavelet)
            
            # サイズを元データに合わせる
            if denoised.shape != data.shape:
                denoised = denoised[:data.shape[0], :data.shape[1]]
            
            # 星保護：マスク領域は元データを保持
            if star_mask is not None:
                denoised = np.where(star_mask, data, denoised)
            
            # 有効値のみ結果に反映
            result = np.where(nan_mask, data, denoised)
        
        return DataBlock(result, block.planeIndex, block.x, block.y)
    
    def _calculate_max_levels(self, shape):
        """データサイズに基づいて適切な最大分解レベルを計算"""
        import numpy as np
        
        min_size = min(shape)
        # 最小サイズが8ピクセル以下にならないよう制限
        max_levels = int(np.log2(min_size // 8)) if min_size >= 16 else 1
        return max(1, max_levels)
    
    def _create_star_mask(self, data):
        """星検出マスクを作成"""
        import numpy as np
        from skimage import morphology

        # 複数の閾値で星を検出
        masks = []
        thresholds = [self.star_threshold, self.star_threshold - 2.0, self.star_threshold - 5.0]
        
        for threshold in thresholds:
            if threshold > 0:
                star_level = np.nanpercentile(data, threshold)
                mask = data > star_level
                
                # 小さなノイズを除去
                mask = morphology.remove_small_objects(mask, min_size=4)
                
                # マスクを拡張して星の周辺も保護
                if np.any(mask):
                    mask = morphology.dilation(mask, morphology.disk(self.protection_radius))
                
                masks.append(mask)
        
        # 全てのマスクを統合
        if masks:
            combined_mask = np.logical_or.reduce(masks)
            return combined_mask
        else:
            return np.zeros_like(data, dtype=bool)

class WaveletDenoiseSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name}設定")
        self.geometry("400x500")
        
        self.createWidgets()
        
    def createWidgets(self):
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # カスタム設定を作成
        settingsFrame = self.createCustomSettings(mainFrame)
        settingsFrame.pack(fill=tk.BOTH, expand=True)
        
        # ボタンフレーム
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def createCustomSettings(self, parent):
        import numpy as np
        
        frame = tk.Frame(parent)
        
        # ウェーブレット種類
        tk.Label(frame, text="ウェーブレット:").pack(anchor="w")
        self.waveletVar = tk.StringVar(value=self.node.wavelet)
        wavelets = [
            "db1 - Daubechies1（最もシンプル）",
            "db4 - Daubechies4（バランス良好・推奨）",
            "db8 - Daubechies8（高品質・重い）",
            "haar - Haar（最速・粗い）",
            "bior2.2 - Biorthogonal2.2（対称性重視）",
            "bior4.4 - Biorthogonal4.4（高品質対称）",
            "coif2 - Coiflets2（有限の範囲）",
            "coif4 - Coiflets4（高精度・有限の範囲）"
        ]
        current_wavelet = next((w for w in wavelets if w.startswith(self.node.wavelet)), wavelets[1])
        self.waveletVar.set(current_wavelet)
        ttk.Combobox(frame, textvariable=self.waveletVar, values=wavelets, state="readonly").pack(fill=tk.X, pady=2)
        
        # 分解レベル
        tk.Label(frame, text="分解レベル:").pack(anchor="w", pady=(10,0))
        self.levelsVar = tk.IntVar(value=self.node.levels)
        # 推奨最大レベルを計算（一般的な画像サイズを想定）
        max_level = min(8, int(np.log2(4096 // 8)))
        self.levelsScale = tk.Scale(frame, from_=1, to=max_level, orient=tk.HORIZONTAL, variable=self.levelsVar)
        self.levelsScale.pack(fill=tk.X)
        
        # レベル情報ラベル
        self.levelInfoLabel = tk.Label(frame, text=f"推奨: 512x512:3-4, 1024x1024:4-5, 4096x4096:5-6", font=("Arial", 8), fg="gray")
        self.levelInfoLabel.pack(anchor="w")
        
        # ノイズ除去強度
        tk.Label(frame, text="ノイズ除去強度:").pack(anchor="w", pady=(10,0))
        self.sigmaVar = tk.DoubleVar(value=self.node.sigma)
        tk.Scale(frame, from_=0.01, to=10.0, resolution=0.01, orient=tk.HORIZONTAL, variable=self.sigmaVar).pack(fill=tk.X)
        
        # 星保護設定
        tk.Label(frame, text="星保護設定:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(20,5))
        
        self.protectionVar = tk.BooleanVar(value=self.node.star_protection)
        tk.Checkbutton(frame, text="星保護を有効にする", variable=self.protectionVar).pack(anchor="w")
        
        tk.Label(frame, text="星検出閾値 (パーセンタイル):").pack(anchor="w", pady=(10,0))
        self.thresholdVar = tk.DoubleVar(value=self.node.star_threshold)
        tk.Scale(frame, from_=80.0, to=99.9, resolution=0.1, orient=tk.HORIZONTAL, variable=self.thresholdVar).pack(fill=tk.X)
        
        tk.Label(frame, text="保護半径 (ピクセル):").pack(anchor="w", pady=(10,0))
        self.radiusVar = tk.IntVar(value=self.node.protection_radius)
        tk.Scale(frame, from_=1, to=10, orient=tk.HORIZONTAL, variable=self.radiusVar).pack(fill=tk.X)
        
        return frame
    
    def onApply(self):
        self.node.wavelet = self.waveletVar.get().split(' - ')[0]
        self.node.levels = self.levelsVar.get()
        self.node.sigma = self.sigmaVar.get()
        self.node.star_threshold = self.thresholdVar.get()
        self.node.star_protection = self.protectionVar.get()
        self.node.protection_radius = self.radiusVar.get()
        self.node.view.onNodeConfigChanged(self.node)
    
    def onClose(self):
        self.destroy()
