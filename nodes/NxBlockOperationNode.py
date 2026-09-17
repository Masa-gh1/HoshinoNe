'''
NxBlockOperationNode base class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from itertools import zip_longest
from abc import abstractmethod
from concurrent.futures import as_completed

from base.FlowNode_CONST import *
from base import FlowNode

if TYPE_CHECKING:
    from base.DataBlock import DataBlock
    from base.FlowData import FlowData

class NxBlockOperationNode(FlowNode):
    """データ入出力 N:x のブロック単位計算ノードの基底クラス"""
    # ノードタイプ
    majorType = 'Nx_block_operation'
    minorType = 'Nx_block_operation'
    # ノード名
    name      = 'NxBlockOperationNode'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    @abstractmethod
    def process(self, context=None):
        """ノードの処理を実行（サブクラスで実装）
        
        Args:
            context: 処理コンテキスト（progress_callbackなど）
        """
        pass
    
    def preprocessStreams(self, inputStreams:list[list[FlowData]]) -> list[list[FlowData]]:
        """入力ストリームの前処理（サブクラスでオーバーライド可能）
        演算結果のデータタイプを primary 優先とするため、
        primary/auxiliaryで分類し、primaryを前に集める。
        
        Args:
            inputStreams: 入力ストリームのリスト
            
        Returns:
            処理対象ストリームのリスト
        """
        def getPriority(stream):
            category = stream[0].headers.get("category", _OUT_CAT_PRI)
            dataType = stream[0].headers.get("type", "table")
            n        = len(stream)
            
            if   _OUT_CAT_PRI == category: priority =     0
            elif _OUT_CAT_AUX == category: priority = 10000
            else                         : priority = 20000
            
            if   "tensor"     == dataType: priority += 1000
            elif "polynomial" == dataType: priority += 2000
            else                         : priority +=    0
            
            priority += max(0, min(999, 1000 - n))
            
            return priority
        
        streams = filter(lambda s: s, inputStreams)
        streams = sorted(streams, key=getPriority)
        return streams
    
    def preprocessStream(self, inputStream:list[FlowData]) -> list[FlowData]:
        """入力データの前処理(サブクラスでオーバーライド可能)
        
        Args:
            inputStream: 入力ストリーム
            
        Returns:
            処理対象データのリスト
        """
        return inputStream
    
    def createFlowData(self, inputDatas:FlowData|list[FlowData]) -> FlowData:
        """
        FlowDataを作成 (サブクラスでオーバーライド可能)
        
        Args:
            inputData: 入力FlowData
            
        Returns:
            FlowData
        """
        from base import FlowData
        
        _inputDatas = inputDatas if isinstance(inputDatas, (list,tuple)) else [inputDatas]
        
        # 基準データを決定
        baseDataIndex = self.getBaseDataIndex(_inputDatas)
        baseData = _inputDatas[baseDataIndex]

        # headers を生成
        headers = baseData.headers.copy() if baseData.headers else {}
        headers["category"] = self.getOutputCategory()
        headers.update(self.processHeaders(baseData, _inputDatas))

        # サイズを決定
        width, height = self.getOutputDimensions(baseData, _inputDatas)
        
        # 結果用の FlowData を生成
        flowData = FlowData(headers)
        flowData.setDimensions(width, height)
        
        return flowData
    
    def getBaseDataIndex(self, inputDatas:list[FlowData]) -> int:
        """
        基準データのインデックスを返す (サブクラスでオーバーライド可能)
        デフォルトは最もプレーン数が多いデータ
        
        Args:
            inputDatas: 入力データのリスト
            
        Returns:
            基準データのインデックス
        """
        baseDataIndex = 0
        maxPlaneCount = 0
        for i, data in enumerate(inputDatas):
            if maxPlaneCount < data.getPlaneCount():
                maxPlaneCount = data.getPlaneCount()
                baseDataIndex = i

        return baseDataIndex
    
    def getOutputDimensions(self, baseData:FlowData, inputDatas:list[FlowData]) -> tuple[int, int]:
        """
        結果画像のサイズを決定 (サブクラスでオーバーライド可能)
        デフォルトは全入力データを包含する最大サイズを計算

        Args:
            baseData: 基準データ
            inputDatas: 入力データのリスト
            
        Returns:
            結果のサイズ
        """
        import numpy as np
        from utils import numpy_helpers as nh

        # 全入力データの最大の型
        variableType = nh.BDTYPE
        for data in inputDatas:
            variableType = np.result_type(variableType, data.getVariableType())
        self._variableType = variableType
        
        # 全入力データを包含する最大サイズ
        width, height = inputDatas[0].getDimensions()
        for data in inputDatas[1:]:
            w, h = data.getDimensions()
            width  = max(width, w)
            height = max(height, h)
        self._outputDimensions = (width, height)
        return self._outputDimensions
    
        return width, height
    
    def processHeaders(self, baseData, inputDatas:list[FlowData]) -> dict:
        """
        出力 FlowData の headers を処理 (サブクラスでオーバーライド可能)
        
        Args:
            baseData: 基準データ
            inputDatas: 入力 FlowData

        Returns:
            出力 FlowData に追記する headers
        """
        return {}
