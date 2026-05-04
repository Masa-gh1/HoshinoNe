'''
SumNode - 総和ノード（N:1）

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from base.FlowNode_CONST import *
from nodes import N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin

class SumNode(N1BlockOperationNode, PolynomialOperationMixin, TensorOperationMixin):
    # ノードタイプ
    majorType = _MAJOR_TYPE_AGG
    minorType = 'sum'
    # ノード名
    name      = '総和'
    # 入出力タイプ
    #ioType    = スーパークラスを継承
    #outputCat = スーパークラスを継承

    def preprocessInputs(self, inputDatas):
        """入力データの前処理：Polynomialを事前統合"""
        import numpy as np
        from utils import numpy_helpers as nh
        
        prmDatas       = []
        prmTensors     = []
        prmPolynomials = []
        auxDatas       = []
        auxTensors     = []
        auxPolynomials = []
        variableType = nh.BDTYPE
        
        for data in inputDatas:
            category = data.headers.get('category', 'primary')
            dataType = data.headers.get('type', 'table')
            if category == 'auxiliary':
                if   dataType == 'tensor':
                    auxTensors.append(data)
                elif dataType == 'polynomial':
                    auxPolynomials.append(data)
                else:
                    auxDatas.append(data)
            else:
                if   dataType == 'tensor':
                    prmTensors.append(data)
                elif dataType == 'polynomial':
                    prmPolynomials.append(data)
                else:
                    prmDatas.append(data)
            variableType = np.result_type(variableType, data.getVariableType())
        
        # tensor を事前統合(加算)
        self._combinedTensor = self.computeCombinedTensor(prmTensors + auxTensors, np.add)
        
        # polynomial を事前統合(加算)
        self._combinedPolynomial = self.computeCombinedPolynomial(prmPolynomials + auxPolynomials, np.add)
        
        self._variableType = variableType
        
        if prmDatas or auxDatas:
            return prmDatas + auxDatas
        elif self._combinedTensor:
            prmDatas = [self._combinedTensor]
            self._combinedTensor = None
            return prmDatas
        elif self._combinedPolynomial:
            prmDatas = [self._combinedPolynomial]
            self._combinedPolynomial = None
            return prmDatas
        else:
            return None

    def getOutputDimensions(self, baseData, inputDatas):
        """加算では全入力データを包含するサイズを使用"""
        self._outputDimensions = self.getUnionDimensions(inputDatas)
        return self._outputDimensions
    
    def processBlock(self, inputDatas, planeIndex, x, y):
        """単一ブロックの加算処理"""
        import numpy as np
        from utils import numpy_helpers as nh
        from config import BLOCK_SIZE
        from base import DataBlock
        
        resultWidth, resultHeight = self._outputDimensions
        
        blockHeight = min(BLOCK_SIZE, resultHeight - y)
        blockWidth  = min(BLOCK_SIZE, resultWidth  - x)
        result = None
        
        # スレッドローカルに作業用メモリを確保
        _invalidA = self.getLocal('_invalidA')
        _invalidB = self.getLocal('_invalidB')
        _invalidC = self.getLocal('_invalidC')
        
        if _invalidA is None:
            _invalidA = np.empty((BLOCK_SIZE, BLOCK_SIZE), dtype=bool)
            self.setLocal('_invalidA', _invalidA)
        if _invalidB is None:
            _invalidB = np.empty((BLOCK_SIZE, BLOCK_SIZE), dtype=bool)
            self.setLocal('_invalidB', _invalidB)
        if _invalidC is None:
            _invalidC = np.empty((BLOCK_SIZE, BLOCK_SIZE), dtype=bool)
            self.setLocal('_invalidC', _invalidC)
        
        # tableデータの加算（NaN対応）
        for inputData in inputDatas:
            inputBlock = inputData.getBlock(planeIndex, x, y)
            if inputBlock:
                minH = min(blockHeight, inputBlock.data.shape[0])
                minW = min(blockWidth , inputBlock.data.shape[1])
                
                if result is None:
                    # 最初のブロックで初期化
                    result = nh.nans((blockHeight, blockWidth), dtype=self._variableType)
                    result[:minH, :minW] = inputBlock.data[:minH, :minW]
                else:
                    # スレッドローカルに作業用メモリを確保
                    invalidA = _invalidA[:minH, :minW]
                    invalidB = _invalidB[:minH, :minW]
                    invalidC = _invalidC[:minH, :minW]
                    
                    # 計算範囲の結果を取得
                    res =  result[:minH, :minW]
                    
                    # NaN 対応加算
                    np.isnan(res                          , out=invalidA)
                    np.isnan(inputBlock.data[:minH, :minW], out=invalidB)
                    np.logical_not(invalidB               , out=invalidB)
                    np.logical_and(invalidA, invalidB     , out=invalidC)
                    if invalidC.any():
                        res[invalidC] = inputBlock.data[invalidC]
                    np.logical_not(invalidA               , out=invalidA)
                    np.logical_and(invalidA, invalidB     , out=invalidC)
                    if invalidC.any():
                        res[invalidC] += inputBlock.data[invalidC]
        
        # tableデータがない場合の初期化
        if result is None:
            result = nh.nans((blockHeight, blockWidth))
        
        # tensor を加算（NaN対応）
        if self._combinedTensor:
            block = self.calculateTensorBlock(self._combinedTensor, planeIndex, x, y, result.shape, defaultValue=0.0)
            if not block is None:
                result += block
        
        # polynomial を加算（NaN対応）
        if self._combinedPolynomial:
            block = self.calculatePolynomialBlock(self._combinedPolynomial, planeIndex, x, y, result.shape, defaultValue=0.0)
            if not block is None:
                result += block
        
        return DataBlock(result, planeIndex, x, y)
    
    import threading
    local = threading.local()

    @staticmethod
    def setLocal(name, value):
        if not hasattr(SumNode.local, "SumNode"):
            SumNode.local.SumNode = {}
        SumNode.local.SumNode[name] = value
    
    @staticmethod
    def getLocal(name):
        if not hasattr(SumNode.local, "SumNode"):
            return None
        else:
            return SumNode.local.SumNode.get(name)
