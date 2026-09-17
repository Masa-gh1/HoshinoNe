'''
DataBlock class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from .Constants import CachePolicy

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

class DataBlock:
    """データブロック配列のラッパークラス"""
    __slots__ = ('blockId'    ,
                 'cachePolicy',
                 '_data'      ,
                 'planeIndex' ,
                 'x'          ,
                 'y'          ,
                )

    def __init__(self, data:np.ndarray|list|str, planeIndex:int, x:int, y:int):
        """
        data に str を渡した場合、id をして扱われキャッシュ機構用に用いられます。
        """
        if isinstance(data, str):
            instanceId = data
            self.blockId = f"{instanceId}:{planeIndex}:{x}:{y}" # キャッシュ用の ID 、キャッシュする場合に設定する
            self._data = None
        else:
            self.blockId = None
            self._data = data # 保存するデータ
        
        self.cachePolicy = CachePolicy.CALCULABLE  # デフォルト
        
        # 付属情報(DataBlockでは使用しない)
        self.planeIndex = planeIndex
        self.x = x
        self.y = y
    
    @property
    def data(self) -> npt.NDArray:
        """遅延ロードでデータを取得"""
        from .CacheManager import CacheManager

        if self._data is None:
            assert not self.blockId is None, "blockId is None"
            data = CacheManager.get(self.blockId)
            self._data = data
            assert not self._data is None, "data is None"
        return self._data
    
    @data.setter
    def data(self, data:np.ndarray):
        """データを設定してキャッシュに保存"""
        from .CacheManager import CacheManager
        
        self._data = data
        if not self.blockId is None:
            CacheManager.set(self.blockId, data, self.cachePolicy)
    
    def isValid(self) -> bool:
        """データが有効かどうかを確認"""
        from .CacheManager import CacheManager
        
        return CacheManager.isCached(self.blockId) if self.blockId else False
    
    def getWidth(self) -> int:
        """ブロックの幅を取得"""
        return self.data.shape[1] if self.data.ndim > 1 else 1
    
    def getHeight(self) -> int:
        """ブロックの高さを取得"""
        return self.data.shape[0]
