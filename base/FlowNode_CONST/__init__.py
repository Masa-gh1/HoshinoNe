'''
FlowNode constant package for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from ..FlowNode import _MAJOR_TYPE_FUNC
from ..FlowNode import _MAJOR_TYPE_U_OP
from ..FlowNode import _MAJOR_TYPE_B_OP
from ..FlowNode import _MAJOR_TYPE_AGG
from ..FlowNode import _MAJOR_TYPE_IO
from ..FlowNode import _MAJOR_TYPE_CONST
from ..FlowNode import _MAJOR_TYPE_UTIL

from ..FlowNode import _IO_TYPE_0N
from ..FlowNode import _IO_TYPE_N0
from ..FlowNode import _IO_TYPE_NN
from ..FlowNode import _IO_TYPE_N1

from ..FlowNode import _OUT_CAT_PRI
from ..FlowNode import _OUT_CAT_AUX
from ..FlowNode import _OUT_CAT_PAS
from ..FlowNode import _OUT_CAT_ETC
from ..FlowNode import _OUT_CAT_NON

__all__ = [
    '_MAJOR_TYPE_FUNC',
    '_MAJOR_TYPE_U_OP',
    '_MAJOR_TYPE_B_OP',
    '_MAJOR_TYPE_AGG',
    '_MAJOR_TYPE_IO',
    '_MAJOR_TYPE_CONST',
    '_MAJOR_TYPE_UTIL',
    '_IO_TYPE_0N',
    '_IO_TYPE_N0',
    '_IO_TYPE_NN',
    '_IO_TYPE_N1',
    '_OUT_CAT_PRI',
    '_OUT_CAT_AUX',
    '_OUT_CAT_PAS',
    '_OUT_CAT_ETC',
    '_OUT_CAT_NON',
]
