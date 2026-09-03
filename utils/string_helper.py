'''
string helper functions with default dtype

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from typing import overload
import math

@overload
def dispS(value:float, representative:float|None = None) -> str: ...

@overload
def dispS(value:list[float], representative:float|None = None) -> list[str]:...

def dispS(value, representative = None):
    """数値を表示に適した長さで文字列化(短)する"""
    if isinstance(value,(list,tuple)):
        values = value
    else:
        values = [value]
    
    if representative:
        abss   = [abs(representative)]
        absMax = max(abss)
    else:
        abss   = [abs(v) for v in values]
        absMax = max(abss)
    
    threshold = [100.0, 10.0,  1.0,  0.1, 0.01, 0.001, 0.0001, 0.00001, 0.000001, 0.0000001, 0.00000001]
    format    = [".0f",".1f",".2f",".3f",".4f", ".5f",  ".6f",   ".7f",    ".8f",     ".9f",      ".9f",      ".10f"]
    if 0.0 == absMax:
        fm = ".2f"
    else:
        fm = format[-1]
        for th,fm in zip(threshold,format):
            if th <= absMax:
                break
    
    texts = [f"{v:{fm}}" for v in values]
    maxLen = max([len(text) for text in texts])
    texts = [text.rjust(maxLen) for text in texts]

    if isinstance(value,(list,tuple)):
        return texts
    else:
        return texts[0]

@overload
def dispL(value:float, representative:float|None = None) -> str: ...

@overload
def dispL(value:list[float], representative:float|None = None) -> list[str]:...

def dispL(value, representative = None):
    """数値を表示に適した長さで文字列化(長)する"""
    if isinstance(value,(list,tuple)):
        values = value
    else:
        values = [value]
    
    if representative:
        abss   = [abs(representative)]
        absMax = max(abss)
    else:
        abss   = [abs(v) if not math.isnan(v) else 0.0 for v in values]
        absMax = max(abss)
    
    threshold = [100.0,  0.1, 0.0001, 0.0000001]
    format    = [".0f",".3f",  ".6f",     ".9f"]
    if 0.0 == absMax:
        fm = ".3f"
    else:
        fm = format[-1]
        for th,fm in zip(threshold,format):
            if th <= absMax:
                break
    
    texts = [f"{v:{fm}}" for v in values]
    maxLen = max([len(text) for text in texts])
    texts = [text.rjust(maxLen) for text in texts]

    if isinstance(value,(list,tuple)):
        return texts
    else:
        return texts[0]
