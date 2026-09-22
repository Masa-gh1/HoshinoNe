'''
DataBlock class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING

from abc import ABC as AbstractBaseClass, abstractmethod

from .Constants import CachePolicy

if TYPE_CHECKING:
    import numpy as np

class AbstractDataBlock(AbstractBaseClass):
    """データブロック配列のラッパークラス"""
    __slots__ = ('id'         ,
                 'blockId'    ,
                 'cachePolicy',
                 '_data'      ,
                )
    
    @abstractmethod
    def createId(self) -> str:
        """IDを生成"""
        pass
    
    @property
    def data(self) -> np.ndarray:
        """遅延ロードでデータを取得"""
        if self._data is None:
            from .CacheManager import CacheManager
            assert not self.blockId is None, "blockId is None"
            data = CacheManager.get(self.blockId)
            self._data = data
            assert not self._data is None, "data is None"
        if isinstance(self._data, list):
            self._data = self._normalizeData(self._data)
        return self._data
    
    @data.setter
    def data(self, data:np.ndarray):
        """データを設定してキャッシュに保存"""
        self._data = data
        if self.blockId:
            from .CacheManager import CacheManager
            self._data = self._normalizeData(self._data)
            CacheManager.set(self.blockId, self._data, self.cachePolicy)

    def setID(self, id:str):
        """IDを設定(キャッシュ有効化)"""
        self.id = id
        self.blockId = self.createId() # キャッシュ用の ID
        if not self._data is None:
            from .CacheManager import CacheManager
            self._data = self._normalizeData(self._data)
            CacheManager.set(self.blockId, self._data, self.cachePolicy)
    
    def isValid(self) -> bool:
        """データが有効かどうかを確認"""
        from .CacheManager import CacheManager
        
        return CacheManager.isCached(self.blockId) if self.blockId else False
    
    def _normalizeData(self, data:np.ndarray|list) -> np.ndarray:
        """データを正規化"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        # numpy配列として正規化
        if isinstance(data, np.ndarray):
            if np.iscomplexobj(data):
                # 複素数
                if data.dtype != nh.BDCOMPLEX:
                    ret = data.astype(nh.BDCOMPLEX)
                else:
                    ret = data
            else:
                # 実数
                if data.dtype != nh.BDTYPE:
                    ret = data.astype(nh.BDTYPE)
                else:
                    ret = data
        elif isinstance(data, list):
            if np.iscomplexobj(data):
                # 複素数
                ret = np.array(data, dtype=nh.BDCOMPLEX)
            else:
                # 実数
                ret = nh.array(data)
        else:
            assert False, "Unsupported data type: " + str(type(data))
        
        return ret

class DataBlock2D(AbstractDataBlock):
    __slots__ = ('blockId'    ,
                 'cachePolicy',
                 '_data'      ,
                 'id'         ,
                 'planeIndex' ,
                 'x'          ,
                 'y'          ,
                )
    
    def createId(self) -> str:
        """IDを生成"""
        return f"{self.id}:{self.planeIndex}:{self.x}:{self.y}" # キャッシュ用の ID
    
    def getWidth(self) -> int:
        """ブロックの幅を取得"""
        return self.data.shape[1] if self.data.ndim > 1 else 1
    
    def getHeight(self) -> int:
        """ブロックの高さを取得"""
        return self.data.shape[0]

class DataBlock(DataBlock2D):
    """新規用のDataBlockクラス(コンストラクタ オーバーロード)"""
    __slots__ = (
                )
    
    def __init__(self, data:np.ndarray|list, planeIndex:int, x:int, y:int):
        """
        Args:
            data: データ配列
            planeIndex: プレーンインデックス
            x: x 座標
            y: y 座標
        """
        self.blockId = None
        self._data = data # データ を保存
        self.cachePolicy = CachePolicy.CALCULABLE  # デフォルト
        
        # 付属情報(DataBlockでは使用しない)
        self.id = None
        self.planeIndex = planeIndex
        self.x = x
        self.y = y

class _DataBlock(DataBlock):
    """遅延ロード用のDataBlockクラス(コンストラクタ オーバーロード)"""
    __slots__ = (
                )
    
    def __init__(self, id:str, planeIndex:int, x:int, y:int):
        """
        Args:
            id: キャッシュ用 ID
            planeIndex: プレーンインデックス
            x: x 座標
            y: y 座標
        """
        # 付属情報(DataBlockでは使用しない)
        self.id = id
        self.planeIndex = planeIndex
        self.x = x
        self.y = y
        
        self.blockId = self.createId() # キャッシュ用の ID
        self._data = None
        self.cachePolicy = CachePolicy.CALCULABLE  # デフォルト
