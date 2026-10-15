'''
LazyHeaders - 遅延評価 header

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Any

from abc import ABC as AbstractBaseClass, abstractmethod

from collections import UserDict

class LazyHeadersMixin(AbstractBaseClass):
    """遅延評価FlowData"""
    
    @abstractmethod
    def getLazyHeaderkeys(self) -> Iterable[str]:
        """
        遅延評価対象の header キーを取得
        
        Returns:
            遅延評価対象の header キーのリスト
        """
        ...
    
    @abstractmethod
    def headerOperation(self, key:str, *args:Any, **kwargs:Any) -> dict[str,Any]:
        """
        header 遅延評価
        
        Args:
            key: header キー
            *args: 追加の引数
            **kwargs: 追加のキーワード引数
            
        Returns:
            遅延評価結果の header 辞書 (少なくとも key を含む)
        """
        ...

class LazyHeaders(UserDict[str,Any]):
    """遅延評価対応の headers 辞書"""
    __slots__ = ('body'  ,
                 'source',
                 'args'  ,
                 'kwargs',
                )
    def __init__(self, body:LazyHeadersMixin, header:dict[str,Any], *args:Any, **kwargs:Any):
        super().__init__()
        
        self.body   = body
        self.source = header
        self.args   = args
        self.kwargs = kwargs

        for key in self.source.keys():
            self.data[key]= "<sourceHeaders>"
    
        for key in self.body.getLazyHeaderkeys():
            self.data[key]= "<LazyHeaderOperation>"
    
    def __getitem__(self, key:str) -> Any:
        if not key in self.data:
            return None
        else:
            value = self.data[key]
            if isinstance(value, str) and "<LazyHeaderOperation>" == value:
                lazyResult = self.body.headerOperation(key, *self.args, **self.kwargs)
                self.data.update(lazyResult)
                value = self.data[key]
            elif isinstance(value, str) and "<sourceHeaders>" == value:
                value = self.source[key]
            return value
    
    def copy(self) -> LazyHeaders:
        obj = LazyHeaders(self.body, self.source, *self.args, **self.kwargs)
        obj.data.update(self.data)
        return obj
