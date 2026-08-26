'''
NodeFactory class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

class NodeFactory:
    nodeLabels = [
        # minor type                 label                            tooltip
        ('offset'                  , '加算(N:N)'                    , 'a+b'                       ),
        ('scale'                   , '乗算(N:N)'                    , 'ab'                        ),
        ('power'                   , '冪算(N:N)'                    , 'a^b'                       ),
        ('------------------------', None                           , None                        ),
        ('negate'                  , '符号反転(N:N)'                , '-a'                        ),
        ('inverse'                 , '逆数(N:N)'                    , '1/a'                       ),
        ('sign'                    , '符号(N:N)'                    , 'sign(a)'                   ),
        ('absolute'                , '絶対値(N:N)'                  , '|a|'                       ),
        ('------------------------', None                           , None                        ),
        ('natural_logarithm'       , '自然対数(N:N)'                , 'log(a)'                    ),
        ('natural_exponential'     , '自然指数(N:N)'                , 'e^a'                       ),
        ('squared_norm'            , 'ノルムの二乗(N:N)'            , '|a|^2'                     ),
        ('conjugate'               , '共役(N:N)'                    , 'a*'                        ),
        ('fill_0'                  , '0 埋め(N:N)'                  , '0+0a'                      ),
        ('fill_1'                  , '1 埋め(N:N)'                  , '1+0a'                      ),
        ('------------------------', None                           , None                        ),
        ('max'                     , '比較大(N:N)'                  , 'max(a,b)'                  ),
        ('min'                     , '比較小(N:N)'                  , 'min(a,b)'                  ),
        ('************************', None                           , None                        ),
        ('sum'                     , '総和(N:1)'                    , 'ΣA'                       ),
        ('product'                 , '総積(N:1)'                    , 'ΠA'                       ),
        ('count'                   , 'カウント(N:1)'                , '|A|'                       ),
        ('maximum'                 , '最大(N:1)'                    , 'max(A)'                    ),
        ('minimum'                 , '最小(N:1)'                    , 'min(A)'                    ),
        ('------------------------', None                           , None                        ),
        ('convolution'             , '畳み込み(N:N)'                , 'A*B'                       ),
        #('deconvolution'           , '逆畳み込み(N:N)'             , None                        ), # 未公開
        ('fft'                     , 'FFT(N:N)'                     , 'DFT(A)'                    ),
        ('ifft'                    , '逆FFT(N:N)'                   , 'IDFT(A)'                   ),
        ('dwt'                     , '離散ウェーブレット変換(N:N)'  , 'DWT(A,B)'                  ),
        ('idwt'                    , '逆離散ウェーブレット変換(N:N)', 'IDWT(A,B)'                 ),
        ('------------------------', None                           , None                        ),
        ('quadratic_fit'           , '2次関数近似(N:N)'             , None                        ),
        ('auto_levels'             , '自動レベル(N:N)'              , None                        ),
        ('tone_curve'              , 'トーンカーブ(N:N)'            , None                        ),
        ('------------------------', None                           , None                        ),
        ('upper_pass'              , '上値通(N:N)'                  , 'a>b ? a : NaN'             ),
        ('lower_pass'              , '下値通(N:N)'                  , 'a<b ? a : NaN'             ),
        ('colorspace_mask'         , '色空間マスク(N:N)'            , None                        ),
        ('------------------------', None                           , None                        ),
        ('category_auxiliary'      , '補正値に変換'                 , None                        ),
        ('pass'                    , '通過点(何もしない)'           , None                        ),
        ('************************', None                           , None                        ),
        ('bayer_unpack_sparse'     , 'ベイヤー分離(疎)(N:N)'        , 'RGGB→R,G1,B,G2'           ),
        ('bayer_unpack_dense'      , 'ベイヤー分離(密)(N:N)'        , 'RGGB→R,G1,B,G2'           ),
        ('lab_converter'           , 'Lab変換(正規化なし)(N:N)'     , 'RGB→Lab'                  ),
        ('rgb_converter'           , 'RGB変換(正規化なし)(N:N)'     , 'Lab→RGB'                  ),
        ('------------------------', None                           , None                        ),
        ('shift_detection'         , 'ズレ検出(N:1)'                , None                        ),
        ('transform'               , '変形(N:N)'                    , None                        ),
        ('reposition'              , '再配置(N:N)'                  , None                        ),
        ('------------------------', None                           , None                        ),
        ('------------------------', None                           , None                        ),
        ('table'                   , '表(0:1)'                      , '[a,b,c,...]'               ),
        ('tensor'                  , '数列(0:1)'                    , '[a,a,a,...]'               ),
        ('coefficients'            , '係数(0:1)'                    , 'a+bx+cx²+...'              ),
        ('------------------------', None                           , None                        ),
        ('file_reader'             , 'ファイル読み込み(0:N)'        , None                        ),
        ('file_writer'             , 'ファイル書き出し(N:0)'        , None                        ),
        ('image_reader'            , '画像読み込み(0:N)'            , None                        ),
        ('image_writer'            , '画像書き出し(N:0)'            , None                        ),
        ('raw_reader'              , 'RAW読み込み(0:N)'             , None                        ),
        ('fits_reader'             , 'FITS読み込み(0:N)'            , None                        ),
        ('------------------------', None                           , None                        ),
        ('chroma_denoise'          , '色空間分離ノイズ除去(N:N)'    , None                        ),
        ('wavelet_denoise'         , 'ウェーブレットノイズ除去(N:N)', None                        ),
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
