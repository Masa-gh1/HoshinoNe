'''
ほしのね - Visual Flow-based Image Processing Tool

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

Created on 2025/10/21
@author: Masakazu Inoue
'''

import sys
import os

if getattr(sys, 'frozen', False):
    # PyInstaller によってフリーズされた
    # 実行ファイルのあるディレクトリを sys.path の
    # 最優先位置に追加しモジュールの実行時ロードを可能にする
    applicationPath = os.path.dirname(sys.executable)
    sys.path.insert(0, applicationPath)
else:
    applicationPath = os.path.dirname(__file__)

import tkinter as tk
from main.FlowEditor import FlowEditor
from utils.Debug import Debug

if __name__ == '__main__':
    if 1 < len(sys.argv):
        filename = sys.argv[1]
    else:
        filename = None

    root = tk.Tk()
    app = FlowEditor(root,"ほしのね")
    app.applicationHome = applicationPath
    Debug.applicationHome = applicationPath

    if filename:
        app.loadFlow(filePath=filename)

    root.mainloop()
