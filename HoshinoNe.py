'''
ほしのね - Visual Flow-based Image Processing Tool

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

Created on 2025/10/21
@author: Masakazu Inoue
'''

import tkinter as tk
from main.FlowEditor import FlowEditor

if __name__ == '__main__':
    root = tk.Tk()
    app = FlowEditor(root,"ほしのね")
    root.mainloop()
