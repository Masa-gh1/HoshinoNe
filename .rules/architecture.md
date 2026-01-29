# アーキテクチャルール

## ノード設計
- 簡素化の為に各ノードは入力に対し交換法則が成り立つこと
- 各ノードは単一責任の原則に従う
- LazyFlowData を活用してメモリ効率を最適化
- LazyFlowData を出力するノードは LazyNNOperationNode を継承
- 計算コストが重いノードは N1BlockOperationNode NNBlockOperationNode を継承
- 設定可能なノードは ConfigurableNode を継承

## データフロー
- FlowDataでブロック単位に遅延評価
- 計算コストの大きなFlowDataはブロック単位での永続キャッシュ
- ヘッダー情報で画像メタデータを管理
- primary/auxiliary分類でデータ種別を区別

## UI設計
- 設定ダイアログは統一されたレイアウト
- パラメータには適切な範囲制限
- パラメータには単位を記載
- パラメータにはユーザーが数値の意味を理解できる説明
- 日本語UIで直感的な操作性
