'''
StarIdentificationNode - 星同定ノード

画像から天体（星点）を検出し、星カタログ（HIP2等）と照合して確定した星のリストを生成するノード

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from types import SimpleNamespace

import hashlib

import tkinter as tk
from tkinter import messagebox

from base.FlowNode_CONST import *
from base import FlowNode
from nodes import ConfigurableNode

if TYPE_CHECKING:
    import numpy as np
    from utils.catalog_helper import Catalog
    from base.FlowData import FlowData

# 配列 index 定義
RA, DEC, MAG = 0, 1, 2 # カタログ配列
X, Y, BRI    = 0, 1, 2 # 点像配列
U, V, W      = 0, 1, 2 # 単位ベクトル配列
CIDX, PIDX   = 0, 1    # 同定配列

class StarIdentificationNode(FlowNode, ConfigurableNode):
    """画像から星を抽出し、カタログデータと照合して星リストを出力するノード"""
    
    # ノードタイプ
    majorType = _MAJOR_TYPE_FUNC
    minorType = 'star_identification'
    # ノード名
    name      = '星同定'
    # 入出力タイプ
    ioType    = _IO_TYPE_NN
    outputCat = _OUT_CAT_AUX
    
    def __init__(self, canvas, editor, x, y, **kwargs):
        super().__init__(canvas, editor, x, y, **kwargs)
        
        # 設定パラメーター
        # 画像パラメーター
        self.fovDeg                 = 2.0                   # 画角 [deg]
        self.useHeaderFovDeg        = True                  # 画像ヘッダから推定する
        
        # カタログ照合パラメーター
        self.catalog                = SimpleNamespace()
        self.catalog.matchLimit     = 1.0                   # カタログ照合許容比 [%]
        self.catalog.magLimit       = 8.0                   # 全球検索等級上限 [mag]
        self.catalog.addMagLimit    = 12.0                  # 同定する等級上限 [mag]
        
        # 点像選択パラメーター
        self.star                   = SimpleNamespace()
        self.star.grid              = SimpleNamespace()
        self.star.grid.rows         = 1                     # グリッド行数
        self.star.grid.cols         = 1                     # グリッド列数
        self.star.grid.searchPerGrid = 8                     # グリッド当たりの全球検索点像数
        self.star.grid.addPerGrid   = 30                    # グリッド当たりの同定する点像数
        self.star.minMatchedStars   = 5                     # 少なくとも同定したい星の数
        self.star.ransac            = SimpleNamespace()
        self.star.ransac.iterations = 100                   # RANSAC試行回数
        self.star.ransac.seed       = 2725                  # RANSAC乱数シード
    
    def getText(self):
        """ノードのテキストを取得"""
        displayText = f"{self.name}\nMatch:{self.catalog.matchLimit}% Mag:{self.catalog.magLimit}"
        return displayText

    def store(self, nodeData):
        """ノード設定を辞書に保存"""
        nodeData["fovDeg"             ] = self.fovDeg
        nodeData["useHeaderFovDeg"    ] = self.useHeaderFovDeg
        nodeData["catalog.matchLimit" ] = self.catalog.matchLimit
        nodeData["catalog.magLimit"   ] = self.catalog.magLimit
        nodeData["catalog.addMagLimit"] = self.catalog.addMagLimit
        nodeData["gridRows"           ] = self.star.grid.rows
        nodeData["gridCols"           ] = self.star.grid.cols
        nodeData["searchPerGrid"      ] = self.star.grid.searchPerGrid
        nodeData["addPerGrid"         ] = self.star.grid.addPerGrid
        nodeData["minMatchedStars"    ] = self.star.minMatchedStars
        nodeData["ransacIterations"   ] = self.star.ransac.iterations
        nodeData["ransacSeed"         ] = self.star.ransac.seed
    
    def restore(self, nodeData):
        """辞書からノード設定を復元"""
        if (val := nodeData.get("fovDeg"             )) is not None: self.fovDeg                  = val
        if (val := nodeData.get("useHeaderFovDeg"    )) is not None: self.useHeaderFovDeg         = val
        if (val := nodeData.get("catalog.matchLimit" )) is not None: self.catalog.matchLimit      = val
        if (val := nodeData.get("catalog.magLimit"   )) is not None: self.catalog.magLimit        = val
        if (val := nodeData.get("catalog.addMagLimit")) is not None: self.catalog.addMagLimit     = val
        if (val := nodeData.get("gridRows"           )) is not None: self.star.grid.rows          = val
        if (val := nodeData.get("gridCols"           )) is not None: self.star.grid.cols          = val
        if (val := nodeData.get("searchPerGrid"      )) is not None: self.star.grid.searchPerGrid = val
        if (val := nodeData.get("addPerGrid"         )) is not None: self.star.grid.addPerGrid    = val
        if (val := nodeData.get("minMatchedStars"    )) is not None: self.star.minMatchedStars    = val
        if (val := nodeData.get("ransacIterations"   )) is not None: self.star.ransac.iterations  = val
        if (val := nodeData.get("ransacSeed"         )) is not None: self.star.ransac.seed        = val
    
    def process(self, context=None):
        """星同定処理のメイン処理"""
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

        # カタログの準備
        catalog = self._getCatalog()

        # 各画像の星をカタログ照合
        outputFlowDatas = []
        totalImages     = len(inputStream)
        
        for i, flowData in enumerate(inputStream):
            self.reportProgress(context, f"画像 {i + 1}/{totalImages} 処理中", i, totalImages)

            # 点像配列作成
            import numpy as np
            points, pointsV, searchIdx = self.getPoints(flowData)
            
            # カタログ照合
            matchedStars, ransac = self.matchCatalog(pointsV, searchIdx, catalog)
            matchedIds     = catalog.getName(   matchedStars[:, CIDX])
            matchedCatalog = catalog.getCatalog(matchedStars[:, CIDX])
            matchedSarts   = points[            matchedStars[:, PIDX]]
            
            # デバッグ出力
            self.debug(flowData, matchedCatalog, matchedSarts, ransac)
            
            # 出力 Table の FlowData を作成
            flowData = self.createFlowData(flowData, catalog, matchedIds, matchedCatalog, matchedSarts)
            outputFlowDatas.append(flowData)

        self.flowDatas = outputFlowDatas
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

        self._catalogStream = auxiliaryStreams[0] if 0 < len(auxiliaryStreams) else None
        
        return primaryStreams
    
    def _getCatalog(self) -> Catalog:
        """カタログデータを取得（入力ストリームまたはファイルから）"""
        from utils import numpy_helpers as nh
        from utils.catalog_helper import Catalog
        if self._catalogStream and self._catalogStream[0]:
            flowData = self._catalogStream[0]
            width, height = flowData.getDimensions()
            
            planes  = flowData.headers["planes"]
            columns = flowData.headers["columns"]
            lines   = flowData.headers["lines"]
            raIdx   = columns.index("ra")
            decIdx  = columns.index("dec")
            magIdx  = columns.index("mag")
            
            # Table FlowData から配列化
            table = nh.nans((len(planes), height, width))
            for block in flowData.iterateBlocks():
                if block:
                    planeIndex = block.planeIndex
                    x, y = block.x, block.y
                    h, w = block.data.shape
                    table[planeIndex, y:y+h, x:x+w] = block.data
            
            symbol = planes[0]
            table = table.reshape((planes * height, width)) # plaen を縦に並べ替え
            table = table[:, [raIdx, decIdx, magIdx]] # RA, DEC, MAG の順に並べ替え
            
            return Catalog( symbol, table)
            
        # ファイルから読み込み
        return Catalog()

    def getPoints(self, flowData:FlowData) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
        """
        点像の配列を読み出し
        
        Args:
            flowData: 入力 FlowData
            
        Returns:
            points: 点像の配列 SHAPE=(N,M) [x, y, brightness,...],...]
            pointV: 点像への単位ベクトル SHAPE=(N,3) [[u, v, w],...]
            searchIdx: 検索対象点像のインデックス SHAPE=(M,)
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from utils import exif_helper as eh
        
        columnCnt, rowCnt = flowData.getDimensions()
        width, height = eh.getImageSize(flowData.headers)
        
        # 画像側の点像を読み込み
        points = nh.nans((rowCnt, columnCnt)) #  SHAPE=(N,M) [x, y, brightness,...],...]
        for block in flowData.iterateBlocks():
            if block:
                x, y = block.x, block.y
                h, w = block.data.shape
                points[y:y+h, x:x+w] = block.data
                
        select = []
        columns = flowData.headers["columns"]
        for name in ["x", "y", "brightness"]:
            idx = columns.index(name)
            select.append(points[:,idx])
        points = np.stack(select, axis=1) # SHAPE=(N,3) [x, y, brightness],...]
        
        # 点像を絞り込み
        pointsIdx, _  = self._selectDistributedPoints(points, width, height, self.star.grid.addPerGrid)
        points = points[pointsIdx]
        searchIdx, _  = self._selectDistributedPoints(points, width, height, self.star.grid.searchPerGrid)
        
        # レンズ中心からの単位 vector を追加
        if self.useHeaderFovDeg:
            # 画像のヘッダからレンズ中心と焦点距離を得て計算
            from utils import exif_helper as eh
            
            focalCenter_px   = eh.getFocalCenter(flowData.headers) # [px]
            focalLength_mm   = eh.getFocalLength(flowData.headers) # [mm]
            resolution_pxpmm = eh.getResolution(flowData.headers)  # [px/mm]
            if focalLength_mm is None or resolution_pxpmm is None:
                raise ValueError("画像のヘッダに焦点情報が設定されていません。")
            
            pointsX = (points[:, X] - focalCenter_px[0]) / resolution_pxpmm[0] # 中心を原点に [mm]
            pointsY = (points[:, Y] - focalCenter_px[1]) / resolution_pxpmm[1] # 中心を原点に [mm]
            f = float(focalLength_mm)                                        # 焦点距離 [mm]
            f = np.broadcast_to(f, pointsX.shape)
        else:
            # 設定値の画角から計算
            pointsX = points[:, X] - (width  / 2) # 中心を原点に [px]
            pointsY = points[:, Y] - (height / 2) # 中心を原点に [px]
            f = (width * width + height * height) ** 0.5 / (2.0 * np.tan(np.radians(self.fovDeg) / 2.0)) # 焦点距離を計算 [px]
            f = np.broadcast_to(f, pointsX.shape)
        pointsV = np.stack([pointsX, pointsY, f]).T
        pointsV = pointsV / np.linalg.norm(pointsV, axis=1, keepdims=True) # 単位ベクトルに変換 SHAPE=(N,3) [[u, v, w],...]
        
        return points, pointsV, searchIdx
    
    def _selectDistributedPoints(self, points:np.ndarray, width:int, height:int, pointsPerGrid:int) -> tuple[np.ndarray, list[int]]:
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

        gridRows, gridCols = self.star.grid.rows, self.star.grid.cols
        
        # 各グリッド領域のサイズ
        cellH = height // gridRows
        cellW = width  // gridCols
        
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
                whereIdx = gridIdx[:pointsPerGrid]
                distributedIdx.extend(whereIdx)
                gridSelectedCounts.append(len(whereIdx))
        
        distributedIdx = np.array(distributedIdx)
        
        return distributedIdx, gridSelectedCounts
    
    def matchCatalog(self, pointsV:np.ndarray, searchIdx:np.ndarray, catalog:Catalog) -> tuple[np.ndarray, dict]:
        """
        画像座標と天球座標の間で投影を行わず、
        幾何学的な相似の比較のみで全星の同定（インライア判定）を行う。
        これにより、レンズ歪みの影響を最小化する。
        
        Args:
            pointsV: 点像の座標と明度の配列 SHAPE=(N,3) [[u, v, w],...]
            searchIdx: 検索対象点像のインデックス配列 SHAPE=(N) [pidx,...]
            catalog: 星のカタログ情報
            
        Returns:
            match: 同定された星の配列 SHAPE=(N,2) [[cidx, pidx],...]
            ransac: RANSAC状況
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        if catalog.count() < 4:
            raise ValueError("少なくともカタログに 4 つ以上の星が必要です。")
        
        if len(searchIdx) < 4 or len(pointsV) < 4:
            raise ValueError("少なくとも 4 つ以上の点像が必要です。")
        
        # RANSAC用固定シードを設定
        random = np.random.default_rng(self.star.ransac.seed)
        
        # 探索結果
        bestMatchCount = 0
        bestMatchError = nh.inf
        bestMatchStars = np.array((0,2), dtype=np.uint32) # [(cidx, pidx),...]
        catalogTotal = 0
        
        # 4 点による 2 つの三角形のパターン
        COMB_TRIANGLE_PAIRS = np.array([
            [[0, 1, 2], [0, 1, 3]],
            [[0, 1, 3], [0, 1, 2]],
            [[0, 2, 1], [0, 2, 3]],
            [[0, 2, 3], [0, 2, 1]],
            [[0, 3, 1], [0, 3, 2]],
            [[0, 3, 2], [0, 3, 1]],
            [[1, 2, 0], [1, 2, 3]],
            [[1, 2, 3], [1, 2, 0]],
            [[1, 3, 0], [1, 3, 2]],
            [[1, 3, 2], [1, 3, 0]],
            [[2, 3, 0], [2, 3, 1]],
            [[2, 3, 1], [2, 3, 0]],
        ], dtype=np.int8)
        
        iterations = 0
        for iterations in range(self.star.ransac.iterations): # RANSAC試行回数
            # 画像側で 4 点をランダムに選択し接する時計回りの三角形 P と Q を作成する
            pqidx = random.choice(searchIdx, 4, replace=False)
            pqidx = pqidx[COMB_TRIANGLE_PAIRS]
            pq = pointsV[pqidx] # 3点2組の組み合わせ
            pq0x = pq[:, :, 0, U]
            pq0y = pq[:, :, 0, V]
            pq1x = pq[:, :, 1, U]
            pq1y = pq[:, :, 1, V]
            pq2x = pq[:, :, 2, U]
            pq2y = pq[:, :, 2, V]
            valid = np.all(((pq1x - pq0x) * (pq2y - pq0y) - (pq1y - pq0y) * (pq2x - pq0x)) < 0, axis=1) # 時計回り判定
            sel = random.choice(np.where(valid)[0]) # valid==True の中から1つを選択
            pidx = pqidx[sel, 0]
            qidx = pqidx[sel, 1]
            
            # 三角形 P を作成
            p = pointsV[pidx]
            p0, p1, p2 = p
            dp01 = self.calcAngDistance(p0[U:W+1], p1[U:W+1])
            dp12 = self.calcAngDistance(p1[U:W+1], p2[U:W+1])
            dp20 = self.calcAngDistance(p2[U:W+1], p0[U:W+1])
            dp = np.stack([dp01, dp12, dp20])
            if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)
            
            # 三角形 Q を作成
            q = pointsV[qidx]
            q0, q1, q2 = q
            dq01 = self.calcAngDistance(q0[U:W+1], q1[U:W+1])
            dq12 = self.calcAngDistance(q1[U:W+1], q2[U:W+1])
            dq20 = self.calcAngDistance(q2[U:W+1], q0[U:W+1])
            dq = np.stack([dq01, dq12, dq20])
            if np.any(dq < 1e-7) or np.min(dq) / np.max(dq) < 0.2: continue # 極端に短い辺が在るのでスキップ(検証に不適切)

            dp2q2 = self.calcAngDistance(p2[U:W+1], q2[U:W+1])
            if np.any(dp2q2 < 1e-7) or dp2q2 / np.max(dq) < 0.2: continue # 二つの三角形が近いのでスキップ(検証に不適切)

            # 三角形 P をカタログから検索し C とする
            cidx = catalog.searchTriangle(dp01, dp12, dp20, self.catalog.matchLimit/100.0, self.catalog.magLimit) # 相似な三角形を取得
            catalogTotal += 3 * len(cidx)
            if 0 == len(cidx): continue # 相似の三角形が見つからないのでスキップ

            # 三角形 Q をカタログから検索し G とする
            gidx = catalog.searchTriangle(dq01, dq12, dq20, self.catalog.matchLimit/100.0, self.catalog.magLimit) # 相似な三角形を取得
            catalogTotal += 3 * len(gidx)
            if 0 == len(gidx): continue # 相似の三角形が見つからないのでスキップ
            
            # C G の 1,2 点目共にが同じ ID 物を抽出
            c0idx = cidx[:, 0].astype(np.uint64)
            c1idx = cidx[:, 1].astype(np.uint64)
            g0idx = gidx[:, 0].astype(np.uint64)
            g1idx = gidx[:, 1].astype(np.uint64)
            c01Hash = c0idx * 0x9E3779B97F4A7C15 + c1idx # 2^64 / φ
            g01Hash = g0idx * 0x9E3779B97F4A7C15 + g1idx # 2^64 / φ
            _, cHashIdx, gHashIdx = np.intersect1d(c01Hash, g01Hash, return_indices=True)
            if 0 == len(cHashIdx) or 0 == len(gHashIdx): continue # 1辺を共有する三角形が見つからないのでスキップ
            
            whereIdx = random.choice(len(cHashIdx)) # 複数ある場合はランダムに選択
            cHashIdx = cHashIdx[whereIdx] # 複数ある場合はランダムに選択
            gHashIdx = gHashIdx[whereIdx] # 複数ある場合はランダムに選択
            cidx = cidx[cHashIdx]
            gidx = gidx[gHashIdx]
            
            # 画像 4 点とカタログ 4 点が相似だった
            currentInlierCount = 4
            currentMatched = np.array([[cidx[0],pidx[0]],
                                       [cidx[1],pidx[1]],
                                       [cidx[2],pidx[2]],
                                       [gidx[2],qidx[2]]], dtype=np.uint32)
            
            # 確定済み以外の点像配列を作成
            otherIdx = searchIdx[np.where(np.logical_not(np.isin(searchIdx, pidx) | np.isin(searchIdx, qidx)))]
            
            # 一致した点像に対し、画像内の全点像について位置関係をランダムに検証
            oIndices = random.choice(otherIdx, len(otherIdx), replace=False)
            for i, p0idx in enumerate(oIndices):
                if currentInlierCount + len(otherIdx) - i < bestMatchCount:
                    # このあと全て inlier でも bestMatchCount に届かないので早期終了 
                    break
                
                p0 = pointsV[p0idx]
                m1idx, m2idx = random.choice(len(currentMatched), 2, replace=False) # currentMatched の中からランダムに 2 つ選択する。
                c1idx = currentMatched[m1idx, CIDX]
                c2idx = currentMatched[m2idx, CIDX]
                p1idx = currentMatched[m1idx, PIDX]
                p2idx = currentMatched[m2idx, PIDX]
                p1 = pointsV[p1idx]
                p2 = pointsV[p2idx]
                
                if 0 < (p1[U] - p0[U]) * (p2[V] - p0[V]) - (p1[V] - p0[V]) * (p2[U] - p0[U]):
                    p1   ,p2    = p2   ,p1 # 時計回りに修正
                    p1idx,p2idx = p2idx,p1idx # インデックスも入れ替え
                    c1idx,c2idx = c2idx,c1idx # カタログ側も入れ替え
                
                dp01 = self.calcAngDistance(p0[U:W+1], p1[U:W+1])
                dp12 = self.calcAngDistance(p1[U:W+1], p2[U:W+1])
                dp20 = self.calcAngDistance(p2[U:W+1], p0[U:W+1])
                dp = np.stack([dp01, dp12, dp20])
                
                # 検証に不適切な三角形をスキップする
                if np.any(dp < 1e-7) or np.min(dp) / np.max(dp) < 0.2: continue # 極端に短い辺が在るのでスキップ
                
                # カタログから検索
                cidx = catalog.searchTriangle(dp01, dp12, dp20, self.catalog.matchLimit/100.0, self.catalog.magLimit, (None, c1idx, c2idx))
                catalogTotal += len(cidx)
                cidx = cidx[np.all(cidx[:,0,np.newaxis] != currentMatched[np.newaxis, :, CIDX], axis=1)] # 既知の点を除く
                if 0 < len(cidx):
                    cidx = random.choice(cidx) # 複数候補からランダムに選択
                    c0idx = cidx[0]
                elif currentInlierCount <= 4:
                    break # 安易に見つかるはずのタイミングで失敗したので早期終了
                else:
                    continue # 相似の三角形が見つからないのでスキップ
                
                currentInlierCount += 1
                currentMatched = np.concatenate([currentMatched, np.array([[c0idx,p0idx]], dtype=np.uint32)], axis=0)
                
                #重複チェック
                x1s, x2s = np.triu_indices(len(currentMatched), k=1) # 表の右上だけ選択
                for x1,x2 in zip(x1s,x2s):
                    assert np.all(currentMatched[x1,CIDX] != currentMatched[x2,CIDX]), "重複が発生しています。"
            
            # インライア数が閾値を超えた場合、モデル情報を更新
            if bestMatchCount <= currentInlierCount:
                pidx = currentMatched[:,PIDX]
                cidx = currentMatched[:,CIDX]
                # 誤差算出
                # 画像側とカタログ側の全ペア間角距離マトリクス (N x N)を作成
                p = pointsV[pidx, U:W+1]
                c = catalog.getCatalog(cidx)[:, RA:DEC+1]
                dp = self.calcAngDistance(   p[:, np.newaxis, :], p[np.newaxis, :, :])
                dc = catalog.angularDistance(c[:, np.newaxis, :], c[np.newaxis, :, :])
                assert isinstance(dc, np.ndarray), "this should be a numpy array"
                currentError = self.calcError( dp, dc)
                
                # インライア数が同じでも、誤差が小さい方が優先
                if bestMatchCount < currentInlierCount or currentError < bestMatchError:
                    bestMatchCount = currentInlierCount
                    bestMatchError = currentError
                    bestMatchStars = currentMatched
            
            if(   self.star.minMatchedStars <= bestMatchCount
                and bestMatchError < self.catalog.matchLimit/100.0
                and np.log(1-0.9999) / np.log(1 - (bestMatchCount/len(searchIdx))**self.star.minMatchedStars) < iterations # 初期一致数(最小インライア数 minMatchedStars)
                ):
                # 99.99% の確率で外れ値を除外するのに十分な試行回数に到達
                break
        
        # 確定済み以外の点像を同定する
        addMatchStars = bestMatchStars
        if 4 <= bestMatchCount:
            pidx = addMatchStars[:,PIDX]
            cidx = addMatchStars[:,CIDX]
            
            # 確定済み以外の点像配列を作成
            otherIdx = np.where(np.logical_not(np.isin(np.arange(len(pointsV)), pidx)))[0]
            
            # 確定済みの星の緯度経度を用いて、残りの点像の緯度経度を計算する
            p = pointsV[pidx, U:W+1]
            c = catalog.getCatalog(cidx)[:, RA:DEC+1]
            otherCrd   = self.calcCoords( pointsV[otherIdx], p, c)
            # catalogs の角距離から許容範囲を計算する。
            refDeg = np.median(catalog.angularDistance(c[:, np.newaxis, :], c[np.newaxis, :, :]))
            rdeg = refDeg * self.catalog.matchLimit/100.0
            for oidx, pidx in enumerate(otherIdx):
                # 閾値内にカタログ側の星が在るか確認
                cidx = catalog.queryStars(otherCrd[oidx, RA], otherCrd[oidx, DEC], rdeg, self.catalog.addMagLimit)
                cidx = cidx[~np.isin(cidx, addMatchStars[:,CIDX])]
                if 0 == len(cidx): continue # 閾値内にカタログが見つからないのでスキップ
                
                # 複数候補がある場合は一番近い星を選択
                cidx = cidx[np.argmin(catalog.angularDistance(otherCrd[oidx, RA:DEC+1], catalog.getCatalog(cidx)[:, RA:DEC+1]))]
                
                addMatchStars = np.concatenate([addMatchStars, np.array([[cidx,pidx]], dtype=np.uint32)], axis=0)
            
            #重複チェック
            x1s, x2s = np.triu_indices(len(addMatchStars), k=1) # 表の右上だけ選択
            for x1,x2 in zip(x1s,x2s):
                assert np.all(addMatchStars[x1,CIDX] != addMatchStars[x2,CIDX]), "重複が発生しています。"
        
        return addMatchStars, {"points": len(pointsV), "inlier": bestMatchCount, "search": len(searchIdx), "catalog": catalogTotal, "error": bestMatchError, "iterations": iterations+1}
    
    def calcAngDistance(self, vector0:np.ndarray, vector1:np.ndarray) -> np.ndarray:
        """2点への単位 vector の角距離を求める
        Args:
            vector0: 1つ目の単位 vector [[x,y,z],...]
            vector1: 2つ目の単位 vector [[x,y,z],...]
        Returns:
            2点間の角距離 (度)
        """
        import numpy as np
        cosTheta = np.vecdot(vector0, vector1)  # ベクトルの内積 x1*x2 + y1*y2 + z1*z2
        cosTheta = np.clip(cosTheta, -1.0, 1.0) # 浮動小数点誤差により -1.0 未満や 1.0 を超えることがあるのでクリップ
        return np.degrees(np.arccos(cosTheta))
    
    def calcCoords(self, p:np.ndarray, refP:np.ndarray, refC:np.ndarray) -> np.ndarray:
        """画像側の点像の座標から、カタログ側の緯度経度を計算する
        
        Args:
            p: 画像側の点像の座標 [[u, v, w],...]
            refP: 参照画像の点像の座標 [[u, v, w],...]
            refC: 参照カタログの座標 [[ra, dec],...]
        Returns:
            計算されたカタログの座標 [[ra, dec],...]
        """
        import numpy as np
        from utils import numpy_helpers as nh
        from utils.catalog_helper import Catalog
        
        center  = np.mean(refC[:,RA:DEC+1], axis=0)
        refXi, refEta = Catalog.gnomonicProjection(refC[:, RA], refC[:, DEC], center[RA], center[DEC])
        
        refU = refP[:, U] / refP[:, W]
        refV = refP[:, V] / refP[:, W]
        
        # アフィン変換
        # xi  = A*u + B*v + C
        # eta = D*u + E*v + F
        mat = np.stack([refU, refV, np.ones(len(refU))], axis=1)
        coeff_xi , _, _, _ = np.linalg.lstsq(mat, refXi,  rcond=None)
        coeff_eta, _, _, _ = np.linalg.lstsq(mat, refEta, rcond=None)
        
        u = p[:, U] / p[:, W]
        v = p[:, V] / p[:, W]

        xi  = coeff_xi[ 0] * u + coeff_xi[ 1] * v + coeff_xi[ 2]
        eta = coeff_eta[0] * u + coeff_eta[1] * v + coeff_eta[2]
        
        ra, dec = Catalog.gnomonicDeprojection(xi, eta, center[RA], center[DEC])
        return np.stack([ra, dec], axis=1)

    def calcError(self, d0:np.ndarray, d1:np.ndarray) -> float:
        """星の配置から誤差を計算する
        
        Args:
            d0: 星が作る形の辺長
            d1: 星が作る形の辺長
        Returns:
            誤差
        """
        import numpy as np
        from utils import numpy_helpers as nh
        
        assert len(d0) == len(d1), "Arrays must be of the same length"
        
        # カタログ側で 2σ 以上離れた角距離を排除
        x1, x2 = np.triu_indices(len(d1), k=1) # 表の右上だけ選択
        d1h = d1[x1, x2]
        d1h = np.sort(d1h)[:len(d1)] # 簡単な図形で考えた場合、外周は短い辺となるので、短い側を採用して統計を採る
        mean = np.mean(d1h)
        std = np.std(d1h)
        valid = (0 < d1) & (d1 < mean + 2.0 * std) # カタログ側で 2σ より短い接続を残す
        # 全点で隣接する2辺の角距離で比を計算する
        d0Ratio = []
        d1Ratio = []
        
        for j in range(len(d1)):
            xIdx = np.where(valid[j])[0]
            if 2 <= len(xIdx):
                x1, x2 = np.triu_indices(len(xIdx), k=1) # 表の右上だけ選択
                x1idx = xIdx[x1]
                x2idx = xIdx[x2]
                d0Ratio.extend(d0[j, x1idx] / d0[j, x2idx]) # 画像側2辺の比
                d1Ratio.extend(d1[j, x1idx] / d1[j, x2idx]) # カタログ側2辺の比
        
        if 0 == len(d0Ratio) or 0 == len(d1Ratio):
            error = np.inf
        else:
            d0Ratio = nh.array(d0Ratio)
            d1Ratio = nh.array(d1Ratio)
            # RMS を計算し error 値とする
            diff = (d0Ratio - d1Ratio) / d0Ratio # 分母に画像側を持ってきているのはカタログ検索(catalog.searchTriangle)の仕様に合わせる為
            error = np.sqrt(np.mean(diff**2))
        
        return error
    
    def createFlowData(self, inputData:FlowData, catalog:Catalog, matchedIds:np.ndarray, matchedCatalog:np.ndarray, matchedStars:np.ndarray) -> FlowData:
        """星リストから Table 型 FlowData を作成"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        from base import FlowData
        
        # 等級でソート
        sortedIdx = np.argsort(matchedCatalog[:,MAG])
        matchedIds     = matchedIds[sortedIdx]
        matchedCatalog = matchedCatalog[sortedIdx]
        matchedStars   = matchedStars[sortedIdx]
        
        columns = ['ra', 'dec', 'mag', 'x', 'y', 'brightness']
        lines   = [f"{id}" for id in matchedIds]
        
        tableRows = []
        for cat, str in zip(matchedCatalog, matchedStars):
            row = [
                cat[RA ],
                cat[DEC],
                cat[MAG],
                str[X  ],
                str[Y  ],
                str[BRI],
            ]
            tableRows.append(row)
        
        if 0 < len(tableRows):
            tableArray = nh.array(tableRows, dtype=nh.BDTYPE)
        else:
            tableArray = nh.zeros((0, len(columns)), dtype=nh.BDTYPE)
        
        # headers を生成
        headers = inputData.headers.copy()
        headers.update({
            'category': self.getOutputCategory(),
            'type'    : 'table',
            'mode'    : '2D',
            'columns' : columns,
            'lines'   : lines,
            'planes'  : ['star_identification'],
        })
        
        flowData = FlowData(headers)
        rows, cols = tableArray.shape
        flowData.setDimensions(cols, rows)
        
        for y in range(0, rows, BLOCK_SIZE):
            blockHeight = min(BLOCK_SIZE, rows - y)
            blockData   = tableArray[y:y + blockHeight, :]
            flowData.setBlock(DataBlock(blockData, 0, 0, y))
        
        return flowData
    
    def debug(self, flowData:FlowData, matchedCatalog:np.ndarray, matchedStars:np.ndarray, ransac:dict):
        from utils.Debug import Debug
        if Debug.isTestMode() or Debug.LEVEL_NONE < Debug.LEVEL:
            import numpy as np
            from utils.catalog_helper import Catalog
            
            # RANSAC 結果から向きと画角を推定する(デバッグ用)
            import cv2
            from utils import numpy_helpers as nh
            from utils import exif_helper as eh
            
            width, height = eh.getImageSize(flowData.headers)
            
            src_pts = nh.array([[star[X ], star[Y  ]] for star in matchedStars])
            dst_pts = nh.array([[star[RA], star[DEC]] for star in matchedCatalog])
            M, inliers_mask = cv2.estimateAffine2D(src_pts, dst_pts)
            if M is not None:
                center = nh.array([width / 2.0, height / 2.0, 1.0])
                coords = M @ center
                est_ra, est_dec = coords[0], coords[1]
            else:
                est_ra, est_dec = np.mean(dst_pts[:, 0]), np.mean(dst_pts[:, 1])
            
            p = matchedStars
            c = matchedCatalog
            
            dc = [
                Catalog.angularDistance(c[0][RA:DEC+1], c[1][RA:DEC+1]),
                Catalog.angularDistance(c[1][RA:DEC+1], c[2][RA:DEC+1]),
                Catalog.angularDistance(c[2][RA:DEC+1], c[0][RA:DEC+1]),
            ]
            dcMean = np.mean(dc)
            
            dp = [
                np.hypot(p[0][X]-p[1][X], p[0][Y]-p[1][Y]),
                np.hypot(p[1][X]-p[2][X], p[1][Y]-p[2][Y]),
                np.hypot(p[2][X]-p[0][X], p[2][Y]-p[0][Y]),
            ]
            apMean = np.mean(dp)
            
            est_fov  = np.hypot(width, height) * (dcMean / apMean)
            
            m = int(np.ceil(np.log10(ransac["points"])))
            n = int(np.ceil(np.log10(ransac["search"])))
            debug  = f"estimated"
            debug += f" ra:{ est_ra :-07.3f}"
            debug += f" dec:{est_dec:+07.3f}"
            debug += f" fov:{est_fov:-07.3f}"
            debug += f" ransac:"
            debug += f" match:{len(matchedStars):0{m}d}"
            debug += f" inlier:{ransac["inlier"]:0{n}d}/{ransac["search"]:0{n}d}"
            debug += f" catalog:{ransac["catalog"]//ransac["iterations"]}"
            debug += f" error:{ransac["error"]:0.3f}"
            debug += f" iter:{ransac["iterations"]}"
            Debug.log(type(self).__name__, f"{debug}")
    
    def createSettingWindow(self):
        """設定ダイアログを作成"""
        return StarIdentificationSettingsDialog(self.view.editor.root, self)
    
    def getConfigHash(self):
        config =(f"{self.minorType}_"
                 f"{self._outputCat}_"
                 f"{self.fovDeg}_"
                 f"{self.useHeaderFovDeg}_"
                 f"{self.catalog.matchLimit}_"
                 f"{self.catalog.magLimit}_"
                 f"{self.catalog.addMagLimit}_"
                 f"{self.star.grid.rows}_"
                 f"{self.star.grid.cols}_"
                 f"{self.star.grid.searchPerGrid}_"
                 f"{self.star.grid.addPerGrid}_"
                 f"{self.star.minMatchedStars}"
                 f"{self.star.ransac.iterations}_"
                 f"{self.star.ransac.seed}_"
                )
        return hashlib.md5(config.encode()).hexdigest()

class StarIdentificationSettingsDialog(tk.Toplevel):
    """StarIdentificationNode 用設定ダイアログ"""
    
    def __init__(self, parent, node:StarIdentificationNode):
        super().__init__(parent)
        self.node = node
        self.title(f"{node.name} 設定")
        self.geometry("450x450")
        
        self._createWidgets()
    
    def _createWidgets(self):
        """UI ウィジェットを生成"""
        mainFrame = tk.Frame(self)
        mainFrame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 画像パラメーター
        tk.Label(mainFrame, text="■ 画像パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 画角
        fovDegFrame = tk.Frame(mainFrame)
        fovDegFrame.pack(fill=tk.X, pady=2)
        tk.Label(fovDegFrame, text="  画角:").pack(side=tk.LEFT)
        self.fovDegEntry = tk.Entry(fovDegFrame, width=6)
        self.fovDegEntry.insert(0, str(self.node.fovDeg))
        self.fovDegEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(fovDegFrame, text="deg").pack(side=tk.LEFT)
        self.useHeaderFovDegVar = tk.BooleanVar(value=self.node.useHeaderFovDeg)
        tk.Checkbutton(fovDegFrame, text="ヘッダー情報から画角を推定", variable=self.useHeaderFovDegVar).pack(side=tk.LEFT)
        
        # カタログ照合パラメーター
        tk.Label(mainFrame, text="■ カタログ照合パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        
        # 許容半径
        radFrame = tk.Frame(mainFrame)
        radFrame.pack(fill=tk.X, pady=2)
        tk.Label(radFrame, text="  照合許容半径:").pack(side=tk.LEFT)
        self.catalogMatchLimitEntry = tk.Entry(radFrame, width=6)
        self.catalogMatchLimitEntry.insert(0, str(self.node.catalog.matchLimit))
        self.catalogMatchLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(radFrame, text="% (カタログとのズレ許容比)").pack(side=tk.LEFT)
        
        # 全球検索等級上限
        magFrame = tk.Frame(mainFrame)
        magFrame.pack(fill=tk.X, pady=2)
        tk.Label(magFrame, text="  全球検索等級上限:").pack(side=tk.LEFT)
        self.magLimitEntry = tk.Entry(magFrame, width=6)
        self.magLimitEntry.insert(0, str(self.node.catalog.magLimit))
        self.magLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(magFrame, text="mag (索引を用いた全球検索の等級上限)").pack(side=tk.LEFT)
        
        # 同定する等級上限
        magFrame = tk.Frame(mainFrame)
        magFrame.pack(fill=tk.X, pady=2)
        tk.Label(magFrame, text="  同定する等級上限:").pack(side=tk.LEFT)
        self.addMagLimitEntry = tk.Entry(magFrame, width=6)
        self.addMagLimitEntry.insert(0, str(self.node.catalog.addMagLimit))
        self.addMagLimitEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(magFrame, text="mag (検索後に追加で同定する等級上限)").pack(side=tk.LEFT)
        
        # 星像選択パラメーター
        tk.Label(mainFrame, text="■ 星像選択パラメーター", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(8, 2))
        
        # グリッド設定
        gridFrame = tk.Frame(mainFrame)
        gridFrame.pack(fill=tk.X, pady=2)
        tk.Label(gridFrame, text="  グリッド:").pack(side=tk.LEFT)
        self.gridRowsEntry = tk.Entry(gridFrame, width=5)
        self.gridRowsEntry.insert(0, str(self.node.star.grid.rows))
        self.gridRowsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="x").pack(side=tk.LEFT)
        self.gridColsEntry = tk.Entry(gridFrame, width=5)
        self.gridColsEntry.insert(0, str(self.node.star.grid.cols))
        self.gridColsEntry.pack(side=tk.LEFT, padx=2)
        tk.Label(gridFrame, text="(星像選択用分割数)").pack(side=tk.LEFT)
        
        # グリッド当たりの全球検索星数
        starsFrame = tk.Frame(mainFrame)
        starsFrame.pack(fill=tk.X, pady=2)
        tk.Label(starsFrame, text="  グリッド当たり全球検索星数:").pack(side=tk.LEFT)
        self.searchPerGridEntry = tk.Entry(starsFrame, width=5)
        self.searchPerGridEntry.insert(0, str(self.node.star.grid.searchPerGrid))
        self.searchPerGridEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから全球検索する星数の上限)").pack(side=tk.LEFT)
        
        # グリッド当たりの同定する星数
        starsFrame = tk.Frame(mainFrame)
        starsFrame.pack(fill=tk.X, pady=2)
        tk.Label(starsFrame, text="  グリッド当たり同定する星数:").pack(side=tk.LEFT)
        self.addPerGridEntry = tk.Entry(starsFrame, width=5)
        self.addPerGridEntry.insert(0, str(self.node.star.grid.addPerGrid))
        self.addPerGridEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(starsFrame, text="個 (各グリッドから同定する星数の上限)").pack(side=tk.LEFT)
        
        # 少なくとも同定したい星の数
        minMatchedStarsFrame = tk.Frame(mainFrame)
        minMatchedStarsFrame.pack(fill=tk.X, pady=2)
        tk.Label(minMatchedStarsFrame, text="  少なくとも同定したい星の数:").pack(side=tk.LEFT)
        self.minMatchedStarsEntry = tk.Entry(minMatchedStarsFrame, width=5)
        self.minMatchedStarsEntry.insert(0, str(self.node.star.minMatchedStars))
        self.minMatchedStarsEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(minMatchedStarsFrame, text="個 (検索の終了を許可する数)").pack(side=tk.LEFT)
        
        # RANSAC試行回数
        ransacFrame = tk.Frame(mainFrame)
        ransacFrame.pack(fill=tk.X, pady=2)
        tk.Label(ransacFrame, text="  RANSAC試行回数:").pack(side=tk.LEFT)
        self.ransacEntry = tk.Entry(ransacFrame, width=5)
        self.ransacEntry.insert(0, str(self.node.star.ransac.iterations))
        self.ransacEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(ransacFrame, text="回 (外れ値耐性用繰り返し回数)").pack(side=tk.LEFT)
        
        # RANSAC乱数シード
        seedFrame = tk.Frame(mainFrame)
        seedFrame.pack(fill=tk.X, pady=2)
        tk.Label(seedFrame, text="  RANSAC乱数シード:").pack(side=tk.LEFT)
        self.ransacSeedEntry = tk.Entry(seedFrame, width=5)
        self.ransacSeedEntry.insert(0, str(self.node.star.ransac.seed))
        self.ransacSeedEntry.pack(side=tk.LEFT, padx=5)
        tk.Label(seedFrame, text="(1以上、結果が悪い場合は変更)").pack(side=tk.LEFT)

        # ボタンフレーム
        btnFrame = tk.Frame(self)
        btnFrame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(btnFrame, text="適用", command=self.onApply).pack(side=tk.LEFT, padx=5)
        tk.Button(btnFrame, text="閉じる", command=self.onClose).pack(side=tk.LEFT, padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.onClose)
    
    def onApply(self):
        """適用ボタンクリックハンドラ"""
        try:
            from config import CATALOG_DB_MAG
            self.node.fovDeg                   = max(0.01, float(self.fovDegEntry.get()))
            self.node.useHeaderFovDeg          = self.useHeaderFovDegVar.get()
            self.node.catalog.matchLimit       = max(0.001, min(99.0, float(self.catalogMatchLimitEntry.get())))
            self.node.catalog.magLimit         = max(1, min(CATALOG_DB_MAG, float(self.magLimitEntry.get())))
            self.node.catalog.addMagLimit      = max(1, min(20, float(self.addMagLimitEntry.get())))
            self.node.star.grid.rows           = max(1, int(self.gridRowsEntry.get()))
            self.node.star.grid.cols           = max(1, int(self.gridColsEntry.get()))
            self.node.star.grid.searchPerGrid  = max(1, int(self.searchPerGridEntry.get()))
            self.node.star.grid.addPerGrid     = max(1, int(self.addPerGridEntry.get()))
            self.node.star.minMatchedStars     = max(4, min(100, int(self.minMatchedStarsEntry.get())))
            self.node.star.ransac.iterations   = max(10, min(10000, int(self.ransacEntry.get())))
            self.node.star.ransac.seed         = max(1, int(self.ransacSeedEntry.get()))
            
            self.node.view.onNodeConfigChanged(self.node)
        except ValueError:
            messagebox.showerror("エラー", "入力値が正しくありません")
    
    def onClose(self):
        """ダイアログを閉じる"""
        self.destroy()
