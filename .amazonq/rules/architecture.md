# アーキテクチャルール

## ノード設計
- 各ノードは単一責任の原則に従う
- LazyFlowData を活用してメモリ効率を最適化
- LazyFlowData を出力するノードは LazyNNOperationNode を継承
- 計算コストが重いノードは N1BlockOperationNode NNBlockOperationNode を継承
- 設定可能なノードは ConfigurableNode を継承

## データフロー
- FlowDataでブロック単位の遅延処理
- ヘッダー情報で画像メタデータを管理
- primary/auxiliary分類でデータ種別を区別

## UI設計
- 設定ダイアログは統一されたレイアウト
- パラメータには適切な範囲制限
- 日本語UIで直感的な操作性
