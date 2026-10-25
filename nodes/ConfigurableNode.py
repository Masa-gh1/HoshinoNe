'''
ConfigurableNode interface

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from abc import ABC as AbstractBaseClass, abstractmethod
import tkinter as tk

class ConfigurableNode(AbstractBaseClass):
    """設定可能なノードのインターフェース"""
    
    @abstractmethod
    def createSettingWindow(self) -> tk.Toplevel:
        """設定ダイアログを開く"""
        pass
    
    @abstractmethod
    def getConfigHash(self) -> str:
        """設定のハッシュ値を取得"""
        pass
    
    @abstractmethod
    def store(self, nodeData: dict):
        """設定をデータに保存"""
        pass
    
    @abstractmethod
    def restore(self, nodeData: dict):
        """データから設定を復元"""
        pass