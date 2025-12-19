'''
EXIF情報取得ヘルパー

@author: Masakazu Inoue
'''

import os
import sys
import datetime
from config import HEADERS_EXIF

# グローバルキャッシュ
_exif_cache = {}

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import exifread
    EXIFREAD_AVAILABLE = True
except ImportError:
    EXIFREAD_AVAILABLE = False

def get_exif(filepath):
    """EXIF情報を取得（キャッシュ付き）"""
    if filepath in _exif_cache:
        return _exif_cache[filepath]
    
    attr = {}
    pil_exif = {}
    
    # PILからEXIF情報を取得
    if PIL_AVAILABLE:
        pil_exif = _get_pil_exif(filepath, attr)
    
    # 不足情報をexifreadで補完
    if EXIFREAD_AVAILABLE:
        exifread_tags = _get_exifread_exif(filepath, attr)
    else:
        exifread_tags = {}
    
    # デバッグ出力
    _debug_missing_tags(filepath, attr, pil_exif, exifread_tags)
    
    result = attr if attr else None
    _exif_cache[filepath] = result
    return result

def _get_pil_exif(filepath, attr):
    """PILからEXIF情報を取得"""
    pil_exif = {}
    try:
        with Image.open(filepath) as img:
            pil_exif = img._getexif() if hasattr(img, '_getexif') else img.getexif()
            
            if pil_exif:
                for tag_id, value in pil_exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    
                    try:
                        # DateTime特別処理
                        if tag in ["DateTime", "DateTimeOriginal", "DateTimeDigitized"]:
                            for fmt in ["%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
                                try:
                                    dt = datetime.datetime.strptime(str(value), fmt)
                                    if "DateTime" not in attr or dt.timestamp() < attr["DateTime"]:
                                        attr["DateTime"] = dt.timestamp()
                                    break
                                except ValueError:
                                    continue
                        # HEADERS_EXIFによる一般化処理
                        else:
                            for name, tag_name, converter in HEADERS_EXIF:
                                if tag == tag_name:
                                    if converter == float:
                                        attr[name] = float(value) if hasattr(value, '__float__') else float(value.real) if hasattr(value, 'real') else value
                                    else:
                                        attr[name] = converter(value)
                                    break
                    except (ValueError, TypeError, AttributeError):
                        continue
    except Exception as e:
        print(f"PIL EXIF error for {filepath}: {e}", file=sys.stderr)
    
    return pil_exif

def _get_exifread_exif(filepath, attr):
    """exifreadからEXIF情報を取得（不足分のみ）"""
    expected_tags = ["DateTime"] + [name for name, _, _ in HEADERS_EXIF]
    missing_tags = [tag for tag in expected_tags if tag not in attr]
    exifread_tags = {}
    
    if missing_tags:
        try:
            with open(filepath, 'rb') as f:
                exifread_tags = exifread.process_file(f)
                
                for tag, value in exifread_tags.items():
                    try:
                        # DateTime特別処理
                        if "DateTime" in tag and "DateTime" not in attr:
                            val_str = str(value)
                            for fmt in ["%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
                                try:
                                    dt = datetime.datetime.strptime(val_str, fmt)
                                    attr["DateTime"] = dt.timestamp()
                                    break
                                except ValueError:
                                    continue
                        # HEADERS_EXIFによる一般化処理
                        else:
                            for name, tag_name, converter in HEADERS_EXIF:
                                if(  (name not in attr)
                                  and(tag_name in tag.split(' '))
                                  ):
                                    
                                    val_str = str(value)
                                    if converter == float and '/' in val_str:
                                        # 分数値の処理
                                        num, den = val_str.split('/')
                                        den_val = float(den)
                                        if den_val != 0:
                                            attr[name] = float(num) / den_val
                                        else:
                                            # 分母が0の場合は分子をそのまま使用（分母=1と仮定）
                                            attr[name] = float(num)
                                    else:
                                        attr[name] = converter(val_str)
                                    break
                    except (ValueError, ZeroDivisionError):
                        continue
        except Exception as e:
            print(f"exifread error for {filepath}: {e}", file=sys.stderr)
    
    return exifread_tags

def _debug_missing_tags(filepath, attr, pil_exif, exifread_tags):
    """不足しているEXIFタグをデバッグ出力"""
    expected_tags = ["DateTime"] + [name for name, _, _ in HEADERS_EXIF]
    missing_tags = [tag for tag in expected_tags if tag not in attr]
    
    if missing_tags:
        print(f"Debug: Missing EXIF tags for {os.path.basename(filepath)}: {missing_tags}", file=sys.stderr)
        if PIL_AVAILABLE and pil_exif:
            print(f"Debug: Available PIL EXIF tags:", file=sys.stderr)
            for tag_id, value in pil_exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if len(str(value)) < 100:
                    print(f"  {tag_id}: {tag} = {value}", file=sys.stderr)
        if EXIFREAD_AVAILABLE and exifread_tags:
            print(f"Debug: Available exifread EXIF tags:", file=sys.stderr)
            for tag, value in exifread_tags.items():
                if len(str(value)) < 100:
                    print(f"  {tag} = {value}", file=sys.stderr)
        if not EXIFREAD_AVAILABLE:
            print(f"Note: Install exifread library for better RAW EXIF support: pip install ExifRead", file=sys.stderr)

def clear_cache():
    """キャッシュをクリア"""
    global _exif_cache
    _exif_cache.clear()