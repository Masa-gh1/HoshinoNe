'''
DataBlock class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import uuid
import numpy as np
from main.CacheManager import CacheManager

class DataBlock:
    def __init__(self, planeIndex, x, y, data):
        self.blockId = None # 再現性と他の DataBlock との衝突を回避する為の ID を入れる
        self._data = data
        self.cachePolicy = CacheManager.CALCULABLE  # デフォルト
        
        # 付属情報(DataBlockでは使用しない)
        self.planeIndex = planeIndex
        self.x = x
        self.y = y
    
    @property
    def data(self):
        """遅延ロードでデータを取得"""
        if self._data is None:
            self._data = self._loadFromCache()
        return self._data
    
    @data.setter
    def data(self, value):
        """データを設定してキャッシュに保存"""
        self._data = value
        self._saveToCache(value)
    
    def isValid(self):
        """データが有効かどうかを確認"""
        return CacheManager.isCached(self.blockId, self.cachePolicy)
    
    def _loadFromCache(self):
        """キャッシュからデータを読み込み"""
        return CacheManager.get(self.blockId, self.cachePolicy)
    
    def _saveToCache(self, data):
        """データをキャッシュに保存"""
        CacheManager.set(self.blockId, data, self.cachePolicy)
    
    def getWidth(self):
        """ブロックの幅を取得"""
        return self.data.shape[1] if self.data.ndim > 1 else 1
    
    def getHeight(self):
        """ブロックの高さを取得"""
        return self.data.shape[0]
    
