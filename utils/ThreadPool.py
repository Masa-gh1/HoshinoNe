'''
Global thread pool for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import atexit

from config import MAX_WORKERS
from utils.ProcessThreadPool import ProcessThreadPool
from utils.CoalescingThreadPool import CoalescingThreadPool

# グローバルスレッドプール
ProcessExecutor = ProcessThreadPool()
CoalescingExecutor = CoalescingThreadPool(max_workers=MAX_WORKERS)
atexit.register(CoalescingExecutor.shutdown)
