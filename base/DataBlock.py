'''
DataBlock class

@author: Masakazu Inoue
'''

import numpy as np

class DataBlock:
    def __init__(self, planeIndex, x, y, data, flowData=None):
        self.flowData = flowData
        self.planeIndex = planeIndex
        self.x = x
        self.y = y
        self._data = data
        self._loaded = False
    
    @property
    def data(self):
        """遅延ロードでデータを取得"""
        if not self._loaded:
            if self.flowData:
                blockX = self.x // self.flowData._blockSize
                blockY = self.y // self.flowData._blockSize
                loaded_data = self.flowData._loadBlock(self.planeIndex, blockX, blockY)
                if loaded_data is not None:
                    self._data = loaded_data
            self._data = np.array(self._data, dtype=np.float64) if not isinstance(self._data, np.ndarray) else self._data
            self._loaded = True
        return self._data
    
    @data.setter
    def data(self, value):
        """データを設定"""
        self._data = value
        self._loaded = True
    
    def getWidth(self):
        """ブロックの幅を取得"""
        return self.data.shape[1] if self.data.ndim > 1 else 1
    
    def getHeight(self):
        """ブロックの高さを取得"""
        return self.data.shape[0]
    
