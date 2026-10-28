'''
QuantileFilterNode - 分位数濾過

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import hashlib

import tkinter as tk
from tkinter import messagebox

from base.FlowNode_CONST import *
from nodes import NNPlaneOperationNode
from config import MAX_WORKERS

class QuantileFilterNode(NNPlaneOperationNode):
    # ノードタイプ
    majorType = _MAJOR_TYPE_NEIBR
    minorType = 'quantile_filter'
    # ノード名
    name      = '分位数濾過'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承
    
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        self.quantile               = 0.5               # 分位数 (概算時は 0.5 固定、カーネルは正方形のみ)
        self.useApproximation       = False             # 概算を使う
        self.approximation          = 1                 # 概算回数
    
    def getText(self):
        """ノードのテキストを取得"""
        if self.useApproximation:
            displayText = f"{self.name}\n概算:{self.approximation} q:0.5"
        else:
            displayText = f"{self.name}\nq:{self.quantile}"
        return displayText
    
    def store(self, nodeData):
        """ノード設定を辞書に保存"""
        nodeData["quantile"]         = self.quantile
        nodeData["useApproximation"] = self.useApproximation
        nodeData["approximation"]    = self.approximation

    def restore(self, nodeData):
        """辞書からノード設定を復元"""
        self.quantile         = nodeData.get("quantile"        , self.quantile        )
        self.useApproximation = nodeData.get("useApproximation", self.useApproximation)
        self.approximation    = nodeData.get("approximation"   , self.approximation   )
        
    def planeOperation(self, flowDatas, planeIndex):
        """分位数濾過処理"""
        import numpy as np
        from config import BLOCK_SIZE
        from base import DataBlock
        from utils import numpy_helpers as nh
        
        flowData = flowDatas[0]
        auxData  = flowDatas[1]
        
        width, height = flowData.getDimensions()
        
        # データを読み込み
        planeData = nh.empty((height, width))
        
        for block in flowData.iterateBlocks(planeIndex):
            blockHeight = min(block.getHeight(), height - block.y)
            blockWidth  = min(block.getWidth() , width  - block.x)
            endY = block.y + blockHeight
            endX = block.x + blockWidth
            planeData[block.y:endY, block.x:endX] = block.data[:blockHeight, :blockWidth]
        
        # 補正データを読み込み
        auxW, auxH = auxData.getDimensions()
        auxPlanCnt = auxData.getPlaneCount()
        
        auxPlane = nh.empty((auxH, auxW))
        
        auxPlaneIdx = 0 if 1 == auxPlanCnt else planeIndex # 補正データが 1 プレーンだけの場合、全プレーンに同じ補正データを適用する
        for block in auxData.iterateBlocks(auxPlaneIdx):
            x = block.x
            y = block.y
            blockWidth  = min(block.getWidth() , auxW - x)
            blockHeight = min(block.getHeight(), auxH - y)
            endX = block.x + blockWidth
            endY = block.y + blockHeight
            auxPlane[y:endY, x:endX] = block.data[:blockHeight, :blockWidth]
        
        if np.uint8 == planeData.dtype and self.useApproximation:
            import cv2
            k = np.max(auxPlane.shape)
            result = cv2.medianBlur(planeData, k) # 分位数濾過
        elif self.useApproximation:
            import cv2
            # 中央値 概算 なので、uint8 にスケールして cv2.medianBlur で概算
            k      = np.max(auxPlane.shape)
            offset = np.nanmin(planeData)
            endV   = np.nanmax(planeData) * (1.0 + nh.epsilon)
            scale  = (256.0 / (endV - offset))
            approx = self.approximation
            # 作業用メモリを確保
            tmp        = nh.empty((height, width))
            planeUByte = np.empty((height, width), dtype=np.uint8)
            resUByte   = np.empty((height, width), dtype=np.uint8)
            result     = nh.zeros((height, width))
            # NaN を 0 で補完
            np.nan_to_num(planeData, nan=0, copy=False)
            for i in range(approx):
                # 少しづつズラして中央値を得て誤差を分散させる
                a = (i - (approx - 1) / 2.0) / approx / scale
                np.add(planeData, -(offset + a), out=tmp)
                tmp *= scale
                planeUByte[:] = tmp.astype(np.uint8) # キャスト
                cv2.medianBlur(planeUByte, k, dst=resUByte) # 分位数濾過
                tmp[:] = resUByte # キャスト
                tmp /= approx * scale
                tmp += (offset + a) / approx
                result += tmp
        elif False:
            # cv2.medianBlur を使って float32 を計算する。
            import cv2
            planeUlong = planeData.view(np.uint32).reshape((height, width))
            maskB        = (0 == planeUlong & 0x80000000)
            planeUlong[ maskB] ^= 0x80000000 # 符号ビットを反転
            planeUlong[~maskB] ^= 0xFFFFFFFF # 符号ビットを反転
            planeUbyte = (planeUlong >> 24).astype(np.uint8)
            resultUbyte = cv2.medianBlur(planeUbyte, auxPlane.shape[0]) # 分位数濾過
            resultUlong = resultUbyte.astype(np.uint32) << 24
            maskB         = (0 == resultUlong & 0x80000000)
            resultUlong[ maskB] ^= 0xFFFFFFFF # 符号ビットを反転
            resultUlong[~maskB] ^= 0x80000000 # 符号ビットを反転
            result = resultUlong.view(np.float32).reshape((height, width))
        else:
            q      = self.quantile
            kh, kw = auxPlane.shape
            kCount = int(np.sum(~np.isnan(auxPlane))) # カーネルの nan 以外の数
            result = nh.nans((height, width))
            size = int(np.floor(np.sqrt(8*1024*1204 // MAX_WORKERS // (planeData.itemsize * kh * kw))))
            if 0 == size: size = 1
            tmpA  = nh.empty((size+(kh-1), size+(kw-1)))
            tmpB  = nh.empty((size, size, kh,  kw))
            maskB = np.empty((size, size, kh * kw), dtype=np.bool)
            
            for y in range(0, height, size):
                for x in range(0, width, size):
                    h = min(size, height - y)
                    w = min(size, width  - x)
                    ay, ah = y-(kh-1)//2, h+(kh-1)
                    ax, aw = x-(kw-1)//2, w+(kw-1)
                    by = max(ay, 0)
                    bx = max(ax, 0)
                    bh = min(ah-(by-ay), height - by)
                    bw = min(aw-(bx-ax), width  - bx)
                    if ay == by and ax == bx and ah == bh and aw == bw:
                        tmpA[:] = planeData[by:by+bh, bx:bx+bw]
                    else:
                        tmpA[:] = nh.nan
                        tmpA[by-ay:by-ay+bh, bx-ax:bx-ax+bw] = planeData[by:by+bh, bx:bx+bw]
                    maskA = np.isnan(tmpA)
                    tmpAV = np.lib.stride_tricks.sliding_window_view(tmpA, window_shape=(kh, kw), axis=(0,1))
                    tmpB[:] = tmpAV[:] * auxPlane[np.newaxis, np.newaxis, :, :]
                    tmpBV = tmpB.reshape(*tmpB.shape[:-2], kh * kw)
                    tmpBV = tmpBV[:h,:w, :]
                    if np.any(maskA):
                        maskBV = maskB[:h,:w, :]
                        np.isnan(tmpBV, out=maskBV)
                        tmpBV[maskBV] = nh.inf
                        tmpBV.sort(axis=-1)
                        validCnt = (kh * kw) - np.sum(maskBV, axis=-1)
                        idx = np.round(q * (np.maximum(1, validCnt) - 1)).astype(np.uint16)
                        qua = np.take_along_axis(tmpBV, idx[..., np.newaxis], axis=-1).squeeze(-1) # 分位数濾過
                        qua[validCnt == 0] = np.nan
                    else:
                        if kCount < kh * kw:
                            tmpBV[np.isnan(tmpBV)] = nh.inf
                        idx = int(np.round(q * (kCount - 1)))
                        tmpBV.partition(idx, axis=-1) # ソートの代わりに idx 位置でパーティション
                        qua = tmpBV[..., idx] # 分位数濾過
                    result[y:y+h, x:x+w] = qua[:h, :w]
        
        blocks = []
        for y in range(0, height, BLOCK_SIZE):
            for x in range(0, width, BLOCK_SIZE):
                blockHeight = min(BLOCK_SIZE, height - y)
                blockWidth  = min(BLOCK_SIZE, width  - x)
                endY = y + blockHeight
                endX = x + blockWidth
                dataBlock = DataBlock(result[y:endY, x:endX], planeIndex=planeIndex, x=x, y=y)
                blocks.append(dataBlock)
        
        return blocks

    def createSettingWindow(self):
        """設定ダイアログを作成"""
        return QuantileFilterSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config =(f"{self.minorType}_"
                 f"{self._outputCat}_"
                 f"{self.quantile}_"
                 f"{self.useApproximation}_"
                 f"{self.approximation}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class QuantileFilterSettingsDialog(tk.Toplevel):
    """QuantileFilterNode 用設定ダイアログ"""
    
    def __init__(self, parent, node:QuantileFilterNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("450x200")
        
        self._createWidgets()
    
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 分位数
        approximationFrame = tk.Frame(mainFrame)
        approximationFrame.pack(fill=tk.X, pady=2)
        tk.Label(approximationFrame, text="分位数:").pack(side=tk.LEFT)
        self.quantileEntry = tk.Entry(approximationFrame, width=6)
        self.quantileEntry.insert(0, str(self.node.quantile))
        self.quantileEntry.pack(side=tk.LEFT, padx=4)
        
        # 概算
        approximationFrame = tk.Frame(mainFrame)
        approximationFrame.pack(fill=tk.X, pady=2)
        tk.Label(approximationFrame, text="概算を使う:").pack(side=tk.LEFT)
        self.useApproximationVar = tk.BooleanVar(value=self.node.useApproximation)
        tk.Checkbutton(approximationFrame, text="概算回数:", variable=self.useApproximationVar).pack(side=tk.LEFT)
        self.approximationEntry = tk.Entry(approximationFrame, width=3)
        self.approximationEntry.insert(0, str(self.node.approximation))
        self.approximationEntry.pack(side=tk.LEFT, padx=4)
        tk.Label(approximationFrame, text="分位数は 0.5 固定、カーネルは正方形のみ").pack(side=tk.LEFT)
        
        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            self.node.quantile         = max(0.0, float(self.quantileEntry.get()))
            self.node.useApproximation = self.useApproximationVar.get()
            self.node.approximation    = max(1, int(self.approximationEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
