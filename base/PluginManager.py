'''
PluginManager - プラグイン管理システム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import os
import sys
import importlib.util
from .CacheManager import CacheManager

class PluginManager:

    _pluginDir = None

    @classmethod
    def getPluginDir(cls):
        """プラグインディレクトリを取得"""
        cls._pluginDir = os.path.join(os.path.expanduser("~"), ".hoshinone", "plugins")
        os.makedirs(cls._pluginDir, exist_ok=True)
        return cls._pluginDir
    
    @classmethod
    def loadPlugins(cls):
        """プラグインを動的読み込み"""
        pluginDir = cls.getPluginDir()
        plugins = []
        
        for item in os.listdir(pluginDir):
            itemPath = os.path.join(pluginDir, item)
            if os.path.isdir(itemPath):
                initFile = os.path.join(itemPath, "__init__.py")
                if os.path.exists(initFile):
                    try:
                        spec = importlib.util.spec_from_file_location(item, initFile)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        plugins.append(module)
                    except Exception as e:
                        print(f"Plugin load error: {item} - {e}")
        
        return plugins