'''
LazyFlowData - 遅延評価 FlowData

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import threading
from collections import UserDict

from config import MAX_WORKERS
from .Constants import CachePolicy
from .FlowData import FlowData

class LazyFlowData(FlowData):
    """遅延評価FlowData"""
    __slots__ = ('cachePolicy'    ,
                 'sourceFlowData' ,
                 'sourceFlowDatas',
                 'headers'        ,
                 'args'           ,
                 'kwargs'         ,
                 '_blockLocks'    ,
                )
    
    def __init__(self, sourceFlowDatas, *args, **kwargs):
        super().__init__(None)
        self.cachePolicy     = CachePolicy.CALCULABLE # キャッシュポリシー（遅延評価データはCALCULABLE固定）
        self.sourceFlowData  = sourceFlowDatas[0] if isinstance(sourceFlowDatas, (list,tuple)) else sourceFlowDatas
        self.sourceFlowDatas = sourceFlowDatas
        self.headers         = LazyHeadersDict(self, *args, **kwargs)
        self.args            = args
        self.kwargs          = kwargs
        
        self.setDimensions(*self.sourceFlowData.getDimensions())
        
        self._blockLocks = [threading.Lock() for _ in range(MAX_WORKERS*4)]
    
    def getBlock(self, planeIndex, x, y):
        """指定位置からブロックを取得（遅延評価）"""
        from utils import measurement as mes
        block = super().getBlock(planeIndex, x, y)
        if not block:
            return None
        elif block.isValid():
            return block
        else:
            from utils.ThreadPool import PerResourceThreadPoolWrapper as wrapper
            # 有効なブロックが無いので遅延評価を実行
            lockKey = hash((planeIndex, x, y)) % len(self._blockLocks)
            if self._blockLocks[lockKey].locked():
                wrapper.enterWait()
                isWait = True
            else:
                isWait = False
            with self._blockLocks[lockKey]: # 既に計算中の場合、終了を待つ
                if isWait:
                    wrapper.exitWait()
                if block.isValid():
                    return block
                elif type(self).operation == LazyFlowData.operation:
                    # operation がオーバーライドされていないので計測しない
                    block = self.operation(self.sourceFlowDatas, planeIndex, x, y, *self.args, **self.kwargs)
                    self.setBlock(block)
                    return block
                else:
                    # operation がオーバーライドされているので計測する
                    block = mes.elapsedThreading(self.operation, self.sourceFlowDatas, planeIndex, x, y, *self.args, **self.kwargs)
                    self.setBlock(block)
                    return block
    
    def operation(self, flowDatas, planeIndex, x, y, *args, **kwargs):
        """遅延評価を実行"""
        from utils import measurement as mes
        from base import BroadcastMixin
        blocks, shape = BroadcastMixin.calculateBroadcastedBlock(flowDatas, planeIndex, x, y)
        if not blocks:
            return blocks
        elif isinstance(blocks, (list,tuple)) and not any(blocks):
            return blocks
        else:
            return self.blockOperation(blocks, planeIndex, x, y, *args, **kwargs)
    
    def blockOperation(self, blocks, planeIndex, x, y, *args, **kwargs):
        """遅延評価を実行"""
        return blocks
    
    def getLazyHeaderkeys(self):
        """遅延評価対象の header キーを取得"""
        return []
    
    def headerOperation(self, lazyFlowData, key, *args, **kwargs):
        """headers 遅延評価"""
        return {}

class LazyHeadersDict(UserDict):
    """遅延評価対応のheaders辞書"""
    __slots__ = ('_lazyFlowData',
                 'args'         ,
                 'kwargs'       ,
                )
    def __init__(self, lazyFlowData, *args, **kwargs):
        super().__init__(lazyFlowData.sourceFlowData.headers)
        
        self._lazyFlowData = lazyFlowData
        self.args          = args
        self.kwargs        = kwargs

        for key in self._lazyFlowData.getLazyHeaderkeys():
            self.data[key]= "<LazyHeaderOperation>"
    
    def __getitem__(self, key):
        if not key in self.data:
            return None
        else:
            value = self.data[key]
            if isinstance(value, str) and "<LazyHeaderOperation>"==value:
                lazyResult = self._lazyFlowData.headerOperation(self._lazyFlowData, key, *self.args, **self.kwargs)
                self.data.update(lazyResult)
                value = self.data[key]
            return value
