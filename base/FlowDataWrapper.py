'''
FlowDataWrapper class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from .FlowData import FlowData

class FlowDataWrapper(FlowData):
    def __init__(self, orgFlowData, updateHeaders={}):
        """
        FlowDataをラップし、headerのみ元を変更せず上書き可能にする
        
        Args:
            orgFlowData (FlowData): ラップ対象のFlowDataインスタンス
            updateHeaders (dict): 追加のheader情報
        """
        # 親クラスの初期化をスキップして直接属性を設定
        self.orgFlowData = orgFlowData
        self.headers = orgFlowData.headers.copy()
        self.headers.update(updateHeaders)
        
        # 元データの属性を参照
        self.instanceId = orgFlowData.instanceId
        self.cachePolicy = orgFlowData.cachePolicy
        self._dimensions = orgFlowData._dimensions
        self._blockSize = orgFlowData._blockSize
        self._maxValue = orgFlowData._maxValue
        self._minValue = orgFlowData._minValue
        self._percentileCache = orgFlowData._percentileCache
        self._histogramCache = orgFlowData._histogramCache
        self._existingBlocks = orgFlowData._existingBlocks
    
    # 以下のメソッドは元データに委譲
    def _loadBlock(self, planeIndex, blockX, blockY):
        return self.orgFlowData._loadBlock(planeIndex, blockX, blockY)
    
    def _saveBlock(self, planeIndex, blockX, blockY, blockData):
        return self.orgFlowData._saveBlock(planeIndex, blockX, blockY, blockData)
    
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
    
    def getPercentile(self, percentile):
        return self.orgFlowData.getPercentile(percentile)
    
    def getHistogram(self, bins=256, log_scale=False):
        return self.orgFlowData.getHistogram(bins, log_scale)