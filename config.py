'''
Configuration settings for FlowEditor

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

# ノードの並列処理ワーカー数設定
MAX_WORKERS = 4

# ブロックサイズ設定
BLOCK_SIZE = 256

# ブロックキャッシュサイズ設定
MAX_BLOCK_CACHE_SIZE = 2000

# Exif デバッグ出力設定
EXIF_DEBUG_OUTPUT = True

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

# RAW読み込み設定 ref https://www.libraw.org/docs/API-datastruct.html
def configRawParams(params):
    # rawpy 0.25.1 パラメータ
    # 初期値メンバ                 規定値         初期値
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
