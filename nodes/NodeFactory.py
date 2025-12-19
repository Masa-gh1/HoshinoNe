'''
NodeFactory class

@author: Masakazu Inoue
'''

from .FileReaderNode import FileReaderNode
from .FileWriterNode import FileWriterNode
from .AdditionNode import AdditionNode
from .NegateNode import NegateNode
from .MultiplicationNode import MultiplicationNode
from .InverseNode import InverseNode
from .ImageReaderNode import ImageReaderNode
from .ImageWriterNode import ImageWriterNode
from .QuadraticFitNode import QuadraticFitNode
from .CoefficientsNode import CoefficientsNode
from .RawReaderNode import RawReaderNode
from .FitsReaderNode import FitsReaderNode
from .CountNode import CountNode

class NodeFactory:
    nodeClasses = {
        'addition': AdditionNode,
        'multiplication': MultiplicationNode,
        'inverse': InverseNode,
        'negate': NegateNode,
        'count': CountNode,
        'coefficients': CoefficientsNode,
        'quadratic_fit': QuadraticFitNode,
        'file_reader': FileReaderNode,
        'image_reader': ImageReaderNode,
        'raw_reader': RawReaderNode,
        'fits_reader': FitsReaderNode,
        'file_writer': FileWriterNode,
        'image_writer': ImageWriterNode,
    }
    
    nodeLabels = [
        ('addition'      , '加算'),
        ('multiplication', '乗算'),
        ('negate'        , '符号反転'),
        ('inverse'       , '逆数'),
        ('count'         , 'カウント'),
        ('separator'     , None),
        ('coefficients'  , '係数'),
        ('quadratic_fit' , '2次関数近似'),
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