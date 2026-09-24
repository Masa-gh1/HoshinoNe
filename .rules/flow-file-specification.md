# フローファイル仕様書 (.flow)

本ドキュメントでは、ほしのねにおけるフローファイルのデータ構造を定義します。
外部システムで本ファイルを読み書きする際のインターフェースとして参照してください。

## 1. 基本構造
フローファイルは JSON 形式で記述されます。

```json
{
  "version": "99.99.99999999",
  "nodes": [
    {
      "index": 0,
      "zOrder": 10,
      "type": "coefficients",
      "text": "係数",
      "x": 100,
      "y": 150,
      "category": "auxiliary",
      ...,
      ...,
      ...,
      "connections": [1, 2]
    }
  ],
  "trays": [
    {
      "zOrder": 5,
      "x": 50,
      "y": 50,
      "width": 200,
      "height": 150,
      "title": "調整係数"
    }
  ]
}
```

## 2. データ定義

### 2.1 共通フィールド
| フィールド名 | 型 | 説明 |
| :--- | :--- | :--- |
| `version` | String | ファイルのバージョン情報 |
| `nodes` | Array | ノードオブジェクトのリスト |
| `trays` | Array | トレイオブジェクトのリスト |

### 2.2 ノードオブジェクト (`nodes`)
| フィールド名 | 型 | 説明 |
| :--- | :--- | :--- |
| `index` | Integer | ノードの識別インデックス（配列内の位置） |
| `zOrder` | Integer | 描画の重なり順序 |
| `type` | String | ノードの種類（識別子） |
| `text` | String | ノードの名称 |
| `x` | Integer | キャンバス上のX座標 |
| `y` | Integer | キャンバス上のY座標 |
| `category` | String | 出力カテゴリ（`primary`, `auxiliary`, `etc`）、primary の場合省略 |
| `connections` | Array[Integer] | 接続先のノードの `index` リスト |
| `...` | Object | ノード固有のパラメータや設定データ |

### 2.3 トレイオブジェクト (`trays`)
| フィールド名 | 型 | 説明 |
| :--- | :--- | :--- |
| `zOrder` | Integer | 描画の重なり順序 |
| `x` | Integer | キャンバス上のX座標 |
| `y` | Integer | キャンバス上のY座標 |
| `width` | Integer | トレイの幅 |
| `height` | Integer | トレイの高さ |
| `title` | String | トレイのタイトル |

## 3. 制約事項
- **文字コード**: UTF-8。
- **数値型**: JSON標準に従う。NumPy等の浮動小数点数は標準の数値型として扱う。
- **接続関係**: `connections` 配列に含まれる数値は、同一ファイル内の `nodes` 配列における `index` を参照する。
