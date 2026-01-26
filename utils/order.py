'''
Order functions with default dtype

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

# Z階数曲線の生成
def zOrderGenerator(x1, y1, x2, y2, xStep=1, yStep=1):
    """
    矩形領域 [x1, x2),[y1, y2) をZ順で走査
    Args:
        x1 (int): 走査開始X座標
        y1 (int): 走査開始Y座標
        x2 (int): 走査終了X座標
        y2 (int): 走査終了Y座標
        xStep (int): X方向のステップサイズ
        yStep (int): Y方向のステップサイズ
    """
    if x2 <= x1 or y2 <= y1:
        return

    xSteps = (x2 - x1 + xStep - 1)//xStep
    ySteps = (y2 - y1 + yStep - 1)//yStep

    if 1 == xSteps and 1 == ySteps:
        yield x1, y1
        return

    # Z順（再帰的二分割）で走査
    if ySteps <= xSteps:
        # 横長なので左右に分割
        width = (xSteps // 2) * xStep
        yield from zOrderGenerator(x1        , y1, x1 + width, y2, xStep, yStep)
        yield from zOrderGenerator(x1 + width, y1, x2        , y2, xStep, yStep)
    else:
        # 縦長なので上下に分割
        height = (ySteps // 2) * yStep
        yield from zOrderGenerator(x1, y1         , x2, y1 + height, xStep, yStep)
        yield from zOrderGenerator(x1, y1 + height, x2, y2         , xStep, yStep)
