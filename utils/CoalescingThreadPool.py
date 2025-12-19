'''
Coalescing Thread Pool - 同一オブジェクトからの重複実行を回避

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Callable, Tuple
import atexit

class CoalescingThreadPool:
    def __init__(self, max_workers=None):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._pending_tasks: Dict[Any, Tuple[Callable, tuple, dict, Future]] = {}  # 待機中タスク
        self._running_tasks: Dict[Any, Future] = {}  # 実行中タスク
        self._lock = threading.Lock()
        
    def submit(self, obj_key: Any, func: Callable, *args, **kwargs) -> Future:
        """
        同一obj_keyからの実行要求は1つだけ実行し、待機中は最新のみ保持
        """
        with self._lock:
            # 既存の待機中タスクをキャンセル
            if obj_key in self._pending_tasks:
                pending_data = self._pending_tasks[obj_key]
                if isinstance(pending_data, tuple) and len(pending_data) == 4:
                    pending_data[3].cancel()  # futureをキャンセル
            
            future = Future()
            if obj_key in self._running_tasks:
                # 実行中タスクがあるので、待機キューに追加
                self._pending_tasks[obj_key] = (func, args, kwargs, future)
            else:
                # 即座に実行
                self._execute_task(obj_key, func, args, kwargs, future)
            return future
    
    def _execute_task(self, obj_key: Any, func: Callable, args: tuple, kwargs: dict, future: Future):
        """タスクを実行"""
        def wrapper():
            try:
                with self._lock:
                    self._running_tasks[obj_key] = future
                
                result = func(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            finally:
                self._execute_next_task(obj_key)
        
        self._executor.submit(wrapper)
    
    def _execute_next_task(self, obj_key: Any):
        """次の待機タスクを実行"""
        with self._lock:
            if obj_key in self._running_tasks:
                del self._running_tasks[obj_key]
            
            # 待機中のタスクがあれば実行
            if obj_key in self._pending_tasks:
                pending_data = self._pending_tasks[obj_key]
                del self._pending_tasks[obj_key]
                
                if isinstance(pending_data, tuple) and len(pending_data) == 4:
                    func, args, kwargs, future = pending_data
                    if not future.cancelled():
                        self._execute_task(obj_key, func, args, kwargs, future)
    
    def shutdown(self, wait=True):
        """スレッドプールを終了"""
        self._executor.shutdown(wait=wait)
