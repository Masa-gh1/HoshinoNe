'''
Global thread pool for FlowEditor

@author: Masakazu Inoue
'''

from concurrent.futures import ThreadPoolExecutor
import atexit
from config import MAX_WORKERS

# グローバルスレッドプール
ProcessExecutor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
atexit.register(ProcessExecutor.shutdown)
