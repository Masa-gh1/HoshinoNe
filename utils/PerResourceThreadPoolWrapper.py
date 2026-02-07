'''
Per Resource Thread Pool Wrapper - リソース毎スレッドプールを実現するラッパー

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import random
from collections import deque
from concurrent.futures import Future
import threading
from typing import Dict, Any, Callable, Tuple, List

class PerResourceThreadPoolWrapper:
    def __init__(self):
        self.maxWorkersPerResource = None
        self._executor = None
        self._pendingTasks:  Dict[Any, List[Tuple[Callable, tuple, dict, Future]]] = {}  # 保留中タスク
        self._runningTasks:  Dict[Any, List[Future]] = {}  # 実行中タスク
        self._runningSum = 0  # 実行中の合計
        self._waitingCounts: Dict[Any, int] = {}  # 待機中の数
        self._waitingSum = 0  # 待機中の合計
        self._lock = threading.Lock()
    
    def setExecutor(self, executor, maxWorkersPerResource = None, maxWorkers = None):
        self._executor = executor
        self.maxWorkersPerResource = maxWorkersPerResource
        self.maxWorkers            = maxWorkers
        self._pendingTasks.clear()
        self._runningTasks.clear()
        self._runningSum = 0
        self._waitingCounts.clear()
        self._waitingSum = 0
    
    def submit(self, resourceKey: Any, func: Callable, *args, **kwargs) -> Future:
        """
        同一 resourceKey からの実行要求は maxWorkersPerResource まで実行する。
        全体での実行数上限は _executor による。
        """
        with self._lock:
            if not resourceKey in self._pendingTasks:
                self._pendingTasks[resourceKey] = deque()
            if not resourceKey in self._runningTasks:
                self._runningTasks[resourceKey] = []
            
            waitingCount = self._waitingCounts.setdefault(resourceKey, 0)
            
            if((   not self.maxWorkers is None
               and     self.maxWorkers <= self._runningSum - self._waitingSum
               )
              or
               (   not self.maxWorkersPerResource is None
               and     self.maxWorkersPerResource <= len(self._runningTasks[resourceKey]) - waitingCount
               )
              ):
                # 実行中のタスクが上限に達しているので保留
                future = Future()
                self._pendingTasks[resourceKey].append((func, args, kwargs, future))
                return future
            else:
                # タスクを実行
                future = Future()
                self._runningTasks[resourceKey].append(future)
                self._runningSum += 1
                self._execute_task(resourceKey, func, args, kwargs, future)
                return future

    def _execute_task(self, resourceKey: Any, func: Callable, args: tuple, kwargs: dict, future: Future):
        """タスクを実行"""
        future._future = self._executor.submit(self._wrapper, resourceKey, func, args, kwargs, future)
    
    local = threading.local()

    def _wrapper(self, resourceKey: Any, func: Callable, args: tuple, kwargs: dict, future: Future):
        try:
            self.local.enterWait = lambda: self.enterWait(resourceKey)
            self.local.exitWait  = lambda: self.exitWait(resourceKey)
            result = func(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            from utils.Debug import Debug
            Debug.log(type(self).__name__, f"Error:{func.__name__}", e)
            future.set_exception(e)
        finally:
            self._execute_next_task(resourceKey, future)
    
    def _execute_next_task(self, resourceKey: Any, future: Future=None):
        """次の保留タスクを実行"""
        with self._lock:
            if not future is None and resourceKey in self._runningTasks:
                self._runningTasks[resourceKey].remove(future)
                self._runningSum -= 1
                if(   len(self._runningTasks[resourceKey]) <= 0
                  and len(self._pendingTasks[resourceKey]) <= 0
                  ):
                    del self._runningTasks[resourceKey]
                    del self._pendingTasks[resourceKey]
                    del self._waitingCounts[resourceKey]
            
            if(   not self.maxWorkers is None
              and     self.maxWorkers <= self._runningSum - self._waitingSum
              ):
                # 実行中のタスクが上限に達しているので保留
                pass
            else:
                # 保留中からランダムに選択し実行
                resourceKeys = list(self._pendingTasks.keys())
                random.shuffle(resourceKeys)
                for resourceKey in resourceKeys:
                    waitingCount = self._waitingCounts[resourceKey]
                    if(     not self.maxWorkersPerResource is None
                        and     self.maxWorkersPerResource <= len(self._runningTasks[resourceKey]) - waitingCount
                        ):
                        # 実行中のタスクが上限に達しているので保留
                        pass
                    elif 0 < len(self._pendingTasks[resourceKey]):
                        # 保留中のタスクを実行
                        func, args, kwargs, future = self._pendingTasks[resourceKey].popleft()
                        if not future.cancelled():
                            self._runningTasks[resourceKey].append(future)
                            self._runningSum += 1
                            self._execute_task(resourceKey, func, args, kwargs, future)
                            break
    
    def enterWait(self, resourceKey: Any):
        """長時間の待ちが考えられることを通知する"""
        with self._lock:
            self._waitingCounts[resourceKey] += 1
            self._waitingSum += 1
        self._execute_next_task(resourceKey)
    
    def exitWait(self, resourceKey: Any):
        """長時間の待ちが終わった事を通知する"""
        with self._lock:
            self._waitingCounts[resourceKey] -= 1
            self._waitingSum -= 1
    
    def shutdown(self, wait=True, cancel_futures=False):
        """シャットダウン"""
        if cancel_futures:
            with self._lock:
                for tasks in self._pendingTasks.values():
                    for func, args, kwargs, future in tasks:
                        future.cancel()
                for futures in self._runningTasks.values():
                    for future in futures:
                        if not future.done():
                            future.set_exception(Exception("中断されました"))
                self._pendingTasks.clear()
                self._runningTasks.clear()
                self._runningSum = 0
                self._waitingCounts.clear()
                self._waitingSum = 0
        self._executor.shutdown(wait=wait,cancel_futures=cancel_futures)
