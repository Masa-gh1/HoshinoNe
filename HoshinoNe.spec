# -*- mode: python ; coding: utf-8 -*-

import os
from PIL import Image

# icon.png から icon.ico を自動生成する
icon_png = 'icon.png'
icon_ico = 'icon.ico'
if os.path.exists(icon_png):
    try:
        img = Image.open(icon_png)
        # Windowsの各種表示に合わせた複数サイズの入った.icoファイルを生成
        img.save(icon_ico, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    except Exception as e:
        print(f"Failed to convert icon: {e}")

def getNodesFilrs():
    nodedir = ['nodes/basic','nodes/preset','nodes/extra']
    result = []
    for nodes in nodedir:
        for root, dirs, files in os.walk(nodes):
            for file in files:
                if file.endswith('.py'): # .py だけを含める
                    rel  = os.path.relpath(root, nodes)
                    src  = os.path.join(root, file)
                    dest = os.path.join(nodes, rel)
                    result.append((src, dest))
    # 実行ファイル内に icon.ico を同梱する
    if os.path.exists(icon_ico):
        result.append((icon_ico, '.'))
    return result

def getImportNodes():
    nodedir = ['nodes/basic','nodes/preset','nodes/extra']
    result = []
    for nodes in nodedir:
        for root, dirs, files in os.walk(nodes):
            for file in files:
                if file.endswith('.py'): # .py だけを含める
                    src = os.path.join(root, file)
                    name,ext = os.path.splitext(src)
                    result.append(name.replace('/','.').replace('\\','.'))
    return result

a = Analysis(
    ['HoshinoNe.py'],
    pathex=[],
    binaries=[],
    datas=getNodesFilrs(),
    hiddenimports=getImportNodes(),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HoshinoNe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_ico if os.path.exists(icon_ico) else None, # 生成された .ico を指定
)
