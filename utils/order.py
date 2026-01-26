'''
Order functions with default dtype

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

# Z階数曲線の生成
def zOrderGenerator(x1, y1, x2, y2, xStep=1, yStep=1):
    """矩形領域 (x, y, width, height) をZ順（再帰的二分割）で走査"""
    width  = (x2 - x1 + xStep - 1)//xStep
    height = (y2 - y1 + yStep - 1)//yStep

    if 1 == width and 1 == height:
        yield x1, y1
        return

    if height <= width:
        # 横長なので左右に分割
        width1 = (width // 2) * xStep
        yield from zOrderGenerator(x1         , y1, x1 + width1, y2, xStep, yStep)
        yield from zOrderGenerator(x1 + width1, y1, x2         , y2, xStep, yStep)
    else:
        # 縦長なので上下に分割
        height1 = (height // 2) * yStep
        yield from zOrderGenerator(x1, y1          , x2, y1 + height1, xStep, yStep)
        yield from zOrderGenerator(x1, y1 + height1, x2, y2          , xStep, yStep)
