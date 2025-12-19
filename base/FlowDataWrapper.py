'''
FlowDataWrapper class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from . import FlowData

class FlowDataWrapper(FlowData):
    __slots__ = ('instanceId' ,
                 'cachePolicy',
                 'orgFlowData',
                 'headers'    ,
                )
    def __init__(self, orgFlowData, updateHeaders={}):
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
    def _loadBlock(self, planeIndex, x, y):
        return self.orgFlowData._loadBlock(planeIndex, x, y)
    
    def _saveBlock(self, planeIndex, x, y, blockData):
        return self.orgFlowData._saveBlock(planeIndex, x, y, blockData)
    
    def setDimensions(self, width, height):
        return self.orgFlowData.setDimensions(width, height)
    
    def getDimensions(self):
        return self.orgFlowData.getDimensions()
    
    def getArea(self):
        return self.orgFlowData.getArea()
    
    def getBlock(self, planeIndex, x, y):
        return self.orgFlowData.getBlock(planeIndex, x, y)
    
    def getBlockCount(self):
        return self.orgFlowData.getBlockCount()
    
    def iterateBlocks(self):
        return self.orgFlowData.iterateBlocks()
    
    def setBlock(self, dataBlock):
        return self.orgFlowData.setBlock(dataBlock)
    
    def getMaxValue(self):
        return self.orgFlowData.getMaxValue()
    
    def getMinValue(self):
        return self.orgFlowData.getMinValue()
    
    def getModeValue(self):
        return self.orgFlowData.getModeValue()

    def getPercentile(self, percentile):
        return self.orgFlowData.getPercentile(percentile)
    
    def getHistogram(self, bins=256, log_scale=False):
        return self.orgFlowData.getHistogram(bins, log_scale)