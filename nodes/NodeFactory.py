'''
NodeFactory class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from .basic.CategoryAuxiliaryNode import CategoryAuxiliaryNode
from .basic.OffsetNode import OffsetNode
from .basic.ScaleNode import ScaleNode
from .basic.NegateNode import NegateNode
from .basic.InverseNode import InverseNode
from .basic.SumNode import SumNode
from .basic.ProductNode import ProductNode
from .basic.CountNode import CountNode
from .basic.QuadraticFitNode import QuadraticFitNode

from .preset.AutoLevelsNode import AutoLevelsNode
from .preset.CoefficientsNode import CoefficientsNode
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
        'inverse': InverseNode,
        'negate': NegateNode,
        'sum': SumNode,
        'product': ProductNode,
        'count': CountNode,
        #####
        'coefficients': CoefficientsNode,
        'quadratic_fit': QuadraticFitNode,
        #####
        'category_auxiliary': CategoryAuxiliaryNode,
        #####
        'auto_levels': AutoLevelsNode,
        'tone_curve': ToneCurveNode,
        #####
        'chroma_denoise': ChromaDenoiseNode,
        'wavelet_denoise': WaveletDenoiseNode,
        'image_alignment': ImageAlignmentNode,
        #####
        'file_reader': FileReaderNode,
        'file_writer': FileWriterNode,
        'image_reader': ImageReaderNode,
        'image_writer': ImageWriterNode,
        'raw_reader': RawReaderNode,
        'fits_reader': FitsReaderNode,
    }
    
    nodeLabels = [
        ('offset'            , '加算(N:N)'),
        ('scale'             , '乗算(N:N)'),
        ('negate'            , '符号反転(N:N)'),
        ('inverse'           , '逆数(N:N)'),
        ('sum'               , '総和(N:1)'),
        ('product'           , '総積(N:1)'),
        ('count'             , 'カウント(N:1)'),
        ('separator'         , None),
        ('coefficients'      , '係数'),
        ('quadratic_fit'     , '2次関数近似'),
        ('separator'         , None),
        ('category_auxiliary', '補正に変更'),
        ('separator'         , None),
        ('auto_levels'       , '自動レベル'),
        ('tone_curve'        , 'トーンカーブ'),
        ('separator'         , None),
        ('chroma_denoise'    , '色空間分離ノイズ除去(色ノイズ除去)'),
        ('wavelet_denoise'   , 'ウェーブレットノイズ除去(輝度ノイズ除去)'),
        ('image_alignment'   , '画像位置合わせ'),
        ('separator'         , None),
        ('file_reader'       , 'ファイル読み込み'),
        ('file_writer'       , 'ファイル書き出し'),
        ('image_reader'      , '画像読み込み'),
        ('image_writer'      , '画像書き出し'),
        ('raw_reader'        , 'RAW読み込み'),
        ('fits_reader'       , 'FITS読み込み'),
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