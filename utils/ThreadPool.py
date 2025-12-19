'''
Global thread pool for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from concurrent.futures import ThreadPoolExecutor
import atexit
from config import MAX_WORKERS

# グローバルスレッドプール
ProcessExecutor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
atexit.register(ProcessExecutor.shutdown)
