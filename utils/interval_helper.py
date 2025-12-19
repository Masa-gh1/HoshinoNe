'''
半開区間ヘルパー関数

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from config import DEFAULT_BLOCK_TYPE

def createHalfOpenEnd(minValue, maxValue):
    """
    半開区間 [min_value, end) の終端値を作成
    
    Args:
        min_value: 最小値
        max_value: 実際の最大値
        
    Returns:
        半開区間の終端値（排他的上限）
    """
    if maxValue is None:
        return None
    elif maxValue == int(maxValue) and minValue == int(minValue):
        # 整数値と判断できる場合は +1
        return float(maxValue) + 1.0
    else:
        # 浮動小数点値の場合は微小値を加算
        return float(maxValue) + maxValue * np.finfo(DEFAULT_BLOCK_TYPE).eps
