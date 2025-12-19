import numpy as np
import os

def save_block_image(data, filename, title="Block Data"):
    """
    ブロックデータを画像ファイルとして保存
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
        
        if data is None:
            print("データがNoneです")
            return
        
        if len(data.shape) != 2:
            print(f"2D配列が必要です。現在の形状: {data.shape}")
            return
        
        plt.figure(figsize=(8, 8))
        
        if np.any(np.isnan(data)):
            # NaN用の表示
            display_data = data.copy()
            nan_mask = np.isnan(data)
            display_data[nan_mask] = -999
            
            valid_data = data[~nan_mask]
            if len(valid_data) > 0:
                vmin, vmax = np.min(valid_data), np.max(valid_data)
            else:
                vmin, vmax = -1, 1
            
            colors = ['red'] + plt.cm.gray(np.linspace(0, 1, 256)).tolist()
            cmap = ListedColormap(colors)
            
            plt.imshow(display_data, cmap=cmap, vmin=-999, vmax=vmax)
            plt.colorbar(label='Value (Red=NaN)')
        else:
            plt.imshow(data, cmap='gray')
            plt.colorbar(label='Value')
        
        plt.title(f"{title}\nShape: {data.shape}, Valid: {np.sum(~np.isnan(data))}/{data.size}")
        plt.xlabel('X')
        plt.ylabel('Y')
        
        filepath = f"c:/workspace/FlowEditor/debug/{filename}.png"
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"画像を保存しました: {filepath}")
        
    except ImportError:
        print("matplotlib が利用できません。テキスト表示を使用します。")
        show_block_text(data, title)

def show_block_text(data, title="Block Data"):
    """
    ブロックデータをテキストで表示（小さなブロック用）
    """
    if data is None:
        print("データがNoneです")
        return
    
    print(f"\n=== {title} ===")
    print(f"Shape: {data.shape}")
    
    if data.size <= 256:  # 16x16以下なら全表示
        print("データ内容:")
        for i in range(data.shape[0]):
            row_str = ""
            for j in range(data.shape[1]):
                val = data[i, j]
                if np.isnan(val):
                    row_str += "  NaN "
                else:
                    row_str += f"{val:6.1f}"
            print(row_str)
    else:
        print("データが大きすぎるため、統計情報のみ表示")

def show_block_info(data, title="Block Info"):
    """ブロックの詳細情報を表示"""
    if data is None:
        print("データがNoneです")
        return
    
    print(f"\n=== {title} ===")
    print(f"Shape: {data.shape}")
    print(f"Type: {data.dtype}")
    
    if np.any(np.isnan(data)):
        valid_data = data[~np.isnan(data)]
        nan_count = np.sum(np.isnan(data))
        print(f"Valid pixels: {len(valid_data)}/{data.size}")
        print(f"NaN pixels: {nan_count}")
        
        if len(valid_data) > 0:
            print(f"Valid range: {np.min(valid_data):.3f} to {np.max(valid_data):.3f}")
            print(f"Valid mean: {np.mean(valid_data):.3f}")
    else:
        print(f"Range: {np.min(data):.3f} to {np.max(data):.3f}")
        print(f"Mean: {np.mean(data):.3f}")

# 使用例をコメントで記載
"""
使用方法:

# デバッグコンソールで実行
import sys
sys.path.append('c:/workspace/FlowEditor')
from utils.debug_block_viewer import save_block_image, show_block_text, show_block_info

# ブロックデータを画像として保存
save_block_image(block.data, "input_block", "Input Block")
show_block_info(block.data, "Input Block Info")

# 小さなデータはテキスト表示
show_block_text(small_data, "Small Block")
"""