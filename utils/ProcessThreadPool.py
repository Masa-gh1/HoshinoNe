'''
Processing Thread Pool - ノード内の並列処理用スレッドプール

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from concurrent.futures import Future
from typing import Callable

class ProcessThreadPool:
    def __init__(self):
        self._executor = None

    def setExecutor(self,executor):
        self._executor = executor
    
    def submit(self, func: Callable, *args, **kwargs) -> Future:
        return self._executor.submit( func, *args, **kwargs)
