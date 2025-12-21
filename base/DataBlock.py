'''
DataBlock class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from .Constants import CachePolicy

class DataBlock:
    __slots__ = ('blockId'    ,
                 'cachePolicy',
                 '_data'      ,
                 'planeIndex' ,
                 'x'          ,
                 'y'          ,
                )
    def __init__(self, data, planeIndex=None, x=None, y=None):
        self.blockId = None # 再現性と他の DataBlock との衝突を回避する為の ID を入れる
        self.cachePolicy = CachePolicy.CALCULABLE  # デフォルト

        self._data = data
        
        # 付属情報(DataBlockでは使用しない)
        self.planeIndex = planeIndex
        self.x = x
        self.y = y
    
    @property
    def data(self):
        """遅延ロードでデータを取得"""
        from .CacheManager import CacheManager

        if self._data is None:
            data = CacheManager.get(self.blockId)
            self._data = data
        return self._data
    
    @data.setter
    def data(self, data):
        """データを設定してキャッシュに保存"""
        from .CacheManager import CacheManager
        
        self._data = data
        CacheManager.set(self.blockId, data, self.cachePolicy)
    
    def isValid(self):
        """データが有効かどうかを確認"""
        from .CacheManager import CacheManager
        
        return CacheManager.isCached(self.blockId)
    
    def getWidth(self):
        """ブロックの幅を取得"""
        return self.data.shape[1] if self.data.ndim > 1 else 1
    
    def getHeight(self):
        """ブロックの高さを取得"""
        return self.data.shape[0]
