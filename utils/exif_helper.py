'''
EXIF情報取得ヘルパー

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from  fractions import Fraction
import datetime
import os
import sys

from config import HEADERS_EXIF, HEADERS_EXIF_OPT
from .Debug import Debug

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

def getExif(filepath):
    """EXIF情報を取得（キャッシュ付き）"""
    if filepath in _exif_cache:
        return _exif_cache[filepath]
    
    attr = {}
    
    # PILからEXIF情報を取得
    if PIL_AVAILABLE:
        pil_exif = _getPilExif(filepath, attr)
    else:
        Debug.log(__file__, "ライブラリ PIL がインストールされていません\npip install pillow でインストールしてください。")
        pil_exif = {}
    
    expected_tags = [name for name, _, _ in (HEADERS_EXIF + HEADERS_EXIF_OPT)]
    missing_tags = [tag for tag in expected_tags if tag not in attr]
    
    if not missing_tags:
        exifread_tags = {}
    elif EXIFREAD_AVAILABLE:
        # 不足情報をexifreadで補完
        exifread_tags = _getExifread(filepath, attr)
    else:
        Debug.log(__file__, "ライブラリ exifread がインストールされていません\npip install ExifRead でインストールしてください。")
        exifread_tags = {}
    
    expected_tags = [name for name, _, _ in HEADERS_EXIF]
    missing_tags = [tag for tag in expected_tags if tag not in attr]
    
    if Debug.LEVEL_NONE < Debug.LEVEL and missing_tags:
        # デバッグ出力
        _debugMissingTags(filepath, missing_tags, pil_exif, exifread_tags)
    
    result = attr if attr else None
    _exif_cache[filepath] = result
    return result

def _getPilExif(filepath, attr):
    """PILからEXIF情報を取得"""
    pil_exif = {}
    if not PIL_AVAILABLE:
        return pil_exif
    
    try:
        with Image.open(filepath) as img:
            pil_exif = img._getexif() if hasattr(img, '_getexif') else img.getexif()
            
            for tag_id, value in pil_exif.items():
                tag = TAGS.get(tag_id, tag_id)
                
                try:
                    for name, tag_name, converter in (HEADERS_EXIF + HEADERS_EXIF_OPT):
                        if(  (name not in attr)
                            and(tag_name == tag)
                            ):
                            if False:
                                pass
                            else:
                                attr[name] = converter(value)
                            break
                except (ValueError):
                    print(f"PIL EXIF error for {tag} = {value} : {e}", file=sys.stderr)
                    continue
    except Exception as e:
        print(f"PIL EXIF error for {filepath}: {e}", file=sys.stderr)
    
    return pil_exif

def _getExifread(filepath, attr):
    """exifreadからEXIF情報を取得（不足分のみ）"""
    exifread_tags = {}
    
    try:
        with open(filepath, 'rb') as f:
            exifread_tags = exifread.process_file(f)
            
            for tag, value in exifread_tags.items():
                try:
                    for name, tag_name, converter in (HEADERS_EXIF + HEADERS_EXIF_OPT):
                        if(  (name not in attr)
                          and(tag_name in tag.split(' '))
                          ):
                            if isinstance(value.values,list) and 2 <= len(value.values):
                                vs = []
                                for v in value.values:
                                    vs.append(converter(v))
                                attr[name] = vs
                            elif isinstance(value.values,list):
                                attr[name] = converter(value.values[0])
                            else:
                                attr[name] = converter(value.values)
                            break
                except (ValueError) as e:
                    print(f"exifread error for {tag} = {value} : {e}", file=sys.stderr)
                    continue
    except Exception as e:
        print(f"exifread error for {filepath}: {e}", file=sys.stderr)
    
    return exifread_tags

def _debugMissingTags(filepath, missing_tags, pil_exif, exifread_tags):
    """不足しているEXIFタグをデバッグ出力"""
    if missing_tags:
        print(f"Debug: Missing EXIF tags for {os.path.basename(filepath)}: {missing_tags}", file=sys.stderr)
        if pil_exif:
            print(f"Debug: Available PIL EXIF tags:", file=sys.stderr)
            for tag_id, value in pil_exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if len(str(value)) < 100:
                    print(f"  {tag_id}: {tag} = {value}", file=sys.stderr)
        if exifread_tags:
            print(f"Debug: Available exifread EXIF tags:", file=sys.stderr)
            for tag, value in exifread_tags.items():
                if len(str(value)) < 100:
                    print(f"  {tag} = {value}", file=sys.stderr)

def clearCache():
    """キャッシュをクリア"""
    global _exif_cache
    _exif_cache.clear()

def toDatetime(exifdt):
    """EXIF の日時文字列を datetime オブジェクトに変換"""
    if not exifdt:
        return None
    elif not exifdt.replace(":", "").strip(): # 不明の場合、: だけか、すべて空白 (Exif 2.3)
        return None
    else:
        return datetime.datetime.strptime(exifdt, "%Y:%m:%d %H:%M:%S")

def toExifDatetime(dt):
    """datetime オブジェクトを EXIF の日時文字列に変換"""
    if not dt:
        return "    :  :     :  :  "
    else:
        return dt.strftime("%Y:%m:%d %H:%M:%S")
