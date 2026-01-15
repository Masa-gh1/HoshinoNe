'''
Coalescing Thread Pool - 同一オブジェクトからの重複実行を回避

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import sys
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Callable, Tuple

class CoalescingThreadPool:
    def __init__(self, max_workers=None):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._pending_tasks: Dict[Any, Tuple[Callable, tuple, dict, Future]] = {}  # 待機中タスク
        self._running_tasks: Dict[Any, Future] = {}  # 実行中タスク
        self._lock = threading.Lock()
    
    def submit(self, resourceKey: Any, func: Callable, *args, **kwargs) -> Future:
        """
        同一 resourceKey からの実行要求は1つだけ実行し、待機中は最新のみ保持
        """
        with self._lock:
            # 既存の待機中タスクをキャンセル
            if resourceKey in self._pending_tasks:
                pending_data = self._pending_tasks[resourceKey]
                if isinstance(pending_data, tuple) and len(pending_data) == 4:
                    pending_data[3].cancel()  # futureをキャンセル
            
            future = Future()
            if resourceKey in self._running_tasks:
                # 実行中タスクがあるので、待機キューに追加
                self._pending_tasks[resourceKey] = (func, args, kwargs, future)
            else:
                # 即座に実行
                self._running_tasks[resourceKey] = future
                self._execute_task(resourceKey, func, args, kwargs, future)
            return future
    
    def _execute_task(self, resourceKey: Any, func: Callable, args: tuple, kwargs: dict, future: Future):
        """タスクを実行"""
        self._executor.submit(self._wrapper, resourceKey, func, args, kwargs, future)
    
    def _wrapper(self, resourceKey: Any, func: Callable, args: tuple, kwargs: dict, future: Future):
        try:
            result = func(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb,file=sys.stderr)
            future.set_exception(e)
        finally:
            self._execute_next_task(resourceKey)
    
    def _execute_next_task(self, resourceKey: Any):
        """次の待機タスクを実行"""
        with self._lock:
            if resourceKey in self._running_tasks:
                del self._running_tasks[resourceKey]
            
            # 待機中のタスクがあれば実行
            if resourceKey in self._pending_tasks:
                pending_data = self._pending_tasks[resourceKey]
                del self._pending_tasks[resourceKey]
                
                if isinstance(pending_data, tuple) and 4 == len(pending_data):
                    func, args, kwargs, future = pending_data
                    if not future.cancelled():
                        self._running_tasks[resourceKey] = future
                        self._execute_task(resourceKey, func, args, kwargs, future)
    
    def shutdown(self, wait=True):
        """スレッドプールを終了"""
        self._executor.shutdown(wait=wait)
