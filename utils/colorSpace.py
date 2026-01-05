'''
colorSpace - 色空間処理

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

def labToRgb(l, a, b):
    """
    Lab 色空間から RGB 色空間へ変換
    
    :param l: L成分 [0.0,1.0)
    :param a: a成分 [-0.5,0.5)
    :param b: b成分 [-0.5,0.5)
    """
    import numpy as np
    from utils import numpy_helpers as nh
    
    _L, _a, _b = l, a, b
    
    # Lab/RGB 変換
    _R = _L + _a/1.41421356237 +     _b/2.44948974278
    _G = _L - _a/1.41421356237 +     _b/2.44948974278
    _B = _L                    - 2.0*_b/2.44948974278

    _R = _R**3
    _G = _G**3
    _B = _B**3

    return (_R, _G, _B)

def rgbToLab(r, g, b):
    """
    RGB 色空間から Lab 色空間へ変換
    
    :param r: R成分 [0.0,1.0)
    :param g: G成分 [0.0,1.0)
    :param b: B成分 [0.0,1.0)
    """
    import numpy as np
    from utils import numpy_helpers as nh

    _R, _G, _B =  r, g, b
    
    _R = np.cbrt(_R)
    _G = np.cbrt(_G)
    _B = np.cbrt(_B)

    # RGB/Lab 変換
    _L = (_R + _G + _B) / 3.0
    _a = (_R - _G         ) / 1.41421356237
    _b = (_R + _G - 2.0*_B) / 2.44948974278

    return (_L, _a, _b) # L:[0.0,1.0), ab:[-0.5,0.5)