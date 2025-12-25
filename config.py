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
# HEADERS_EXIF は天体写真加工に欲しい情報
# HEADERS_EXIF_OPT は書き込み時に読み込み側から転記するだけの情報
HEADERS_EXIF = [
    #############################################################
    # 0th IFD TIFF Tag
    #   id  name                             型         個数     id    名称
    (  256, "ImageWidth"                   , int     ,     1), # 0100h 画像の幅
    (  257, "ImageLength"                  , int     ,     1), # 0101h 画像の高さ
    (  258, "BitsPerSample"                , int     ,     1), # 0102h 画像のビットの深さ
    (  306, "DateTime"                     , str     ,    20), # 0132h ファイル変更日時
    #############################################################
    # 0th IFD Exif Private Tag
    #   id  name                             型         個数     id    名称
    (33434, "ExposureTime"                 , Fraction,     1), # 829Ah 露出時間
    (33437, "FNumber"                      , Fraction,     1), # 829Dh F ナンバー
    (34867, "ISOSpeed"                     , int     ,     1), # 8833h ISO スピード
    (36867, "DateTimeOriginal"             , str     ,    20), # 9003h 原画像データの生成日時
    (36868, "DateTimeDigitized"            , str     ,    20), # 9004h デジタルデータの作成日時
    (37386, "FocalLength"                  , Fraction,     1), # 920Ah レンズ焦点距離
    (41486, "FocalPlaneXResolution"        , Fraction,     1), # A20Eh 焦点面の幅の解像度
    (41487, "FocalPlaneYResolution"        , Fraction,     1), # A20Fh 焦点面の高さの解像度
    (41488, "FocalPlaneResolutionUnit"     , int     ,     1), # A210h 焦点面解像度単位
]

HEADERS_EXIF_OPT = [
    #############################################################
    # 0th IFD TIFF Tag
    #   id  name                             型         個数     id    名称
#    (  256, "ImageWidth"                   , int     ,     1), # 0100h 画像の幅
#    (  257, "ImageLength"                  , int     ,     1), # 0101h 画像の高さ
#    (  258, "BitsPerSample"                , int     ,     1), # 0102h 画像のビットの深さ
#    (  259, "Compression"                  , int     ,     1), # 0103h 圧縮の種類
#    (  262, "PhotometricInterpretation"    , int     ,     1), # 0106h 画素構成
#    (  270, "ImageDescription"             , str     ,  None), # 010Eh 画像タイトル
    (  271, "Make"                         , str     ,  None), # 010Fh 画像入力機器のメーカ名
    (  272, "Model"                        , str     ,  None), # 0110h 画像入力機器のモデル名
#    (  273, "StripOffsets"                 , int     ,  None), # 0111h 画像データのロケーション
    (  274, "Orientation"                  , int     ,     1), # 0112h 画像方向
#    (  277, "SamplesPerPixel"              , int     ,     1), # 0115h コンポーネント数
#    (  278, "RowsPerStrip"                 , int     ,     1), # 0116h ストリップあたりの行数
#    (  279, "StripByteCounts"              , int     ,  None), # 0117h ストリップの総バイト数
    (  282, "XResolution"                  , Fraction,     1), # 011Ah 画像の幅の解像度
    (  283, "YResolution"                  , Fraction,     1), # 011Bh 画像の高さの解像度
#    (  284, "PlanarConfiguration"          , int     ,     1), # 011Ch 画像データの並び
    (  296, "ResolutionUnit"               , int     ,     1), # 0128h 画像の幅と高さの解像度の単位
#    (  301, "TransferFunction"             , int     , 3*256), # 012Dh 再生階調カーブ特性
#    (  305, "Software"                     , str     ,  None), # 0131h ソフトウェア
#    (  306, "DateTime"                     , str     ,    20), # 0132h ファイル変更日時
    (  315, "Artist"                       , str     ,  None), # 013Bh アーティスト
#    (  318, "WhitePoint"                   , Fraction,     2), # 013Eh 参照白色点の色度座標値
#    (  319, "PrimaryChromaticities"        , Fraction,     6), # 013Fh 原色の色度座標値
#    (  513, "JPEGInterchangeFormat"        , int     ,     1), # 0201h JPEG の SOI へのオフセット
#    (  514, "JPEGInterchangeFormatLength"  , int     ,     1), # 0202h JPEG データのバイト数
#    (  529, "YCbCrCoefficients"            , Fraction,     3), # 0211h 色変換マトリクス係数
#    (  530, "YCbCrSubSampling"             , int     ,     2), # 0212h YCC の画素構成(C の間引き率)
#    (  531, "YCbCrPositioning"             , int     ,     1), # 0213h YCC の画素構成(Y と C の位置)
#    (  532, "ReferenceBlackWhite"          , Fraction,     6), # 0214h 参照黒色点値と参照白色点値
    (33432, "Copyright"                    , str     ,  None), # 8298h 撮影著作権者/編集著作権者
#    (34665, "Exif IFD Pointer"             , int     ,     1), # 8769h Exif タグ
#    (34853, "GPSInfo IFD Pointer"          , int     ,     1), # 8825h GPS タグ
    #############################################################
    # 0th IFD Exif Private Tag
    #   id  name                             型         個数     id    名称
#    (33434, "ExposureTime"                 , Fraction,     1), # 829Ah 露出時間
#    (33437, "FNumber"                      , Fraction,     1), # 829Dh F ナンバー
#    (34850, "ExposureProgram"              , int     ,     1), # 8822h 露出プログラム
#    (34852, "SpectralSensitivity"          , str     ,  None), # 8824h スペクトル感度
#    (34855, "PhotographicSensitivity"      , int     ,  None), # 8827h 撮影感度
#    (34856, "OECF"                         , None    ,  None), # 8828h 光電変換関数
#    (34864, "SensitivityType"              , int     ,     1), # 8830h 感度種別
#    (34865, "StandardOutputSensitivity"    , int     ,     1), # 8831h 標準出力感度
#    (34866, "RecommendedExposureIndex"     , int     ,     1), # 8832h 推奨露光指数
#    (34867, "ISOSpeed"                     , int     ,     1), # 8833h ISO スピード
#    (34868, "ISOSpeedLatitudeyyy"          , int     ,     1), # 8834h ISO スピードラチチュード yyy
#    (34869, "ISOSpeedLatitudezzz"          , int     ,     1), # 8835h ISO スピードラチチュード zzz
#    (36864, "ExifVersion"                  , None    ,     4), # 9000h Exif バージョン
#    (36867, "DateTimeOriginal"             , str     ,    20), # 9003h 原画像データの生成日時
#    (36868, "DateTimeDigitized"            , str     ,    20), # 9004h デジタルデータの作成日時
#    (37121, "ComponentsConfiguration"      ), # 9101h 各コンポーネントの意味
#    (37122, "CompressedBitsPerPixel"       ), # 9102h 画像圧縮モード
#    (37377, "ShutterSpeedValue"            , Fraction,     1), # 9201h シャッタースピード
#    (37378, "ApertureValue"                , Fraction,     1), # 9202h 絞り値
#    (37379, "BrightnessValue"              , Fraction,     1), # 9203h 輝度値
#    (37380, "ExposureBiasValue"            , Fraction,     1), # 9204h 露光補正値
#    (37381, "MaxApertureValue"             , Fraction,     1), # 9205h レンズ最小Ｆ値
#    (37382, "SubjectDistance"              , Fraction,     1), # 9206h 被写体距離
#    (37383, "MeteringMode"                 , int     ,     1), # 9207h 測光方式
#    (37384, "LightSource"                  , int     ,     1), # 9208h 光源
#    (37385, "Flash"                        , int     ,     1), # 9209h フラッシュ
#    (37386, "FocalLength"                  , Fraction,     1), # 920Ah レンズ焦点距離
#    (37396, "SubjectArea"                  , int     ,  None), # 9214h 被写体領域
#    (37500, "MakerNote"                    , None    ,  None), # 927Ch メーカノート
#    (37510, "UserComment"                  , None    ,  None), # 9286h ユーザコメント
#    (37520, "SubSecTime"                   , str     ,  None), # 9290h DateTime のサブセック
#    (37521, "SubSecTimeOriginal"           , str     ,  None), # 9291h DateTimeOriginal のサブセック
#    (37522, "SubSecTimeDigitized"          , str     ,  None), # 9292h DateTimeDigitized のサブセック
#    (40960, "FlashpixVersion"              , None    ,     4), # A000h 対応フラッシュピックスバージョン
#    (40961, "ColorSpace"                   , int     ,     1), # A001h 色空間情報
#    (40962, "PixelXDimension"              , int     ,     1), # A002h 実効画像幅
#    (40963, "PixelYDimension"              , int     ,     1), # A003h 実効画像高さ
#    (40964, "RelatedSoundFile"             , str     ,    13), # A004h 関連音声ファイル
#    (40965, " Interoperability IFD Pointer", int     ,     1), # A005h 互換性 IFD へのポインタ
#    (41483, "FlashEnergy"                  , Fraction,     1), # A20Bh フラッシュ強度
#    (41484, "SpatialFrequencyResponse"     , None    ,  None), # A20Ch 空間周波数応答
#    (41486, "FocalPlaneXResolution"        , Fraction,     1), # A20Eh 焦点面の幅の解像度
#    (41487, "FocalPlaneYResolution"        , Fraction,     1), # A20Fh 焦点面の高さの解像度
#    (41488, "FocalPlaneResolutionUnit"     , int     ,     1), # A210h 焦点面解像度単位
#    (41492, "SubjectLocation"              , int     ,     2), # A214h 被写体位置
#    (41493, "ExposureIndex"                , Fraction,     1), # A215h 露出インデックス
#    (41495, "SensingMethod"                , int     ,     1), # A217h センサー方式
#    (41728, "FileSource"                   , None    ,     1), # A300h ファイルソース
#    (41729, "SceneType"                    , None    ,     1), # A301h シーンタイプ
#    (41730, "CFAPattern"                   , None    ,  None), # A302h CFA パターン
#    (41985, "CustomRendered"               , int     ,     1), # A401h 個別画像処理
#    (41986, "ExposureMode"                 , int     ,     1), # A402h 露出モード
#    (41987, "WhiteBalance"                 , int     ,     1), # A403h ホワイトバランス
#    (41988, "DigitalZoomRatio"             , Fraction,     1), # A404h デジタルズーム倍率
#    (41989, "FocalLengthIn35mmFilm"        , int     ,     1), # A405h 35mm 換算レンズ焦点距離
#    (41990, "SceneCaptureType"             , int     ,     1), # A406h 撮影シーンタイプ
#    (41991, "GainControl"                  , int     ,     1), # A407h ゲイン制御
#    (41992, "Contrast"                     , int     ,     1), # A408h 撮影コントラスト
#    (41993, "Saturation"                   , int     ,     1), # A409h 撮影彩度
#    (41994, "Sharpness"                    , int     ,     1), # A40Ah 撮影シャープネス
#    (41995, "DeviceSettingDescription"     , None    ,  None), # A40Bh 撮影条件記述情報
#    (41996, "SubjectDistanceRange"         , int     ,     1), # A40Ch 被写体距離レンジ
#    (42016, "ImageUniqueID"                , str     ,    33), # A420h 画像ユニーク ID
#    (42032, "CameraOwnerName"              , str     ,  None), # A430h カメラ所有者名
#    (42033, "BodySerialNumber"             , str     ,  None), # A431h カメラシリアル番号
#    (42034, "LensSpecification"            , Fraction,     4), # A432h レンズの仕様情報
    (42035, "LensMake"                     , str     ,  None), # A433h レンズのメーカ名
    (42036, "LensModel"                    , str     ,  None), # A434h レンズのモデル名
#    (42037, "LensSerialNumber"             , str     ,  None), # A435h レンズシリアル番号
#    (42240, "Gamma"                        , Fraction,     1), # A500h 再生ガンマ
    #############################################################
    # 0th IFD GPS Info Tag
    #   id  name                             型         個数     id    名称
#    (    0, "GPSVersionID"                 , bytes   ,     4), # 0000h GPS タグのバージョン
    (    1, "GPSLatitudeRef"               , str     ,     2), # 0001h 北緯(N)or 南緯(S)
    (    2, "GPSLatitude"                  , Fraction,     3), # 0002h 緯度（数値）
    (    3, "GPSLongitudeRef"              , str     ,     2), # 0003h 東経(E)or 西経(W)
    (    4, "GPSLongitude"                 , Fraction,     3), # 0004h 経度（数値）
#    (    5, "GPSAltitudeRef"               , bytes   ,     1), # 0005h 高度の基準
    (    6, "GPSAltitude"                  , Fraction,     1), # 0006h 高度（数値）
#    (    7, "GPSTimeStamp"                 , Fraction,     3), # 0007h GPS 時間（原子時計の時間）
#    (    8, "GPSSatellites"                , str     ,  None), # 0008h 測位につかった衛星信号
#    (    9, "GPSStatus"                    , str     ,     2), # 0009h GPS 受信機の状態
#    (   10, "GPSMeasureMode"               , str     ,     2), # 000Ah GPS の測位方法
#    (   11, "GPSDOP"                       , Fraction,     1), # 000Bh 測位の信頼性
#    (   12, "GPSSpeedRef"                  , str     ,     2), # 000Ch 速度の単位
#    (   13, "GPSSpeed"                     , Fraction,     1), # 000Dh 速度（数値）
#    (   14, "GPSTrackRef"                  , str     ,     2), # 000Eh 進行方向の単位
#    (   15, "GPSTrack"                     , Fraction,     1), # 000Fh 進行方向（数値）
#    (   16, "GPSImgDirectionRef"           , str     ,     2), # 0010h 撮影した画像の方向の単位
#    (   17, "GPSImgDirection"              , Fraction,     1), # 0011h 撮影した画像の方向（数値）
#    (   18, "GPSMapDatum"                  , str     ,  None), # 0012h 測位に用いた地図データ
#    (   19, "GPSDestLatitudeRef"           , str     ,     2), # 0013h 目的地の北緯(N)or 南緯(S)
#    (   20, "GPSDestLatitude"              , Fraction,     3), # 0014h 目的地の緯度（数値）
#    (   21, "GPSDestLongitudeRef"          , str     ,     2), # 0015h 目的地の東経(E)or 西経(W)
#    (   22, "GPSDestLongitude"             , Fraction,     3), # 0016h 目的地の経度（数値）
#    (   23, "GPSDestBearingRef"            , str     ,     2), # 0017h 目的地の方角の単位
#    (   24, "GPSDestBearing"               , Fraction,     1), # 0018h 目的の方角（数値）
#    (   25, "GPSDestDistanceRef"           , str     ,     2), # 0019h 目的地までの距離の単位
#    (   26, "GPSDestDistance"              , Fraction,     1), # 001Ah 目的地までの距離（数値）
#    (   27, "GPSProcessingMethod"          , None    ,  None), # 001Bh 測位方式の名称
#    (   28, "GPSAreaInformation"           , None    ,  None), # 001Ch 測位地点の名称
#    (   29, "GPSDateStamp"                 , str     ,    11), # 001Dh GPS 日付
#    (   30, "GPSDifferential"              , int     ,     1), # 001Eh GPS 補正測位
#    (   31, "GPSHPositioningError"         , Fraction,     1), # 001Fh 水平方向測位誤差
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
