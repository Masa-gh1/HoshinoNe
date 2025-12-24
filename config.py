'''
Configuration settings for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from fractions import Fraction

try:
    import numpy as np
except ImportError:
    print("ライブラリ numpy がインストールされていません。\npip install numpy でインストールしてください。")
    exit()

# ノードの並列処理ワーカー数設定
MAX_WORKERS = 8

# デフォルトのブロックデータタイプ
DEFAULT_BLOCK_TYPE = np.float32
DEFAULT_BLOCK_TYPE_BYTES = DEFAULT_BLOCK_TYPE().itemsize

# ブロックキャッシュサイズ設定(GB)
MAX_BLOCK_CACHE_SIZE_GB = 8

# ブロックサイズ設定
# ベイヤーを処理する場合、ベイヤーのサイズの倍数にしてください
BLOCK_SIZE = 256

# ブロック当たりの推定 byte 数 (画像なら)
ESTIMATE_SIZE_PER_BLOCK = BLOCK_SIZE * BLOCK_SIZE * DEFAULT_BLOCK_TYPE_BYTES

# ブロックキャッシュサイズ設定(ブロック数)
# キャッシュサイズが 32768 を超えるとパフォーマンスが下がる PC 構成があります。
# 恐らく CPU キャッシュサイズと python の dict の実装に関係していると思われます。
MAX_BLOCK_CACHE_SIZE = MAX_BLOCK_CACHE_SIZE_GB*1024*1024*1024//ESTIMATE_SIZE_PER_BLOCK

# 画像読み書きノードで使用する
# データヘッダに含める Exif
HEADERS_EXIF = [
    # name                       tag                         converter
    # 0th IFD TIFF Tag
    ("ImageWidth"              , "ImageWidth"              , int         ),
    ("ImageWidth"              , "ExifImageWidth"          , int         ),
    ("ImageLength"             , "ImageLength"             , int         ),
    ("ImageLength"             , "ExifImageHeight"         , int         ),
    ("DateTime"                , "DateTime"                , str         ),
    ("ExposureTime"            , "ExposureTime"            , Fraction    ),
    ("FNumber"                 , "FNumber"                 , Fraction    ),
    ("ISOSpeed"                , "ISOSpeed"                , int         ),
    ("ISOSpeed"                , "ISO"                     , int         ),
    ("ISOSpeed"                , "ISOSpeedRatings"         , int         ),
    ("ISOSpeed"                , "PhotographicSensitivity" , int         ),
    ("DateTimeOriginal"        , "DateTimeOriginal"        , str         ),
    ("DateTimeDigitized"       , "DateTimeDigitized"       , str         ),
    ("FocalLength"             , "FocalLength"             , Fraction    ),
    # 0th IFD Exif Private Tag
    ("ColorSpace"              , "ColorSpace"              , str         ),
    ("FocalPlaneXResolution"   , "FocalPlaneXResolution"   , Fraction    ),
    ("FocalPlaneYResolution"   , "FocalPlaneYResolution"   , Fraction    ),
    ("FocalPlaneResolutionUnit", "FocalPlaneResolutionUnit", int         ),
]
HEADERS_EXIF_OPT = [
    # name                       tag                        converter
    # 0th IFD TIFF Tag
    ("Make"                    , "Make"                    , str         ),
    ("Model"                   , "Model"                   , str         ),
    ("Orientation"             , "Orientation"             , int         ),
    ("XResolution"             , "XResolution"             , Fraction    ),
    ("YResolution"             , "YResolution"             , Fraction    ),
    ("ResolutionUnit"          , "ResolutionUnit"          , int         ),
    ("Artist"                  , "Artist"                  , str         ),
    ("Copyright"               , "Copyright"               , str         ),
    # 0th IFD Exif Private Tag
    ("MeteringMode"            , "MeteringMode"            , str         ),
    ("Flash"                   , "Flash"                   , str         ),
    ("WhiteBalance"            , "WhiteBalance"            , str         ),
    ("ExposureMode"            , "ExposureMode"            , str         ),
    ("LensMake"                , "LensMake"                , str         ),
    ("LensModel"               , "LensModel"               , str         ),
    # 0th IFD GPS Info Tag
    ("GPSLatitude"             , "GPSLatitude"             , Fraction    ),
    ("GPSLongitude"            , "GPSLongitude"            , Fraction    ),
    ("GPSAltitude"             , "GPSAltitude"             , Fraction    ),
]

# RawReaderNode 用
# 選択し入れるデモザイクアルゴリズム
# ここには無い、"bayer", "bayer crop", "unpack", "raw" はプリセットされています。
RAW_DEMOSAIC_ALGORITHMS = {
    # name  text
    "AHD" : "適応的同質性指向アルゴリズム:高品質だが処理時間が長い",
    "AAHD": "適応的AHD:AHDの改良版",
    "VNG" : "可変勾配数アルゴリズム:バランスの取れた品質と速度",
    "PPG" : "パターン化ピクセルグループ化:高速だが品質は劣る",
}
# RAW 読み込み設定 ref https://www.libraw.org/docs/API-datastruct.html
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
