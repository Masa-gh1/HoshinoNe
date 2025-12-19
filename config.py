'''
Configuration settings for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

try:
    import numpy as np
except ImportError:
    print("numpyライブラリがインストールされていません。\npip install numpy でインストールしてください。")
    exit()

from version import VERSION_DATE

# varsion
VERSION = f"0.1.{VERSION_DATE}"

# ノードの並列処理ワーカー数設定
MAX_WORKERS = 8

# デフォルトのブロックデータタイプ
DEFAULT_BLOCK_TYPE = np.float32
DEFAULT_BLOCK_TYPE_BYTES = DEFAULT_BLOCK_TYPE().itemsize

# ブロックサイズ設定
BLOCK_SIZE = 256

# ブロックキャッシュサイズ設定
MAX_BLOCK_CACHE_SIZE = 16000

# ブロック辺りの推定 byte 数 (画像なら)
ESTIMATE_SIZE_PER_BLOCK = BLOCK_SIZE * BLOCK_SIZE * DEFAULT_BLOCK_TYPE_BYTES

# データヘッダに含める Exif
HEADERS_EXIF = [
    # name                tag                        converter
    ("Make"             , "Make"                   , str),
    ("Model"            , "Model"                  , str),
    ("ImageWidth"       , "ImageWidth"             , int),
    ("ImageWidth"       , "ExifImageWidth"         , int),
    ("ImageLength"      , "ImageLength"            , int),
    ("ImageLength"      , "ExifImageHeight"        , int),
    ("LensModel"        , "LensModel"              , str),
    ("FocalLength"      , "FocalLength"            , float),
    ("FNumber"          , "FNumber"                , float),
    ("ExposureTime"     , "ExposureTime"           , float),
    ("ISOSpeedRatings"  , "ISO"                    , int),
    ("ISOSpeedRatings"  , "ISOSpeedRatings"        , int),
    ("ISOSpeedRatings"  , "PhotographicSensitivity", int),
]
HEADERS_EXIF_OPT = [
    # 位置情報
    ("GPSLatitude"      , "GPSLatitude"            , float),
    ("GPSLongitude"     , "GPSLongitude"           , float),
    ("GPSAltitude"      , "GPSAltitude"            , float),
    # 著作権情報
    ("Artist"           , "Artist"                 , str),
    ("Copyright"        , "Copyright"              , str),
    # カメラ設定
    ("Flash"            , "Flash"                  , str),
    ("MeteringMode"     , "MeteringMode"           , str),
    ("ExposureMode"     , "ExposureMode"           , str),
    ("WhiteBalance"     , "WhiteBalance"           , str),
    # レンズ情報
    ("LensSerialNumber" , "LensSerialNumber"       , str),
    ("LensMake"         , "LensMake"               , str),
    # 色空間・解像度
    ("ColorSpace"       , "ColorSpace"             , str),
    ("WhitePoint"       , "WhitePoint"             , str),
    ("Orientation"      , "Orientation"            , int),
    ("XResolution"      , "XResolution"            , float),
    ("YResolution"      , "YResolution"            , float),
    ("ResolutionUnit"   , "ResolutionUnit"         , int),
]

# RAW読み込み設定 ref https://www.libraw.org/docs/API-datastruct.html
def configRawParams(params):
    # rawpy 0.25.1 パラメータ
    # 初期値メンバ                 既定値         初期値
    #params.aber               = (1, 1)       # tuple: (1, 1)
    #params.gamm               = (0.45, 4.5)  # tuple: (0.45, 4.5)
    #params.user_mul           = [0, 0, 0, 0] # list:  [0, 0, 0, 0]
    #params.bright             = 1.0          # float: 1.0
    #params.threshold          = 0.0          # float: 0.0
    #params.half_size          = False        # bool:  False
    #params.four_color_rgb     = False        # bool:  False
    #params.highlight          = 0            # int:   0
    #params.use_auto_wb        = False        # bool:  False
    #params.use_camera_wb      = False        # bool:  False
    #params.output_color       = 1            # int:   1
    #params.bad_pixels         = None         # -:     None
    params.output_bps          = 16           # int:   8
    #params.user_flip          = -1           # int:   -1
    #params.user_qual          = -1           # int:   -1  
    params.user_black          = 0            # int:   -1
    #params.user_sat           = -1           # int:   -1
    #params.med_passes         = 0            # int:   0
    params.no_auto_bright      = True         # bool:  False
    #params.auto_bright_thr    = 0.01         # float: 0.01
    #params.adjust_maximum_thr = 0.75         # float: 0.75
    #params.dcb_iterations     = 0            # int:   0
    #params.dcb_enhance_fl     = False        # bool:  False
    #params.fbdd_noiserd       = 0            # int:   0
    #params.exp_correc         = -1           # int:   -1
    #params.exp_shift          = 1.0          # float: 1.0
    #params.exp_preser         = 0.0          # float: 0.0
    params.no_auto_scale       = True         # bool:  False
