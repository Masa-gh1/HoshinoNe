'''
Global thread pool for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import atexit
from concurrent.futures import ThreadPoolExecutor

from config import MAX_WORKERS
from utils.CoalescingThreadPool import CoalescingThreadPool

# グローバルスレッドプール
ProcessExecutor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
atexit.register(ProcessExecutor.shutdown)

CoalescingExecutor = CoalescingThreadPool(max_workers=MAX_WORKERS)
atexit.register(CoalescingExecutor.shutdown)
