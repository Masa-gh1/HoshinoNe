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
    executablePath = os.path.dirname(sys.executable)
    sys.path.insert(0, executablePath)
    applicationPath = sys._MEIPASS
else:
    executablePath = os.path.dirname(__file__)
    applicationPath = executablePath

import tkinter as tk
from main.FlowEditor import FlowEditor
from utils.Debug import Debug

if __name__ == '__main__':
    if 1 < len(sys.argv):
        filename = sys.argv[1]
    else:
        filename = None

    # Windows環境でタスクバーのアイコンを独自のものに反映させるための処理
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoshinone.floweditor.app")
        except Exception:
            pass

    root = tk.Tk()
    root.iconbitmap(os.path.join(applicationPath, "icon.ico"))
    app = FlowEditor(root,"ほしのね")
    app.applicationHome = executablePath
    Debug.applicationHome = executablePath

    if filename:
        app.loadFlow(filePath=filename)

    root.mainloop()
