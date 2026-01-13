'''
NodeFactory class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

class NodeFactory:
    nodeLabels = [
        # minor type                 label
        ('offset'                  , '加算(N:N)'),
        ('scale'                   , '乗算(N:N)'),
        ('power'                   , '冪算(N:N)'),
        ('negate'                  , '符号反転(N:N)'),
        ('inverse'                 , '逆数(N:N)'),
        ('absolute'                , '絶対値(N:N)'),
        ('max'                     , '比較大(N:N)'),
        ('min'                     , '比較小(N:N)'),
        ('upper_pass'              , '上値通(N:N)'),
        ('lower_pass'              , '下値通(N:N)'),
        ('------------------------', None),
        ('sum'                     , '総和(N:1)'),
        ('product'                 , '総積(N:1)'),
        ('count'                   , 'カウント(N:1)'),
        ('maximum'                 , '最大(N:1)'),
        ('minimum'                 , '最小(N:1)'),
        ('------------------------', None),
        ('tensor'                  , '数列(0:1)'),
        ('coefficients'            , '係数(0:1)'),
        ('------------------------', None),
        ('quadratic_fit'           , '2次関数近似(N:N)'),
       #('absolute_lowpass_filter' , '絶対値(低通)(N:N)'),# 廃止 upper_pass, lower_pass に分割
        ('auto_levels'             , '自動レベル(N:N)'),
        ('tone_curve'              , 'トーンカーブ(N:N)'),
        ('------------------------', None),
        ('bayer_unpack_sparse'     , 'ベイヤー分離(疎)(N:N)'),
        ('bayer_unpack_dense'      , 'ベイヤー分離(密)(N:N)'),
        ('lab_converter'           , 'Lab変換(正規化なし)(N:N)'),
        ('rgb_converter'           , 'RGB変換(正規化なし)(N:N)'),
        ('------------------------', None),
       #('image_alignment'         , '画像位置合わせ(N:N)'),# 廃止 ShiftDetectionNode, TransformNode に分割
        ('shift_detection'         , 'ズレ検出(N:1)'),
        ('transform'               , '変形(N:N)'),
        ('------------------------', None),
        ('colorspace_mask'         , '色空間マスク(N:N)'),
        ('chroma_denoise'          , '色空間分離ノイズ除去(色ノイズ除去)(N:N)'),
        ('wavelet_denoise'         , 'ウェーブレットノイズ除去(輝度ノイズ除去)(N:N)'),
        ('------------------------', None),
        ('category_auxiliary'      , '補正値に変換'),
        ('pass'                    , '通過点(何もしない)'),
        ('------------------------', None),
        ('file_reader'             , 'ファイル読み込み(0:N)'),
        ('file_writer'             , 'ファイル書き出し(N:0)'),
        ('image_reader'            , '画像読み込み(0:N)'),
        ('image_writer'            , '画像書き出し(N:0)'),
        ('raw_reader'              , 'RAW読み込み(0:N)'),
        ('fits_reader'             , 'FITS読み込み(0:N)'),
    ]
    
    nodeList = None
    
    @classmethod
    def createNode(cls, nodeType, canvas, editor, x, y, **kwargs):
        nodeClass = cls.loadNodeClass(nodeType)
        return nodeClass(canvas, editor, x, y, **kwargs)
    
    @classmethod
    def getMenuItems(cls):
        return cls.nodeLabels
    
    @classmethod
    def loadNodeClass(cls, nodeType):
        if not cls.nodeList:
            cls.nodeList = cls.getNodeList()
        
        import importlib
        modName, className = cls.nodeList[nodeType]
        mod = importlib.import_module(modName)
        return getattr(mod, className) 

    @classmethod
    def getNodeList(cls):
        import ast
        import pkgutil
        import nodes.basic
        import nodes.preset
        import nodes.extra
        from utils.Debug import Debug
        
        nodeList = {}
        for pkg in [nodes.basic, nodes.preset, nodes.extra]:
            for modInfo in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
                if modInfo.ispkg:
                    pass
                else:
                    spec = modInfo.module_finder.find_spec(modInfo.name)
                    if spec is None:
                        pass
                    elif spec.origin is None:
                        pass
                    elif spec.origin.endswith('.py'):
                        with open(spec.origin, "r", encoding="utf-8") as file:
                            tree = ast.parse(file.read())
                            for item in tree.body:
                                if isinstance(item, ast.ClassDef):
                                    classInfo = item
                                    minorType = cls.getMinorType(item.body)
                                    if minorType:
                                        nodeList[minorType] = (modInfo.name, classInfo.name)
                                        Debug.log(cls.__name__, f"{modInfo.name} {classInfo.name}")
        return nodeList

    @classmethod
    def getMinorType(cls, body):
        import ast
        for item in body:
            if isinstance(item, ast.Assign): # 通常の代入 (minorType = "...")
                for target in item.targets:
                    if(   isinstance(target, ast.Name)
                      and 'minorType' == target.id
                      and item.value
                      and isinstance(item.value, ast.Constant)
                      ):
                        minorType = str(item.value.value)
                        return minorType
            
            elif isinstance(item, ast.AnnAssign): # 型ヒント付きの代入 (minorType: str = "...")
                if(   isinstance(item.target, ast.Name)
                  and 'minorType' == item.target.id
                  and item.value
                  and isinstance(item.value, ast.Constant)
                  ):
                    minorType =  str(item.value.value)
                    return minorType
