'''
NumPy helper functions with default dtype

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import numpy as np
from config import DEFAULT_BLOCK_TYPE

# NumPyのデフォルト浮動小数点型を設定
# 注意: この設定は一部の関数でのみ有効。確実にするには下記ヘルパー関数を使用
np.float_ = DEFAULT_BLOCK_TYPE

# 型変換用エイリアス
BDTYPE = DEFAULT_BLOCK_TYPE  # ブロックデータタイプ 使用例 arr.astype(nh.BDTYPE)

def array(*args, **kwargs):
    """np.arrayのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.array(*args, **kwargs)

def zeros(*args, **kwargs):
    """np.zerosのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.zeros(*args, **kwargs)

def ones(*args, **kwargs):
    """np.onesのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.ones(*args, **kwargs)

def nans(shape, **kwargs):
    """NaNで埋めた配列を作成（デフォルトdtype版）
    
    Args:
        shape: 配列の形状
        **kwargs: np.fullの追加引数
    """
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.full(shape, np.nan, **kwargs)

def full(*args, **kwargs):
    """np.fullのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.full(*args, **kwargs)

def empty(*args, **kwargs):
    """np.emptyのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.empty(*args, **kwargs)

def arange(*args, **kwargs):
    """np.arangeのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.arange(*args, **kwargs)

def linspace(*args, **kwargs):
    """np.linspaceのデフォルトdtype版"""
    kwargs.setdefault('dtype', DEFAULT_BLOCK_TYPE)
    return np.linspace(*args, **kwargs)