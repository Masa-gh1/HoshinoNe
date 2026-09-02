'''
FlowDataWrapper class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING, Iterator

from .FlowData import FlowData

if TYPE_CHECKING:
    import numpy as np
    from .DataBlock import DataBlock

class FlowDataWrapper(FlowData):
    __slots__ = ('instanceId' ,
                 'cachePolicy',
                 'orgFlowData',
                 'headers'    ,
                )
    def __init__(self, orgFlowData:FlowData, updateHeaders:dict = {}):
        """
        FlowDataをラップし、headerのみ元を変更せず上書き可能にする
        
        Args:
            orgFlowData (FlowData): ラップ対象のFlowDataインスタンス
            updateHeaders (dict): 追加のheader情報
        """
        # 元データの属性を参照
        self.instanceId = orgFlowData.instanceId
        self.cachePolicy = orgFlowData.cachePolicy
    
        # 親クラスの初期化をスキップして直接属性を設定
        self.orgFlowData = orgFlowData
        self.headers = orgFlowData.headers.copy()
        self.headers.update(updateHeaders)
        
    # 以下のメソッドは元データに委譲
    def setDimensions(self, width:int, height:int):
        return self.orgFlowData.setDimensions(width, height)
    
    def getDimensions(self) -> tuple[int, int]:
        return self.orgFlowData.getDimensions()
    
    def getVariableType(self) -> np.dtype:
        return self.orgFlowData.getVariableType()
    
    def getArea(self) -> int:
        return self.orgFlowData.getArea()
    
    def getBlock(self, planeIndex:int, x:int, y:int) -> DataBlock:
        return self.orgFlowData.getBlock(planeIndex, x, y)
    
    def getBlockCount(self) -> int:
        return self.orgFlowData.getBlockCount()
    
    def iterateBlocks(self, planeIndex:int=None) -> Iterator[DataBlock]:
        return self.orgFlowData.iterateBlocks(planeIndex)
    
    def setBlock(self, dataBlock:DataBlock):
        return self.orgFlowData.setBlock(dataBlock)
    
    def getMaxValue(self) -> float:
        return self.orgFlowData.getMaxValue()
    
    def getMinValue(self) -> float:
        return self.orgFlowData.getMinValue()
    
    def getModeValue(self) -> float:
        return self.orgFlowData.getModeValue()

    def getQuantile(self, per:float) -> float:
        return self.orgFlowData.getQuantile(per)
    
    def getHistogram(self, bins:int=256, log_scale:bool=False) -> dict:
        return self.orgFlowData.getHistogram(bins, log_scale)
