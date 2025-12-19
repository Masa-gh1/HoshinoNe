'''
ConfigurableNode interface

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import ABC as AbstractBaseClass, abstractmethod

class ConfigurableNode(AbstractBaseClass):
    """設定可能なノードのインターフェース"""
    
    @abstractmethod
    def createSettingWindow(self):
        """設定ダイアログを開く"""
        pass
    
    @abstractmethod
    def getConfigHash(self):
        """設定のハッシュ値を取得"""
        pass
    
    @abstractmethod
    def store(self, nodeData):
        """設定をデータに保存"""
        pass
    
    @abstractmethod
    def restore(self, nodeData):
        """データから設定を復元"""
        pass