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

class NodeFactory:
    nodeClasses = {
        'file_reader': FileReaderNode,
        'image_reader': ImageReaderNode,
        'addition': AdditionNode,
        'multiplication': MultiplicationNode,
        'inverse': InverseNode,
        'negate': NegateNode,
        'file_writer': FileWriterNode,
        'image_writer': ImageWriterNode,
        'quadratic_fit': QuadraticFitNode,
        'coefficients': CoefficientsNode,
    }
    
    nodeLabels = {
        'file_reader': 'ファイル読み込み',
        'image_reader': '画像読み込み',
        'addition': '加算',
        'negate': '符号反転',
        'multiplication': '乗算',
        'inverse': '逆数',
        'coefficients': '係数',
        'file_writer': 'ファイル書き出し',
        'image_writer': '画像書き出し',
        'quadratic_fit': '2次関数近似',
    }
    
    @classmethod
    def createNode(cls, nodeType, canvas, editor, x, y, **kwargs):
        nodeClass = cls.nodeClasses.get(nodeType)
        if nodeClass:
            return nodeClass(canvas, editor, x, y, **kwargs)
        return None
    
    @classmethod
    def getMenuItems(cls):
        return [(label, nodeType) for nodeType, label in cls.nodeLabels.items()]