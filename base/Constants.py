'''
Constants - 本システム共通定義

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from types import SimpleNamespace

# キャッシュポリシー
CachePolicy = SimpleNamespace()
CachePolicy.PERSISTENT = 'persistent'    # 永続化（ストレージ退避あり）
CachePolicy.CALCULABLE = 'calculable'    # 計算可能（キャッシュする:上限まで保持）
