'''
LazyFlowData - 遅延評価 FlowData

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING, Any

import time
import threading
from collections import UserDict

from config import MAX_WORKERS
from .Constants import CachePolicy
from .FlowData import FlowData

if TYPE_CHECKING:
    from .DataBlock import DataBlock

class LazyFlowData(FlowData):
    """遅延評価FlowData"""
    __slots__ = ('cachePolicy'    ,
                 'sourceFlowDatas',
                 'headers'        ,
                 'args'           ,
                 'kwargs'         ,
                 '_blockLocks'    ,
                )
    
    def __init__(self, headers:dict[str,Any], sourceFlowDatas:FlowData|list[FlowData], *args, **kwargs):
        super().__init__()
        
        self.cachePolicy     = CachePolicy.CALCULABLE # キャッシュポリシー（遅延評価データはCALCULABLE固定）
        self.sourceFlowDatas = sourceFlowDatas
        self.headers         = LazyHeadersDict(self, headers, *args, **kwargs)
        self.args            = args
        self.kwargs          = kwargs
        
        self._blockLocks = [threading.Lock() for _ in range(MAX_WORKERS*8)]
    
    def getBlock(self, planeIndex:int, x:int, y:int) -> DataBlock|None:
        """指定位置からブロックを取得（遅延評価）"""
        from utils import measurement as mes
        block = super().getBlock(planeIndex, x, y)
        if not block:
            return None
        elif block.isValid():
            return block
        else:
            from utils.ThreadPool import ParallelExecutor
            # 有効なブロックが無いので遅延評価を実行
            lockIndex = hash((planeIndex, x, y)) % len(self._blockLocks)
            lock = self._blockLocks[lockIndex]
            if lock.locked():
                ParallelExecutor.enterWait() # 長時間の待ちが考えられることを通知する
                isWait = True
            else:
                isWait = False
            start = time.perf_counter_ns()
            with lock: # 既に計算中の場合、終了を待つ
                t = time.perf_counter_ns() - start
                if 1000 < t:
                    from base import CacheManager
                    CacheManager.elapsedLogging("lazyFlowData lock waitting", t)
                if isWait:
                    ParallelExecutor.exitWait() # 長時間の待ちが終わった事を通知する
                if block.isValid():
                    return block
                elif type(self).operation == LazyFlowData.operation:
                    # operation がオーバーライドされていないので計測しない
                    block = self.operation(self.sourceFlowDatas, planeIndex, x, y, *self.args, **self.kwargs)
                    assert not block is None, f"block is None: class={type(self).__name__}, planeIndex={planeIndex}, x={x}, y={y}"
                    self.setBlock(block)
                    return block
                else:
                    # operation がオーバーライドされているので計測する
                    block = mes.elapsedThreading(self.operation, self.sourceFlowDatas, planeIndex, x, y, *self.args, **self.kwargs)
                    assert not block is None, f"block is None: class={type(self).__name__}, planeIndex={planeIndex}, x={x}, y={y}"
                    self.setBlock(block)
                    return block
    
    def operation(self, flowDatas:FlowData|list[FlowData], planeIndex:int, x:int, y:int, *args, **kwargs) -> DataBlock:
        """遅延評価を実行"""
        from utils import measurement as mes
        from base import BroadcastMixin
        blocks, shape = BroadcastMixin.calculateBroadcastedBlock(flowDatas, planeIndex, x, y)
        assert blocks                                             , f"blocks is None: class={type(self).__name__}, planeIndex={planeIndex}, x={x}, y={y}"
        assert not isinstance(blocks, (list,tuple)) or any(blocks), f"blocks is all empty: class={type(self).__name__}, planeIndex={planeIndex}, x={x}, y={y}"
        return self.blockOperation(blocks, planeIndex, x, y, *args, **kwargs)
    
    def blockOperation(self, blocks:DataBlock|list[DataBlock], planeIndex:int, x:int, y:int, *args, **kwargs) -> DataBlock:
        """遅延評価を実行"""
        if isinstance(blocks, (list,tuple)):
            return blocks[0]
        else:
            return blocks
    
    def getLazyHeaderkeys(self) -> list[str]:
        """遅延評価対象の header キーを取得"""
        return []
    
    def headerOperation(self, lazyFlowData:LazyFlowData, key:str, *args, **kwargs) -> dict:
        """headers 遅延評価"""
        return {}

class LazyHeadersDict(UserDict[str,Any]):
    """遅延評価対応のheaders辞書"""
    __slots__ = ('lazyFlowData' ,
                 'sourceHeaders',
                 'args'         ,
                 'kwargs'       ,
                )
    def __init__(self, lazyFlowData:LazyFlowData, headers:dict[str,Any], *args, **kwargs):
        super().__init__()
        
        self.lazyFlowData = lazyFlowData
        self.sourceHeaders = headers
        self.args          = args
        self.kwargs        = kwargs

        for key in self.sourceHeaders.keys():
            self.data[key]= "<sourceHeaders>"
    
        for key in self.lazyFlowData.getLazyHeaderkeys():
            self.data[key]= "<LazyHeaderOperation>"
    
    def __getitem__(self, key:str) -> Any:
        if not key in self.data:
            return None
        else:
            value = self.data[key]
            if isinstance(value, str) and "<LazyHeaderOperation>" == value:
                lazyResult = self.lazyFlowData.headerOperation(self.lazyFlowData, key, *self.args, **self.kwargs)
                self.data.update(lazyResult)
                value = self.data[key]
            elif isinstance(value, str) and "<sourceHeaders>" == value:
                value = self.sourceHeaders[key]
            return value
    
    def copy(self) -> LazyHeadersDict:
        o = LazyHeadersDict(self.lazyFlowData, self.sourceHeaders, *self.args, **self.kwargs)
        o.data.update(self.data)
        return o
