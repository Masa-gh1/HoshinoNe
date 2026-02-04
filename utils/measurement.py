'''
measurement - 計測ユーティリティ

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import time
import threading
from utils.ThreadPool import CoalescingExecutor
from base import CacheManager

_local = threading.local()
_elapsedLog = []

def elapsed(func, *args, **kwargs):
    """func の処理時間を計測する"""
    start = time.perf_counter_ns()
    result = func(*args, **kwargs)
    elapsed_ns = (time.perf_counter_ns() - start)
    
    _elapsedLog.append((func.__qualname__, elapsed_ns))

    if 1000 <= len(_elapsedLog):
        CoalescingExecutor.submit(histgram.update, histgram.update, _elapsedLog)

    return result

def elapsedThreading(func, *args, **kwargs):
    """func の処理時間を計測する(入れ子の呼び出しを分離する)"""
    if not hasattr(_local, "elapsedThreading"):
        _local.elapsedThreading = []
        _local.n = 0
        begin = True
    else:
        _local.n += 1
        begin = False
    
    start = time.perf_counter_ns()
    result = func(*args, **kwargs)
    elapsed_ns = (time.perf_counter_ns() - start)

    _local.elapsedThreading.append((_local.n, func.__qualname__, elapsed_ns))

    if begin:
        _elapsedLog.append((func.__qualname__, _local.elapsedThreading))
        if 1000 <= len(_elapsedLog):
            CoalescingExecutor.submit(histgram.update, histgram.update, _elapsedLog)
        
        del _local.elapsedThreading
        del _local.n
    else:
        _local.n -= 1

    return result

def elapsedLogging(name, elapsed_ns):
    """処理時間を記録する"""
    _elapsedLog.append((name, elapsed_ns))

    if 1000 <= len(_elapsedLog):
        CoalescingExecutor.submit(histgram.update, histgram.update, _elapsedLog)

class histgram:
    """処理時間のヒストグラム"""
    _elapsedHis = {}
    _times = 0

    @classmethod
    def update(cls, elapsedLog):
        """処理時間のヒストグラムを更新"""
        _logs = list(elapsedLog)
        elapsedLog.clear()
        logs = []
        last = {}
        for log in _logs:
            name, elapsed = log
            if isinstance(elapsed, list):
                for n, name, elapsed in reversed(elapsed):
                    l = last.setdefault(n+1,[0])
                    logs.append((name, elapsed - l[0]))
                    l[0] = 0
                    l = last.setdefault(n,[0])
                    l[0] += elapsed
            else:
                logs.append((name, elapsed))

        for log in reversed(logs):
            name, elapsed = log
            cls._times += 1
            
            key = None
            for e in range(20):
                x = int(4096*(1.1892072**e))
                if cls._times < x:
                    key = f"{x}:{name}"
                    break
            if key is None:
                key = f"{x}+:{name}"
            
            his = cls._elapsedHis.setdefault( key, {})
            elapsed = min( elapsed//1000 , 8191)

            for e in range(20):
                x = int(10*(2**e))
                for values in cls._elapsedHis.values():
                    values.setdefault(x,0)
                
                if elapsed < x:
                    his[x] += 1
                    break

def getHistgram():
    """処理時間のヒストグラムを取得"""
    return histgram._elapsedHis
