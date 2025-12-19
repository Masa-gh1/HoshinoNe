'''
半開区間ヘルパー関数
@author: Masakazu Inoue
'''

def createHalfOpenEnd(minValue, maxValue):
    """
    半開区間 [min_value, end) の終端値を作成
    
    Args:
        min_value: 最小値
        max_value: 実際の最大値
        
    Returns:
        半開区間の終端値（排他的上限）
    """
    if maxValue == int(maxValue) and minValue == int(minValue):
        # 整数値の場合は +1
        return maxValue + 1
    else:
        # 浮動小数点値の場合は微小値を加算
        return maxValue + (maxValue - minValue) * 0.001 if maxValue > minValue else maxValue + 0.001
