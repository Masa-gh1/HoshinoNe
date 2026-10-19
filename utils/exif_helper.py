'''
EXIF情報取得ヘルパー

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from  fractions import Fraction
import datetime
import os
import sys

from config import HEADERS, HEADERS_EXIF
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
        result = _exif_cache[filepath]
        return normalize(result), result
    
    attr = {}
    
    # PILからEXIF情報を取得
    if PIL_AVAILABLE:
        _attr, pil_exif = _getPilExif(filepath)
        attr.update(_attr)
    else:
        Debug.log(__name__, "ライブラリ PIL がインストールされていません\npip install pillow でインストールしてください。")
        pil_exif = {}
    
    tagMap = {id:name for id, name, _, _ in HEADERS_EXIF}
    expectedTags = tagMap
    missingTags = [id for id in expectedTags if id not in attr]
    
    if not missingTags:
        exifread_tags = {}
    elif EXIFREAD_AVAILABLE:
        # 不足情報をexifreadで補完
        _attr, exifread_tags = _getExifread(filepath)
        attr.update({id: _attr[id] for id in missingTags if id in _attr})
    else:
        Debug.log(__name__, "ライブラリ exifread がインストールされていません\npip install ExifRead でインストールしてください。")
        exifread_tags = {}
    
    expectedTags = {id for id, _, _, _ in HEADERS_EXIF}
    missingTags = [id for id in expectedTags if id not in attr]
    
    result = {tagMap[id]:value for id, value in attr.items()} if attr else None
    norm = normalize(result)

    if Debug.LEVEL_NONE < Debug.LEVEL and None in norm.values():
        # デバッグ出力
        _debugMissingTags(filepath, missingTags, pil_exif, exifread_tags)
    
    _exif_cache[filepath] = result
    return norm, result

def _getPilExif(filepath):
    """PILからEXIF情報を取得"""
    allExif = {}
    result = {}

    if not PIL_AVAILABLE:
        return result, allExif
    
    try:
        with Image.open(filepath) as img:
            allExif = img._getexif() if hasattr(img, '_getexif') else img.getexif()
            
            try:
                for id, name, converter, count in HEADERS_EXIF:
                    if id in allExif:
                        values = allExif[id]
                        if isinstance(values, (list,tuple)) and 2 <= len(values):
                            vs = []
                            for v in values:
                                vs.append(converter(v))
                            result[id] = tuple(vs)
                        elif isinstance(values, (list,tuple)):
                            result[id] = converter(values[0])
                        else:
                            result[id] = converter(values)

            except (ValueError):
                Debug.log(__name__, f"PIL EXIF error for {id} = {values}", e)
    except Exception as e:
        Debug.log(__name__, f"PIL EXIF error for {filepath}", e)
    
    return result, allExif

def _getExifread(filepath):
    """exifreadからEXIF情報を取得（不足分のみ）"""
    allExif = {}
    result = {}

    if not EXIFREAD_AVAILABLE:
        return result, allExif
    
    try:
        with open(filepath, 'rb') as f:
            orgExif = exifread.process_file(f)
            allExif = {value.tag: value for name, value in orgExif.items() if name.startswith('Image') or name.startswith('EXIF')}
            
            try:
                for id, name, converter, count in HEADERS_EXIF:
                    if id in allExif:
                        values = allExif[id].values
                        if isinstance(values, list) and 2 <= len(values):
                            vs = []
                            for v in values:
                                if isinstance(v, tuple):
                                    vs.append(converter(*v))
                                else:
                                    vs.append(converter(v))
                            result[id] = tuple(vs)
                        elif isinstance(values, list):
                            if isinstance(values[0], tuple):
                                result[id] = converter(*values[0])
                            else:
                                result[id] = converter(values[0])
                        else:
                            if isinstance(values, tuple):
                                result[id] = converter(*values)
                            else:
                                result[id] = converter(values)
            except (ValueError) as e:
                Debug.log(__name__, f"exifread error for {id} = {values}", e)
    except Exception as e:
        Debug.log(__name__, f"exifread error for {filepath}", e)
    
    return result, allExif

def normalize(exif):
    """EXIF から画像処理に必要な情報を取り出す"""
    result = {}
    
    if not exif:
        return result
    
    for name, tag in HEADERS:
        if name in result and result[name]:
            pass
        elif isinstance(tag,str) and tag in exif:
            result[name] = exif[tag]
        elif isinstance(tag,str):
            result[name] = None
        elif callable(tag):
            result[name] = tag(exif)
        else:
            result[name] = None
    
    return result

def _debugMissingTags(filepath, missing_tags, pil_exif, exifread_tags):
    """不足しているEXIFタグをデバッグ出力"""
    if missing_tags:
        print(f"Debug: Missing EXIF tags for {os.path.basename(filepath)}: {missing_tags}", file=sys.stderr)
        if pil_exif:
            print(f"Debug: Available PIL EXIF tags:", file=sys.stderr)
            for id, value in pil_exif.items():
                name = TAGS.get(id, id)
                if len(str(value)) < 100:
                    print(f"  {id}: {name} = {value}", file=sys.stderr)
        if exifread_tags:
            print(f"Debug: Available exifread EXIF tags:", file=sys.stderr)
            for id, value in exifread_tags.items():
                name = TAGS.get(id, id)
                if isinstance(value.values, (tuple,list)) and 0 < len(value.values):
                    s = f"({",".join([str(v) for v in value.values])})"
                    s = s if len(s)<100 else s[:100] + " ..."
                else:
                    s = str(value.values)
                
                print(f"  {id}: {name} = {s} {value}", file=sys.stderr)

def clearCache():
    """キャッシュをクリア"""
    global _exif_cache
    _exif_cache.clear()

def toDatetime(exifdt, exifsubsec = None):
    """EXIF の日時文字列を datetime オブジェクトに変換"""
    if not exifdt:
        return None
    elif not exifdt.replace(":", "").strip(): # 不明の場合、: だけか、すべて空白 (Exif 2.3)
        return None
    elif exifsubsec:
        return datetime.datetime.strptime(exifdt+"."+exifsubsec, "%Y:%m:%d %H:%M:%S.%f")
    else:
        return datetime.datetime.strptime(exifdt, "%Y:%m:%d %H:%M:%S")

def toExifDatetime(dt):
    """datetime オブジェクトを EXIF の日時文字列に変換"""
    if not dt:
        return "    :  :     :  :  "
    else:
        return dt.strftime("%Y:%m:%d %H:%M:%S")

def getFocalCenter(info:dict[str,Any]) -> list[float]:
    """EXIF から焦点位置を取得"""
    from utils import numpy_helpers as nh
    
    trans  = info["transformation"]
    width  = info["width"]
    height = info["height"]
    
    center = ((trans @ nh.array([[width / 2.0], [height / 2.0], [1.0]])).ravel()[:2]).tolist()
    return center

def getFocalLength(info:dict[str,Any]) -> float|None:
    """EXIF から焦点距離を取得"""
    focalLength = info["focal_length"] if "focal_length" in info else None
    return focalLength

def getResolution(info:dict[str,Any]) -> tuple[float,float]|None:
    """EXIF から解像度を取得"""
    from utils import numpy_helpers as nh
    
    trans   = info["transformation"]
    xRes    = info["focal_plane_x_resolution"]    if "focal_plane_x_resolution"    in info else None
    yRes    = info["focal_plane_y_resolution"]    if "focal_plane_y_resolution"    in info else None
    resUnit = info["focal_plane_resolution_unit"] if "focal_plane_resolution_unit" in info else None
    
    if   xRes is None or yRes is None or resUnit is None: # 未指定
        pass
    elif "inch" == resUnit: # inch
        xRes = xRes / 25.4
        yRes = yRes / 25.4
    elif "cm" == resUnit: # cm
        xRes = xRes / 10.0
        yRes = yRes / 10.0
    elif "mm" == resUnit: # mm
        xRes = xRes / 1.0
        yRes = yRes / 1.0
    elif "um" == resUnit: # um
        xRes = xRes / 0.001
        yRes = yRes / 0.001
    else:
        raise ValueError(f"Unsupported FocalPlaneResolutionUnit {resUnit}")
    
    resolution = (trans @ nh.array([[1.0, 0.0],
                                    [0.0, 1.0],
                                    [0.0, 0.0]]))
    resolution = (xRes * float(resolution[0,0]), yRes * float(resolution[1,1])) if xRes and yRes else None
    return resolution


def getFov(info:dict[str,Any], width, height) -> float|None:
    """EXIF から画角を取得"""
    import numpy as np
    from utils import numpy_helpers as nh
    
    center      = getFocalCenter(info)
    focalLength = getFocalLength(info)
    resolution  = getResolution(info)
    
    if resolution is None or focalLength is None:
        fov = None
    else:
        # center が中央でない場合を考慮した対角画角を計算
        v = nh.array([
            [(    0 - center[0]) / resolution[0], (     0 - center[1]) / resolution[1], focalLength], # 左上
            [(width - center[0]) / resolution[0], (     0 - center[1]) / resolution[1], focalLength], # 右上
            [(    0 - center[0]) / resolution[0], (height - center[1]) / resolution[1], focalLength], # 左下
            [(width - center[0]) / resolution[0], (height - center[1]) / resolution[1], focalLength], # 右下
        ])
        v = v / np.linalg.norm(v, axis=1, keepdims=True)
        cosTheta = v @ v.T
        fov = np.degrees(np.max(np.arccos(np.clip(cosTheta, -1, 1))))
    return fov
