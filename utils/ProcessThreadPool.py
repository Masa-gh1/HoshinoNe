'''
Per Resource Thread Pool Wrapper - リソース毎スレッドプールを実現するラッパー

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import sys
import traceback
from concurrent.futures import Future
import threading
from typing import Dict, Any, Callable, Tuple, List

class PerResourceThreadPoolWrapper:
    def __init__(self):
        self.maxWorkersPerResource = None
        self._executor = None
        self._pendingTasks: Dict[Any, List[Tuple[Callable, tuple, dict, Future]]] = {}  # 待機中タスク
        self._runningTasks: Dict[Any, List[Future]] = {}  # 実行中タスク
        self._lock = threading.Lock()

    def setExecutor(self, executor, maxWorkersPerResource = None):
        self._executor = executor
        self.maxWorkersPerResource = maxWorkersPerResource
        self._pendingTasks.clear()
        self._runningTasks.clear()
    
    def submit(self, resourceKey: Any, func: Callable, *args, **kwargs) -> Future:
        """
        同一 resourceKey からの実行要求は maxWorkersPerResource まで実行する。
        全体での実行数上限は _executor による。
        """
        with self._lock:
            if not resourceKey in self._pendingTasks:
                self._pendingTasks[resourceKey] = []
            if not resourceKey in self._runningTasks:
                self._runningTasks[resourceKey] = []
            
            if(   self.maxWorkersPerResource is not None
              and self.maxWorkersPerResource <= len(self._runningTasks[resourceKey])
              ):
                # 実行中のタスクが上限に達しているので待機
                future = Future()
                self._pendingTasks[resourceKey].append((func, args, kwargs, future))
                return future
            else:
                # 実行可能なタスクがあるので実行
                future = Future()
                self._runningTasks[resourceKey].append(future)
                self._execute_task(resourceKey, func, args, kwargs, future)
                return future

    def _execute_task(self, resourceKey: Any, func: Callable, args: tuple, kwargs: dict, future: Future):
        """タスクを実行"""
        def wrapper():
            try:
                result = func(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                tb = traceback.format_exc()
                print(tb,file=sys.stderr)
                future.set_exception(e)
            finally:
                self._execute_next_task(resourceKey, future)
        
        self._executor.submit(wrapper)
    
    def _execute_next_task(self, resourceKey: Any, future: Future):
        """次の待機タスクを実行"""
        with self._lock:
            if resourceKey in self._runningTasks:
                self._runningTasks[resourceKey].remove(future)
            
            # 待機中のタスクがあれば実行
            if(   resourceKey in self._pendingTasks
              and self._pendingTasks[resourceKey]
              ):
                pending_data = self._pendingTasks[resourceKey][0]
                self._pendingTasks[resourceKey].remove(pending_data)
                
                if isinstance(pending_data, tuple) and 4 == len(pending_data):
                    func, args, kwargs, future = pending_data
                    if not future.cancelled():
                        self._runningTasks[resourceKey].append(future)
                        self._execute_task(resourceKey, func, args, kwargs, future)
