'''
NodeFactory class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

class NodeFactory:
    nodeLabels = [
        ('OffsetNode'               , '加算(N:N)'),
        ('ScaleNode'                , '乗算(N:N)'),
        ('PowerNode'                , '冪算(N:N)'),
        ('NegateNode'               , '符号反転(N:N)'),
        ('InverseNode'              , '逆数(N:N)'),
        ('AbsoluteNode'             , '絶対値(N:N)'),
        ('MaxNode'                  , '比較大(N:N)'),
        ('MinNode'                  , '比較小(N:N)'),
        ('-------------------------', None),
        ('SumNode'                  , '総和(N:1)'),
        ('ProductNode'              , '総積(N:1)'),
        ('CountNode'                , 'カウント(N:1)'),
        ('MaximumNode'              , '最大(N:1)'),
        ('MinimumNode'              , '最小(N:1)'),
        ('-------------------------', None),
        ('TensorNode'               , '数列'),
        ('CoefficientsNode'         , '係数'),
        ('QuadraticFitNode'         , '2次関数近似'),
        ('-------------------------', None),
        ('AbsoluteLowPassFilterNode', '絶対値(低通)(N:N)'),
        ('AutoLevelsNode'           , '自動レベル(N:N)'),
        ('ToneCurveNode'            , 'トーンカーブ(N:N)'),
        ('BayerUnpackSparseNode'    , 'ベイヤー分離(疎)(N:N)'),
        ('BayerUnpackDenseNode'     , 'ベイヤー分離(密)(N:N)'),
        ('LabConverterNode'         , 'Lab変換(正規化なし)(N:N)'),
        ('RGBConverterNode'         , 'RGB変換(正規化なし)(N:N)'),
        ('-------------------------', None),
        ('ShiftDetectionNode'       , 'ズレ検出(N:1)'),
        ('TransformNode'            , '変形(N:N)'),
        ('-------------------------', None),
        ('ChromaDenoiseNode'        , '色空間分離ノイズ除去(色ノイズ除去)(N:N)'),
        ('WaveletDenoiseNode'       , 'ウェーブレットノイズ除去(輝度ノイズ除去)(N:N)'),
        ('-------------------------', None),
        ('CategoryAuxiliaryNode'    , '補正値として使う'),
        ('PassNode'                 , '通点(何もしない)'),
        ('-------------------------', None),
        ('FileReaderNode'           , 'ファイル読み込み(0:N)'),
        ('FileWriterNode'           , 'ファイル書き出し(N:0)'),
        ('ImageReaderNode'          , '画像読み込み(0:N)'),
        ('ImageWriterNode'          , '画像書き出し(N:0)'),
        ('RawReaderNode'            , 'RAW読み込み(0:N)'),
        ('FitsReaderNode'           , 'FITS読み込み(0:N)'),
    ]
    
    nodeClasses = None

    @classmethod
    def createNodeByName(cls, nodeType, canvas, editor, x, y, **kwargs):
        nodeClass = cls.loadNodeClassByName(nodeType)
        return nodeClass(canvas, editor, x, y, **kwargs)
    
    @classmethod
    def createNodeByType(cls, nodeType, canvas, editor, x, y, **kwargs):
        nodeClass = cls.loadNodeClassByType(nodeType)
        return nodeClass(canvas, editor, x, y, **kwargs)
    
    @classmethod
    def getMenuItems(cls):
        return cls.nodeLabels

    @classmethod
    def loadNodeClassByName(cls, nodeName):
        import importlib
        pkgs = ["extra","preset","basic"]
        mod = None
        ex = []
        for pkg in pkgs:
            try:
                mod = importlib.import_module(__package__+"."+pkg+"."+nodeName)
                clz = getattr(mod, nodeName)
                return clz
            except ModuleNotFoundError as e:
                ex.append(e)
        raise ex[0]

    @classmethod
    def loadNodeClassByType(cls, nodeType):
        if cls.nodeClasses is None:
            cls.nodeClasses = {}
            for className, label in cls.nodeLabels:
                if '---' in className:
                    pass
                else:
                    clz = cls.loadNodeClassByName(className)
                    cls.nodeClasses[clz.minorType] = (clz.__module__, clz.__name__)
        
        import importlib
        moduleName, className = cls.nodeClasses[nodeType]
        mod = importlib.import_module(moduleName)
        return getattr(mod, className) 
