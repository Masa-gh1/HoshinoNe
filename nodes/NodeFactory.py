'''
NodeFactory class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from .FileReaderNode import FileReaderNode
from .FileWriterNode import FileWriterNode
from .SumNode import SumNode
from .NegateNode import NegateNode
from .ProductNode import ProductNode
from .OffsetNode import OffsetNode
from .ScaleNode import ScaleNode
from .InverseNode import InverseNode
from .ImageReaderNode import ImageReaderNode
from .ImageWriterNode import ImageWriterNode
from .QuadraticFitNode import QuadraticFitNode
from .CoefficientsNode import CoefficientsNode
from .RawReaderNode import RawReaderNode
from .FitsReaderNode import FitsReaderNode
from .CountNode import CountNode
from .ToneCurveNode import ToneCurveNode
from .WaveletDenoiseNode import WaveletDenoiseNode
from .ChromaDenoiseNode import ChromaDenoiseNode
from .ImageAlignmentNode import ImageAlignmentNode

from .LazyOffsetNode import LazyOffsetNode

class NodeFactory:
    nodeClasses = {
        'offset': LazyOffsetNode,
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
        ('offset'        , 'オフセット(N:N)'),
        ('scale'         , 'スケール(N:N)'),
        ('negate'        , '符号反転(N:N)'),
        ('inverse'       , '逆数(N:N)'),
        ('sum'           , '総和(N:1)'),
        ('product'       , '総積(N:1)'),
        ('count'         , 'カウント(N:1)'),
        ('separator'     , None),
        ('coefficients'  , '係数'),
        ('quadratic_fit' , '2次関数近似'),
        ('separator'     , None),
        ('tone_curve'    , 'トーンカーブ'),
        ('separator'     , None),
        ('chroma_denoise' , '色空間分離ノイズ除去(色ノイズ除去)'),
        ('wavelet_denoise', 'ウェーブレットノイズ除去(輝度ノイズ除去)'),
        ('image_alignment', '画像位置合わせ'),
        ('separator'     , None),
        ('file_reader'   , 'ファイル読み込み'),
        ('file_writer'   , 'ファイル書き出し'),
        ('image_reader'  , '画像読み込み'),
        ('image_writer'  , '画像書き出し'),
        ('raw_reader'    , 'RAW読み込み'),
        ('fits_reader'   , 'FITS読み込み'),
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