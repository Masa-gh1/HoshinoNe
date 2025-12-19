# データフォーマット仕様書

## FlowData Headers 仕様

### 基本ヘッダー（全データ共通）
- `category`: データ分類 ('primary' | 'auxiliary')
- `type`: データ種別 ('image' | 'matrix' | 'tensor')
- `mode`: データモード
- `planes`: プレーン名リスト
- `width`: データ幅
- `height`: データ高さ
- `display_levels`: 表示レベル範囲 {min, exclusive_upper}

### 画像データ (type: 'image')
#### mode値
- `RGB`, `RGBA`: カラー画像
- `L`, `LA`: グレースケール
- `RGBG`: ベイヤー分離後4プレーン
- `BAYER`: ベイヤー配列生データ
- `P`, `CMYK`, `YCbCr`, `HSV`, `LAB`: その他色空間

#### 画像固有ヘッダー
- `source_file`: 元ファイルパス
- `datetime`: 撮影日時文字列 ("YYYY-MM-DD HH:MM:SS")
- `is_bayer`: ベイヤーデータフラグ
- `bayer_pattern`: ベイヤーパターン ('RGGB' | 'GRBG' | 'GBRG' | 'BGGR')
- `exif`: EXIF情報辞書

#### RAW画像追加ヘッダー
- `demosaic`: デモザイクアルゴリズム
- `colorspace`: 出力色空間
- `white_balance`: ホワイトバランス設定
- `raw`: RAW固有情報辞書

### Matrix データ (type: 'matrix')
#### mode値
- `2D`: 2次元行列データ

#### Matrix固有ヘッダー
- `columns`: 列名リスト (['dx', 'dy', 'rotation', 'confidence', 'method_id'])
- `lines`: 行識別子リスト (ファイル名など)
- `method_definitions`: method_id マッピング辞書

### Tensor データ (type: 'tensor')
#### mode値
- `0D`, `1D`, `2D`: テンソル次元

#### Tensor固有ヘッダー
- `axes`: 軸名リスト (['x_order', 'y_order'])
- `columns`: 列ラベル (['x^0', 'x^1', ...])
- `lines`: 行ラベル (['y^0', 'y^1', ...])
- `max_orders`: 最大次数リスト
- `equations`: 方程式説明リスト

### 位置合わせ関連ヘッダー
- `method`: 使用した位置合わせ手法 ('star' | 'phase' | 'template')
- `success`: 位置合わせ成功フラグ
- `confidence`: 信頼度 (0.0-1.0)
- `movement_from_reference`: 基準画像からの移動量 {dx, dy, rotation}
- `{method}_success`: 各手法の成功フラグ
- `{method}_confidence`: 各手法の信頼度
- `{method}_movement`: 各手法の移動量
- `{method}_extra_info`: 各手法の詳細情報

## ノード別 Headers 生成規則

### 読み込みノード（BaseReaderNode継承）
#### 共通ヘッダー（全読み込みノード）
- `category`: 'primary' (デフォルト)
- `source_file`: 元ファイルパス
- `width`: データ幅
- `height`: データ高さ
- `planes`: プレーン名リスト
- `display_levels`: 表示レベル範囲 {min, exclusive_upper}

#### 画像系読み込みノード共通（RawReader, ImageReader, FitsReader）
- `type`: 'image'
- `datetime`: 撮影日時文字列 ("YYYY-MM-DD HH:MM:SS")
- `mode`: 画像モード (RGB, L, BAYER等)
- `exif`: EXIF情報辞書

#### RawReader
- RAW固有: is_bayer, bayer_pattern, demosaic, colorspace, white_balance, raw

#### ImageReader
- 標準画像ファイル（JPG, PNG等）の読み込み

#### FitsReader
- FITS固有: context_index (HDU番号), fits (FITSヘッダー辞書)
- ベイヤー対応: is_bayer, bayer_pattern (FITSヘッダーから自動判別)
- 疑似EXIF: FITS情報をEXIF形式に変換して格納

#### FileReader
- `type`: 'matrix'
- `mode`: '2D'
- `columns`: 列名リスト
- `lines`: 行名リスト
- CSV固有: プレーン名はファイル内の#マーカーから取得

### 処理ノード
#### ImageAlignment, ShiftDetection
- 入力headersを継承
- 位置合わせ情報を追加 (method, success, confidence, movement_from_reference等)

#### BayerUnpackSparse
- 入力headersを継承
- mode='RGB', planes=['R', 'G', 'B']に変更

#### BayerUnpackDense
- 入力headersを継承
- mode='RGBG', planes=['R', 'G1', 'B', 'G2']に変更
- width, heightを半分に変更

### 生成ノード
#### CoefficientsNode
- category='auxiliary', type='tensor'
- mode, axes, columns, lines, max_orders, equations設定

### 分類ノード
#### CategoryAuxiliary
- category='auxiliary'に変更
- その他は入力を継承

## Headers 継承ルール
1. 入力 headers をベースとして継承
2. ノード固有の情報を追加/更新
3. 競合する場合は新しい値で上書き
4. 削除は原則禁止（トレーサビリティ確保）
5. LazyFlowData では addHeaderOperation で動的計算可能