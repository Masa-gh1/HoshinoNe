'''
NodeFactory class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from .basic.CategoryAuxiliaryNode import CategoryAuxiliaryNode
from .basic.PassNode import PassNode

from .basic.OffsetNode import OffsetNode
from .basic.ScaleNode import ScaleNode
from .basic.PowerNode import PowerNode
from .basic.NegateNode import NegateNode
from .basic.InverseNode import InverseNode
from .basic.AbsoluteNode import AbsoluteNode
from .basic.MaxNode import MaxNode
from .basic.MinNode import MinNode
from .basic.SumNode import SumNode
from .basic.ProductNode import ProductNode
from .basic.CountNode import CountNode
from .basic.MaximumNode import MaximumNode
from .basic.MinimumNode import MinimumNode
from .basic.QuadraticFitNode import QuadraticFitNode

from .preset.AutoLevelsNode import AutoLevelsNode
from .preset.TensorNode import TensorNode
from .preset.CoefficientsNode import CoefficientsNode
from .preset.AbsoluteLowPassFilterNode import AbsoluteLowPassFilterNode
from .preset.ImageAlignmentNode import ImageAlignmentNode # 廃止 ShiftDetectionNode, TransformNode に分割
from .preset.ShiftDetectionNode import ShiftDetectionNode
from .preset.TransformNode import TransformNode
from .preset.ToneCurveNode import ToneCurveNode
from .preset.BayerUnpackSparseNode import BayerUnpackSparseNode
from .preset.BayerUnpackDenseNode import BayerUnpackDenseNode

from .extra.FileReaderNode import FileReaderNode
from .extra.FileWriterNode import FileWriterNode
from .extra.FitsReaderNode import FitsReaderNode
from .extra.ImageReaderNode import ImageReaderNode
from .extra.ImageWriterNode import ImageWriterNode
from .extra.RawReaderNode import RawReaderNode
from .extra.ChromaDenoiseNode import ChromaDenoiseNode
from .extra.WaveletDenoiseNode import WaveletDenoiseNode

class NodeFactory:
    nodeClasses = {
        'offset'                 : OffsetNode,
        'scale'                  : ScaleNode,
        'power'                  : PowerNode,
        'negate'                 : NegateNode,
        'inverse'                : InverseNode,
        'absolute'               : AbsoluteNode,
        'max'                    : MaxNode,
        'min'                    : MinNode,
        'sum'                    : SumNode,
        'product'                : ProductNode,
        'count'                  : CountNode,
        'maximum'                : MaximumNode,
        'minimum'                : MinimumNode,
        #####
        'tensor'                 : TensorNode,
        'coefficients'           : CoefficientsNode,
        'quadratic_fit'          : QuadraticFitNode,
        #####
        'absolute_lowpass_filter': AbsoluteLowPassFilterNode,
        'auto_levels'            : AutoLevelsNode,
        'tone_curve'             : ToneCurveNode,
        'bayer_unpack_sparse'    : BayerUnpackSparseNode,
        'bayer_unpack_dense'     : BayerUnpackDenseNode,
        #####
        'image_alignment'        : ImageAlignmentNode, # 廃止 ShiftDetectionNode, TransformNode に分割
        'shift_detection'        : ShiftDetectionNode,
        'transform'              : TransformNode,
        #####
        'chroma_denoise'         : ChromaDenoiseNode,
        'wavelet_denoise'        : WaveletDenoiseNode,
        #####
        'category_auxiliary'     : CategoryAuxiliaryNode,
        'pass'                   : PassNode,
        #####
        'file_reader'            : FileReaderNode,
        'file_writer'            : FileWriterNode,
        'image_reader'           : ImageReaderNode,
        'image_writer'           : ImageWriterNode,
        'raw_reader'             : RawReaderNode,
        'fits_reader'            : FitsReaderNode,
    }
    
    nodeLabels = [
        ('offset'                 , '加算(N:N)'),
        ('scale'                  , '乗算(N:N)'),
        ('power'                  , '冪算(N:N)'),
        ('negate'                 , '符号反転(N:N)'),
        ('inverse'                , '逆数(N:N)'),
        ('absolute'               , '絶対値(N:N)'),
        ('max'                    , '比較大(N:N)'),
        ('min'                    , '比較小(N:N)'),
        ('separator'              , None),
        ('sum'                    , '総和(N:1)'),
        ('product'                , '総積(N:1)'),
        ('count'                  , 'カウント(N:1)'),
        ('maximum'                , '最大(N:1)'),
        ('minimum'                , '最小(N:1)'),
        ('separator'              , None),
        ('tensor'                 , '数列'),
        ('coefficients'           , '係数'),
        ('quadratic_fit'          , '2次関数近似'),
        ('separator'              , None),
        ('absolute_lowpass_filter', '絶対値(低通)(N:N)'),
        ('auto_levels'            , '自動レベル(N:N)'),
        ('tone_curve'             , 'トーンカーブ(N:N)'),
        ('bayer_unpack_sparse'    , 'ベイヤー分離(疎)(N:N)'),
        ('bayer_unpack_dense'     , 'ベイヤー分離(密)(N:N)'),
        ('separator'              , None),
        ('shift_detection'        , 'ズレ検出(N:1)'),
        ('transform'              , '変形(N:N)'),
        ('separator'              , None),
        ('chroma_denoise'         , '色空間分離ノイズ除去(色ノイズ除去)(N:N)'),
        ('wavelet_denoise'        , 'ウェーブレットノイズ除去(輝度ノイズ除去)(N:N)'),
        ('separator'              , None),
        ('category_auxiliary'     , '補正値として使う'),
        ('pass'                   , '通点(何もしない)'),
        ('separator'              , None),
        ('file_reader'            , 'ファイル読み込み(0:N)'),
        ('file_writer'            , 'ファイル書き出し(N:0)'),
        ('image_reader'           , '画像読み込み(0:N)'),
        ('image_writer'           , '画像書き出し(N:0)'),
        ('raw_reader'             , 'RAW読み込み(0:N)'),
        ('fits_reader'            , 'FITS読み込み(0:N)'),
    ]
    
    @classmethod
    def createNode(cls, nodeType, canvas, editor, x, y, **kwargs):
        nodeClass = cls.nodeClasses.get(nodeType)
        if nodeClass:
            return nodeClass(canvas, editor, x, y, **kwargs)
        return None
    
    @classmethod
    def getMenuItems(cls):
        return cls.nodeLabels