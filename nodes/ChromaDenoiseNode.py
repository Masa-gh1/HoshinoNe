'''
ChromaDenoiseNode class - 色空間分離ノイズ除去

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
import hashlib
from base import FlowNode, DataBlock, FlowData
from base.ConfigurableNode import ConfigurableNode
from utils import numpy_helpers as nh

try:
    from scipy.ndimage import gaussian_filter, sobel
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

class ChromaDenoiseNode(FlowNode,ConfigurableNode):
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, "chroma_denoise", "色空間分離ノイズ除去")
        
        # デフォルト設定
        self.colorspace = "Lab"  # Lab, YUV, HSV
        self.chroma_strength = 2.0  # 色成分のノイズ除去強度
        self.luma_strength = 0.5    # 輝度成分のノイズ除去強度
        self.preserve_edges = True  # エッジ保護
        self.edge_threshold = 0.00001   # エッジ検出閾値
        
        self.lastConfigHash = None

        if not SCIPY_AVAILABLE:
            messagebox.showerror(f"{self.text} エラー", "scipyライブラリがインストールされていません\npip install scipy でインストールしてください")
        
        self.updateNodeText()
    
    def updateNodeText(self):
        displayText = f"{self.text}\n{self.colorspace}\nC:{self.chroma_strength:.1f} L:{self.luma_strength:.1f}"
        self.editor.updateNodeText(self, displayText)
        
        newHash = self.getConfigHash()
        if newHash != self.lastConfigHash:
            self.lastConfigHash = newHash
            if hasattr(self.editor, 'onNodeConfigChanged'):
                self.editor.onNodeConfigChanged(self)
    
    def onEdit(self):
        return ChromaDenoiseSettingsDialog(self.editor.root, self)
    
    def store(self, nodeData):
        nodeData["colorspace"] = self.colorspace
        nodeData["chroma_strength"] = self.chroma_strength
        nodeData["luma_strength"] = self.luma_strength
        nodeData["preserve_edges"] = self.preserve_edges
        nodeData["edge_threshold"] = self.edge_threshold
    
    def restore(self, nodeData):
        self.colorspace = nodeData.get("colorspace", "Lab")
        self.chroma_strength = nodeData.get("chroma_strength", 2.0)
        self.luma_strength = nodeData.get("luma_strength", 0.5)
        self.preserve_edges = nodeData.get("preserve_edges", True)
        self.edge_threshold = nodeData.get("edge_threshold", 0.00001)
        self.updateNodeText()
    
    def getColor(self):
        return self._color_func
    
    def getConfigHash(self):
        config = f"{self.colorspace}_{self.chroma_strength}_{self.luma_strength}_{self.preserve_edges}_{self.edge_threshold}"
        return hashlib.md5(config.encode()).hexdigest()
    
    def process(self, context=None):
        """RGB画像全体を処理"""
        self.reportProgress(context, "開始")
        
        # 入力データを取得
        flowDatas = []
        for node in self.inputNodes:
            flowDatas.extend(node.flowDatas)
        
        if not flowDatas:
            return
        
        resultFlowDatas = []
        
        for flowData in flowDatas:
            if flowData.getPlaneCount() < 3:
                # RGB以外はそのまま通す
                resultFlowDatas.append(flowData)
                continue
            
            # RGB画像を再構築
            width, height = flowData.getDimensions()
            rgb_image = self._reconstruct_rgb_image(flowData, width, height)
            
            # 色空間変換してノイズ除去
            denoised_rgb = self._denoise_color_image(rgb_image)
            
            # 結果をFlowDataに変換
            result_flowdata = self._create_result_flowdata(flowData, denoised_rgb)
            resultFlowDatas.append(result_flowdata)
            
            self.reportProgress(context, "処理中")
        
        self.flowDatas = resultFlowDatas
        self.reportProgress(context, "完了")
    
    def _reconstruct_rgb_image(self, flowData, width, height):
        """FlowDataからRGB画像を再構築"""
        rgb_image = nh.zeros((height, width, 3))
        
        from config import BLOCK_SIZE
        for blockY in range(0, height, BLOCK_SIZE):
            for blockX in range(0, width, BLOCK_SIZE):
                for c in range(3):
                    block = flowData.getBlock(c, blockX, blockY)
                    if block:
                        endY = min(blockY + block.getHeight(), height)
                        endX = min(blockX + block.getWidth(), width)
                        rgb_image[blockY:endY, blockX:endX, c] = block.data[:endY-blockY, :endX-blockX]
        
        return rgb_image
    
    def _denoise_color_image(self, rgb_image):
        """色ノイズ除去処理（NaN対応）"""
        # NaN値を事前に検出
        nan_mask = np.isnan(rgb_image)
        if np.all(nan_mask):
            return rgb_image  # 全てNaNの場合はそのまま返す
        
        # 入力範囲を検出して0.0-1.0に正規化（NaN除外）
        input_min = np.nanmin(rgb_image)
        input_max = np.nanmax(rgb_image)
        
        if input_max > input_min:
            rgb_normalized = (rgb_image - input_min) / (input_max - input_min)
        else:
            rgb_normalized = rgb_image.copy()
        
        # 色空間変換
        if self.colorspace == "Lab":
            converted = self._rgb_to_lab(rgb_normalized)
        elif self.colorspace == "YUV":
            converted = self._rgb_to_yuv(rgb_normalized)
        elif self.colorspace == "HSV":
            converted = self._rgb_to_hsv(rgb_normalized)
        else:
            converted = rgb_normalized.copy()
        
        # エッジマスク作成（エッジ保護が有効な場合）
        edge_mask = None
        if self.preserve_edges:
            edge_mask = self._create_edge_mask(converted[:,:,0])  # 輝度成分でエッジ検出
        
        # 各チャンネルにノイズ除去を適用（NaN値は保持）
        denoised = converted.copy()
        
        # 輝度成分（L, Y, V）
        if self.luma_strength > 0:
            sigma = self.luma_strength
            if edge_mask is not None:
                denoised[:,:,0] = self._edge_preserving_filter_nan(converted[:,:,0], sigma, edge_mask)
            else:
                denoised[:,:,0] = self._gaussian_filter_nan(converted[:,:,0], sigma)
        
        # 色成分（a,b / U,V / H,S）のノイズ除去
        if self.chroma_strength > 0:
            sigma = self.chroma_strength
            for c in range(1, 3):
                if edge_mask is not None:
                    denoised[:,:,c] = self._edge_preserving_filter_nan(converted[:,:,c], sigma, edge_mask)
                else:
                    denoised[:,:,c] = self._gaussian_filter_nan(converted[:,:,c], sigma)
        
        # RGB色空間に戻す
        if self.colorspace == "Lab":
            result = self._lab_to_rgb(denoised)
        elif self.colorspace == "YUV":
            result = self._yuv_to_rgb(denoised)
        elif self.colorspace == "HSV":
            result = self._hsv_to_rgb(denoised)
        else:
            result = denoised
        
        # 元の入力範囲に戻す
        if input_max > input_min:
            result = result * (input_max - input_min) + input_min
        
        return result
    
    def _create_edge_mask(self, luma):
        """エッジマスクを作成"""
        # Sobelフィルタでエッジ検出
        if SCIPY_AVAILABLE:
            grad_x = sobel(luma, axis=1)
            grad_y = sobel(luma, axis=0)
            gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
            # 正規化（最小値と最大値を使用）
            min_val = gradient_magnitude.min()
            max_val = gradient_magnitude.max()
            if max_val > min_val:
                gradient_magnitude = (gradient_magnitude - min_val) / (max_val - min_val)
        else:
            gradient_magnitude = np.zeros_like(luma)
        
        # 閾値でエッジマスクを作成
        edge_mask = gradient_magnitude > self.edge_threshold
        return edge_mask
    
    def _gaussian_filter_nan(self, image, sigma):
        """ガウシアンフィルタ（NaN対応）"""
        nan_mask = np.isnan(image)
        if np.all(nan_mask):
            return image
        
        result = image.copy()
        if SCIPY_AVAILABLE and np.any(~nan_mask):
            # NaN以外の部分のみフィルタ適用
            temp_image = np.where(nan_mask, 0, image)
            filtered = gaussian_filter(temp_image, sigma)
            result = np.where(nan_mask, image, filtered)
        
        return result
    
    def _edge_preserving_filter_nan(self, image, sigma, edge_mask):
        """エッジ保護ガウシアンフィルタ（NaN対応）"""
        filtered = self._gaussian_filter_nan(image, sigma)
        # エッジ部分は元画像を保持
        return np.where(edge_mask, image, filtered)
    
    def _rgb_to_lab(self, rgb):
        """RGB to Lab変換（簡易版）"""
        # 入力は既に0.0-1.0に正規化済み
        rgb_norm = rgb
        
        # sRGB to XYZ
        xyz = np.zeros_like(rgb_norm)
        xyz[:,:,0] = 0.412453 * rgb_norm[:,:,0] + 0.357580 * rgb_norm[:,:,1] + 0.180423 * rgb_norm[:,:,2]
        xyz[:,:,1] = 0.212671 * rgb_norm[:,:,0] + 0.715160 * rgb_norm[:,:,1] + 0.072169 * rgb_norm[:,:,2]
        xyz[:,:,2] = 0.019334 * rgb_norm[:,:,0] + 0.119193 * rgb_norm[:,:,1] + 0.950227 * rgb_norm[:,:,2]
        
        # XYZ to Lab
        lab = np.zeros_like(xyz)
        lab[:,:,0] = 116 * np.cbrt(xyz[:,:,1]) - 16  # L
        lab[:,:,1] = 500 * (np.cbrt(xyz[:,:,0]) - np.cbrt(xyz[:,:,1]))  # a
        lab[:,:,2] = 200 * (np.cbrt(xyz[:,:,1]) - np.cbrt(xyz[:,:,2]))  # b
        
        return lab
    
    def _lab_to_rgb(self, lab):
        """Lab to RGB変換（簡易版）"""
        # Lab to XYZ
        xyz = np.zeros_like(lab)
        fy = (lab[:,:,0] + 16) / 116
        fx = lab[:,:,1] / 500 + fy
        fz = fy - lab[:,:,2] / 200
        
        xyz[:,:,0] = fx**3
        xyz[:,:,1] = fy**3
        xyz[:,:,2] = fz**3
        
        # XYZ to sRGB
        rgb = np.zeros_like(xyz)
        rgb[:,:,0] = 3.240479 * xyz[:,:,0] - 1.537150 * xyz[:,:,1] - 0.498535 * xyz[:,:,2]
        rgb[:,:,1] = -0.969256 * xyz[:,:,0] + 1.875992 * xyz[:,:,1] + 0.041556 * xyz[:,:,2]
        rgb[:,:,2] = 0.055648 * xyz[:,:,0] - 0.204043 * xyz[:,:,1] + 1.057311 * xyz[:,:,2]
        
        return np.clip(rgb, 0, 1)
    
    def _rgb_to_yuv(self, rgb):
        """RGB to YUV変換"""
        yuv = np.zeros_like(rgb)
        yuv[:,:,0] = 0.299 * rgb[:,:,0] + 0.587 * rgb[:,:,1] + 0.114 * rgb[:,:,2]  # Y
        yuv[:,:,1] = -0.147 * rgb[:,:,0] - 0.289 * rgb[:,:,1] + 0.436 * rgb[:,:,2]  # U
        yuv[:,:,2] = 0.615 * rgb[:,:,0] - 0.515 * rgb[:,:,1] - 0.100 * rgb[:,:,2]  # V
        return yuv
    
    def _yuv_to_rgb(self, yuv):
        """YUV to RGB変換"""
        rgb = np.zeros_like(yuv)
        rgb[:,:,0] = yuv[:,:,0] + 1.140 * yuv[:,:,2]  # R
        rgb[:,:,1] = yuv[:,:,0] - 0.394 * yuv[:,:,1] - 0.581 * yuv[:,:,2]  # G
        rgb[:,:,2] = yuv[:,:,0] + 2.032 * yuv[:,:,1]  # B
        return np.clip(rgb, 0, 1)
    
    def _rgb_to_hsv(self, rgb):
        """RGB to HSV変換"""
        # 入力は既に半開区間 [0.0, 1.0) に正規化済み
        rgb_norm = rgb
        hsv = np.zeros_like(rgb_norm)
        
        max_val = np.max(rgb_norm, axis=2)
        min_val = np.min(rgb_norm, axis=2)
        diff = max_val - min_val
        
        # V (Value)
        hsv[:,:,2] = max_val
        
        # S (Saturation)
        hsv[:,:,1] = np.where(max_val != 0, diff / max_val, 0)
        
        # H (Hue)
        h = np.zeros_like(max_val)
        mask = diff != 0
        
        # Red is max
        red_max = mask & (max_val == rgb_norm[:,:,0])
        h[red_max] = (rgb_norm[:,:,1][red_max] - rgb_norm[:,:,2][red_max]) / diff[red_max]
        
        # Green is max
        green_max = mask & (max_val == rgb_norm[:,:,1])
        h[green_max] = 2.0 + (rgb_norm[:,:,2][green_max] - rgb_norm[:,:,0][green_max]) / diff[green_max]
        
        # Blue is max
        blue_max = mask & (max_val == rgb_norm[:,:,2])
        h[blue_max] = 4.0 + (rgb_norm[:,:,0][blue_max] - rgb_norm[:,:,1][blue_max]) / diff[blue_max]
        
        h = h / 6.0
        h[h < 0] += 1.0
        hsv[:,:,0] = h
        
        return hsv
    
    def _hsv_to_rgb(self, hsv):
        """HSV to RGB変換"""
        # 入力は既に0.0-1.0に正規化済み
        hsv_norm = hsv
        h, s, v = hsv_norm[:,:,0], hsv_norm[:,:,1], hsv_norm[:,:,2]
        
        h = h * 6.0
        i = np.floor(h).astype(int)
        f = h - i
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        
        rgb = np.zeros_like(hsv_norm)
        
        idx = (i % 6) == 0
        rgb[idx] = np.stack([v[idx], t[idx], p[idx]], axis=-1)
        
        idx = (i % 6) == 1
        rgb[idx] = np.stack([q[idx], v[idx], p[idx]], axis=-1)
        
        idx = (i % 6) == 2
        rgb[idx] = np.stack([p[idx], v[idx], t[idx]], axis=-1)
        
        idx = (i % 6) == 3
        rgb[idx] = np.stack([p[idx], q[idx], v[idx]], axis=-1)
        
        idx = (i % 6) == 4
        rgb[idx] = np.stack([t[idx], p[idx], v[idx]], axis=-1)
        
        idx = (i % 6) == 5
        rgb[idx] = np.stack([v[idx], p[idx], q[idx]], axis=-1)
        
        return np.clip(rgb, 0, 1)
    
    def _create_result_flowdata(self, original_flowdata, denoised_rgb):
        """結果FlowDataを作成"""
        headers = original_flowdata.headers.copy()
        result_flowdata = FlowData(headers)
        
        width, height = original_flowdata.getDimensions()
        result_flowdata.setDimensions(width, height)
        
        # ブロック単位で結果を設定
        from config import BLOCK_SIZE
        for blockY in range(0, height, BLOCK_SIZE):
            for blockX in range(0, width, BLOCK_SIZE):
                endY = min(blockY + BLOCK_SIZE, height)
                endX = min(blockX + BLOCK_SIZE, width)
                
                for c in range(3):
                    block_data = denoised_rgb[blockY:endY, blockX:endX, c]
                    block = DataBlock(c, blockX, blockY, block_data)
                    result_flowdata.setBlock(block)
        
        return result_flowdata

class ChromaDenoiseSettingsDialog(tk.Toplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.text}設定")
        self.geometry("400x450")
        
        self.createWidgets()
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def createWidgets(self):
        # メインフレーム
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 設定フレーム
        settingsFrame = self.createCustomSettings(mainFrame)
        settingsFrame.pack(fill=tk.BOTH, expand=True)
        
        # ボタンフレーム
        buttonFrame = tk.Frame(self)
        buttonFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttonFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(buttonFrame, text="閉じる", command=self.destroy).pack(side=tk.LEFT, padx=5)
    
    def createCustomSettings(self, parent):
        if not parent:
            return tk.Frame()
        
        frame = tk.Frame(parent)
        
        # 色空間選択
        tk.Label(frame, text="色空間:").pack(anchor="w")
        self.colorspaceVar = tk.StringVar(value=self.node.colorspace)
        colorspaces = ["Lab - 知覚的均等色空間（推奨）", 
                      "YUV - 輝度・色差分離", 
                      "HSV - 色相・彩度・明度"]
        current_cs = next((cs for cs in colorspaces if cs.startswith(self.node.colorspace)), colorspaces[0])
        self.colorspaceVar.set(current_cs)
        ttk.Combobox(frame, textvariable=self.colorspaceVar, values=colorspaces, state="readonly").pack(fill=tk.X, pady=2)
        
        # 色成分ノイズ除去強度
        tk.Label(frame, text="色成分ノイズ除去強度:").pack(anchor="w", pady=(15,0))
        tk.Label(frame, text="色ノイズ（カラーノイズ）の除去強度", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.chromaVar = tk.DoubleVar(value=self.node.chroma_strength)
        tk.Scale(frame, from_=0.0, to=5.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.chromaVar).pack(fill=tk.X)
        
        # 輝度成分ノイズ除去強度
        tk.Label(frame, text="輝度成分ノイズ除去強度:").pack(anchor="w", pady=(10,0))
        tk.Label(frame, text="輝度ノイズの除去強度", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.lumaVar = tk.DoubleVar(value=self.node.luma_strength)
        tk.Scale(frame, from_=0.0, to=5.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.lumaVar).pack(fill=tk.X)
        
        # エッジ保護
        tk.Label(frame, text="エッジ保護:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(20,5))
        
        self.edgeVar = tk.BooleanVar(value=self.node.preserve_edges)
        tk.Checkbutton(frame, text="エッジ保護を有効にする", variable=self.edgeVar).pack(anchor="w")
        
        tk.Label(frame, text="エッジ検出閾値:").pack(anchor="w", pady=(10,0))
        tk.Label(frame, text="低いほど細かいエッジも保護（輝度値の変化率）", font=("Arial", 8), fg="gray").pack(anchor="w")
        self.thresholdVar = tk.DoubleVar(value=self.node.edge_threshold)
        tk.Scale(frame, from_=0.0, to=1.0, resolution=0.01, orient=tk.HORIZONTAL, variable=self.thresholdVar).pack(fill=tk.X)
        
        return frame
    
    def customOnApply(self):
        self.node.colorspace = self.colorspaceVar.get().split(' - ')[0]
        self.node.chroma_strength = self.chromaVar.get()
        self.node.luma_strength = self.lumaVar.get()
        self.node.preserve_edges = self.edgeVar.get()
        self.node.edge_threshold = self.thresholdVar.get()
        self.node.updateNodeText()
    
    def onApply(self):
        self.customOnApply()
        self.node.updateNodeText()
    
    def onClose(self):
        self.destroy()