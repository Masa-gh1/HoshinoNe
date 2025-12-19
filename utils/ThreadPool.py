'''
Global thread pool for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import atexit

from config import MAX_WORKERS
from utils.PerResourceThreadPoolWrapper import PerResourceThreadPoolWrapper
from utils.CoalescingThreadPool import CoalescingThreadPool

# グローバルスレッドプール
ProcessExecutorInNode  = PerResourceThreadPoolWrapper()
CoalescingExecutor = CoalescingThreadPool(max_workers=MAX_WORKERS)
atexit.register(CoalescingExecutor.shutdown)
