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
        OffsetNode               .minorType: OffsetNode               ,
        ScaleNode                .minorType: ScaleNode                ,
        PowerNode                .minorType: PowerNode                ,
        NegateNode               .minorType: NegateNode               ,
        InverseNode              .minorType: InverseNode              ,
        AbsoluteNode             .minorType: AbsoluteNode             ,
        MaxNode                  .minorType: MaxNode                  ,
        MinNode                  .minorType: MinNode                  ,
        ###############################################################
        SumNode                  .minorType: SumNode                  ,
        ProductNode              .minorType: ProductNode              ,
        CountNode                .minorType: CountNode                ,
        MaximumNode              .minorType: MaximumNode              ,
        MinimumNode              .minorType: MinimumNode              ,
        ###############################################################
        TensorNode               .minorType: TensorNode               ,
        CoefficientsNode         .minorType: CoefficientsNode         ,
        QuadraticFitNode         .minorType: QuadraticFitNode         ,
        ###############################################################
        AbsoluteLowPassFilterNode.minorType: AbsoluteLowPassFilterNode,
        AutoLevelsNode           .minorType: AutoLevelsNode           ,
        ToneCurveNode            .minorType: ToneCurveNode            ,
        BayerUnpackSparseNode    .minorType: BayerUnpackSparseNode    ,
        BayerUnpackDenseNode     .minorType: BayerUnpackDenseNode     ,
        ###############################################################
        ImageAlignmentNode       .minorType: ImageAlignmentNode       , # 廃止 ShiftDetectionNode, TransformNode に分割
        ShiftDetectionNode       .minorType: ShiftDetectionNode       ,
        TransformNode            .minorType: TransformNode            ,
        ###############################################################
        ChromaDenoiseNode        .minorType: ChromaDenoiseNode        ,
        WaveletDenoiseNode       .minorType: WaveletDenoiseNode       ,
        ###############################################################
        CategoryAuxiliaryNode    .minorType: CategoryAuxiliaryNode    ,
        PassNode                 .minorType: PassNode                 ,
        ###############################################################
        FileReaderNode           .minorType: FileReaderNode           ,
        FileWriterNode           .minorType: FileWriterNode           ,
        ImageReaderNode          .minorType: ImageReaderNode          ,
        ImageWriterNode          .minorType: ImageWriterNode          ,
        RawReaderNode            .minorType: RawReaderNode            ,
        FitsReaderNode           .minorType: FitsReaderNode           ,
    }
    
    nodeLabels = [
        (OffsetNode               .minorType, '加算(N:N)'),
        (ScaleNode                .minorType, '乗算(N:N)'),
        (PowerNode                .minorType, '冪算(N:N)'),
        (NegateNode               .minorType, '符号反転(N:N)'),
        (InverseNode              .minorType, '逆数(N:N)'),
        (AbsoluteNode             .minorType, '絶対値(N:N)'),
        (MaxNode                  .minorType, '比較大(N:N)'),
        (MinNode                  .minorType, '比較小(N:N)'),
        ('separator'                        , None),
        (SumNode                  .minorType, '総和(N:1)'),
        (ProductNode              .minorType, '総積(N:1)'),
        (CountNode                .minorType, 'カウント(N:1)'),
        (MaximumNode              .minorType, '最大(N:1)'),
        (MinimumNode              .minorType, '最小(N:1)'),
        ('separator'                        , None),
        (TensorNode               .minorType, '数列'),
        (CoefficientsNode         .minorType, '係数'),
        (QuadraticFitNode         .minorType, '2次関数近似'),
        ('separator'                        , None),
        (AbsoluteLowPassFilterNode.minorType, '絶対値(低通)(N:N)'),
        (AutoLevelsNode           .minorType, '自動レベル(N:N)'),
        (ToneCurveNode            .minorType, 'トーンカーブ(N:N)'),
        (BayerUnpackSparseNode    .minorType, 'ベイヤー分離(疎)(N:N)'),
        (BayerUnpackDenseNode     .minorType, 'ベイヤー分離(密)(N:N)'),
        ('separator'                        , None),
        (ShiftDetectionNode       .minorType, 'ズレ検出(N:1)'),
        (TransformNode            .minorType, '変形(N:N)'),
        ('separator'                        , None),
        (ChromaDenoiseNode        .minorType, '色空間分離ノイズ除去(色ノイズ除去)(N:N)'),
        (WaveletDenoiseNode       .minorType, 'ウェーブレットノイズ除去(輝度ノイズ除去)(N:N)'),
        ('separator'                        , None),
        (CategoryAuxiliaryNode    .minorType, '補正値として使う'),
        (PassNode                 .minorType, '通点(何もしない)'),
        ('separator'                        , None),
        (FileReaderNode           .minorType, 'ファイル読み込み(0:N)'),
        (FileWriterNode           .minorType, 'ファイル書き出し(N:0)'),
        (ImageReaderNode          .minorType, '画像読み込み(0:N)'),
        (ImageWriterNode          .minorType, '画像書き出し(N:0)'),
        (RawReaderNode            .minorType, 'RAW読み込み(0:N)'),
        (FitsReaderNode           .minorType, 'FITS読み込み(0:N)'),
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