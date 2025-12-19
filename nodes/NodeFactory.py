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
from .basic.SumNode import SumNode
from .basic.ProductNode import ProductNode
from .basic.CountNode import CountNode
from .basic.QuadraticFitNode import QuadraticFitNode

from .preset.AutoLevelsNode import AutoLevelsNode
from .preset.CoefficientsNode import CoefficientsNode
from .basic.AbsoluteLowPassFilterNode import AbsoluteLowPassFilterNode
from .preset.ImageAlignmentNode import ImageAlignmentNode
from .preset.ToneCurveNode import ToneCurveNode

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
        'offset': OffsetNode,
        'scale': ScaleNode,
        'power': PowerNode,
        'negate': NegateNode,
        'inverse': InverseNode,
        'absolute': AbsoluteNode,
        'sum': SumNode,
        'product': ProductNode,
        'count': CountNode,
        #####
        'coefficients': CoefficientsNode,
        'quadratic_fit': QuadraticFitNode,
        #####
        'absolute_lowpass_filter': AbsoluteLowPassFilterNode,
        'auto_levels': AutoLevelsNode,
        'tone_curve': ToneCurveNode,
        #####
        'chroma_denoise': ChromaDenoiseNode,
        'wavelet_denoise': WaveletDenoiseNode,
        'image_alignment': ImageAlignmentNode,
        #####
        'category_auxiliary': CategoryAuxiliaryNode,
        'pass': PassNode,
        #####
        'file_reader': FileReaderNode,
        'file_writer': FileWriterNode,
        'image_reader': ImageReaderNode,
        'image_writer': ImageWriterNode,
        'raw_reader': RawReaderNode,
        'fits_reader': FitsReaderNode,
    }
    
    nodeLabels = [
        ('offset'                 , '加算(N:N)'),
        ('scale'                  , '乗算(N:N)'),
        ('power'                  , '冪算(N:N)'),
        ('negate'                 , '符号反転(N:N)'),
        ('inverse'                , '逆数(N:N)'),
        ('absolute'               , '絶対値(N:N)'),
        ('sum'                    , '総和(N:1)'),
        ('product'                , '総積(N:1)'),
        ('count'                  , 'カウント(N:1)'),
        ('separator'              , None),
        ('coefficients'           , '係数'),
        ('quadratic_fit'          , '2次関数近似'),
        ('separator'              , None),
        ('absolute_lowpass_filter', '絶対値(低通)(N:N)'),
        ('auto_levels'            , '自動レベル(N:N)'),
        ('tone_curve'             , 'トーンカーブ(N:N)'),
        ('separator'              , None),
        ('chroma_denoise'         , '色空間分離ノイズ除去(色ノイズ除去)(N:N)'),
        ('wavelet_denoise'        , 'ウェーブレットノイズ除去(輝度ノイズ除去)(N:N)'),
        ('image_alignment'        , '画像位置合わせ(N:N)'),
        ('separator'              , None),
        ('category_auxiliary'     , '補正値として使う'),
        ('pass'                   , '通点'),
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