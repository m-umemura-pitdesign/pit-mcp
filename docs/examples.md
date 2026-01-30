# 質問 → SQL → 回答 の例

このドキュメントでは、MCPサーバーを通じた質問処理の具体例を示します。

---

## 例1: 再課金猶予時間の確認

### ユーザーの質問
```
「東京中央パーキングの再課金猶予時間は何分？」
```

### 処理フロー

#### Step 1: 駐車場を特定
```
Tool: search_parking
Arguments: { "query": "東京中央パーキング", "search_type": "name" }
```

**実行されるSQL:**
```sql
SELECT id, name, code, address, status
FROM parkings
WHERE name LIKE '%東京中央パーキング%'
LIMIT 10
```

**結果:**
```json
[
  {
    "id": 123,
    "name": "東京中央パーキング",
    "code": "TKY001",
    "address": "東京都中央区...",
    "status": "active"
  }
]
```

#### Step 2: 設定を取得
```
Tool: get_parking_config
Arguments: { "parking_id": 123 }
```

**実行されるSQL:**
```sql
SELECT
    pc.*,
    p.name as parking_name,
    p.code as parking_code,
    COALESCE(pc.re_charge_grace_time, pc.default_re_charge_time) as effective_re_charge_time,
    CASE
        WHEN pc.re_charge_grace_time IS NULL THEN 'デフォルト'
        ELSE '個別設定'
    END as re_charge_time_type
FROM parking_configs pc
JOIN parkings p ON pc.parking_id = p.id
WHERE pc.parking_id = 123
LIMIT 1
```

**結果:**
```json
{
  "parking_id": 123,
  "parking_name": "東京中央パーキング",
  "re_charge_grace_time": null,
  "default_re_charge_time": 30,
  "effective_re_charge_time": 30,
  "re_charge_time_type": "デフォルト",
  "night_rate_enabled": true,
  ...
}
```

### 回答
```
東京中央パーキングの再課金猶予時間は30分です。

この物件では個別設定はなく、デフォルト値（30分）が適用されています。

※ 再課金猶予時間とは、出庫後にこの時間内に再入庫した場合、
   新たな課金が発生しない猶予期間のことです。
```

---

## 例2: デフォルトか例外かの確認

### ユーザーの質問
```
「新宿西口パーキングの再課金猶予はデフォルト？それとも例外？」
```

### 処理フロー

#### Step 1: 駐車場を特定
```
Tool: search_parking
Arguments: { "query": "新宿西口パーキング", "search_type": "name" }
```

**結果:** parking_id = 456

#### Step 2: 設定を取得
```
Tool: get_parking_config
Arguments: { "parking_id": 456 }
```

**結果:**
```json
{
  "parking_id": 456,
  "parking_name": "新宿西口パーキング",
  "re_charge_grace_time": 60,
  "default_re_charge_time": 30,
  "effective_re_charge_time": 60,
  "re_charge_time_type": "個別設定",
  ...
}
```

### 回答
```
新宿西口パーキングの再課金猶予時間は【例外設定】です。

- 設定値: 60分（個別設定）
- デフォルト値: 30分

この物件には通常より長い60分の猶予時間が個別に設定されています。
```

---

## 例3: 夜間ルールの確認

### ユーザーの質問
```
「渋谷駅前パーキングは夜間ルールで何が変わる？」
```

### 処理フロー

#### Step 1: 駐車場を特定
```
Tool: search_parking
Arguments: { "query": "渋谷駅前パーキング", "search_type": "name" }
```

**結果:** parking_id = 789

#### Step 2: 夜間設定を取得
```
Tool: get_night_rate_config
Arguments: { "parking_id": 789 }
```

**実行されるSQL:**
```sql
SELECT
    p.name as parking_name,
    pc.night_rate_enabled,
    pc.night_rate_start_time,
    pc.night_rate_end_time,
    pc.night_rate_amount,
    pc.max_daily_charge
FROM parking_configs pc
JOIN parkings p ON pc.parking_id = p.id
WHERE pc.parking_id = 789
LIMIT 1
```

**結果:**
```json
{
  "parking_name": "渋谷駅前パーキング",
  "night_rate_enabled": true,
  "night_rate_start_time": "22:00:00",
  "night_rate_end_time": "08:00:00",
  "night_rate_amount": 500,
  "max_daily_charge": 1800
}
```

### 回答
```
渋谷駅前パーキングには夜間料金が設定されています。

【夜間ルールの内容】
- 適用時間帯: 22:00 〜 翌 08:00
- 夜間料金: 500円（この時間帯の固定料金）
- 1日最大料金: 1,800円

夜間帯（22:00以降）に入庫し、翌朝8:00までに出庫した場合、
通常料金ではなく夜間固定料金500円が適用されます。
```

---

## 例4: 該当なしの場合

### ユーザーの質問
```
「ABC パーキングの設定を教えて」
```

### 処理フロー

#### Step 1: 駐車場を特定
```
Tool: search_parking
Arguments: { "query": "ABC パーキング", "search_type": "name" }
```

**結果:** 空配列（該当なし）

### 回答
```
「ABC パーキング」という名前の駐車場は見つかりませんでした。

以下をご確認ください：
- 駐車場名の表記が正しいか（「パーキング」「駐車場」など）
- 駐車場コードをご存知であれば、コードでの検索もできます

例: 「TKY001 の設定を教えて」
```

---

## 例5: 曖昧な質問への対応

### ユーザーの質問
```
「駐車場の設定を見たい」
```

### 処理フロー
駐車場が特定されていないため、確認質問を返す。

### 回答
```
どの駐車場の設定を確認されたいですか？

以下のいずれかでご指定ください：
- 駐車場名（例: 「東京中央パーキング」）
- 駐車場コード（例: 「TKY001」）
- 駐車場ID（例: 「123」）

複数の条件で検索することもできます。
```

---

## 例6: カスタムSQLの実行

### ユーザーの質問
```
「夜間料金が有効な駐車場の一覧を見たい」
```

### 処理フロー

#### Step 1: カスタムSQLを実行
```
Tool: execute_readonly_sql
Arguments: {
  "query": "SELECT p.id, p.name, p.code, pc.night_rate_start_time, pc.night_rate_end_time, pc.night_rate_amount FROM parkings p JOIN parking_configs pc ON p.id = pc.parking_id WHERE pc.night_rate_enabled = true ORDER BY p.name"
}
```

**実行されるSQL（LIMIT自動付与後）:**
```sql
SELECT p.id, p.name, p.code, pc.night_rate_start_time, pc.night_rate_end_time, pc.night_rate_amount
FROM parkings p
JOIN parking_configs pc ON p.id = pc.parking_id
WHERE pc.night_rate_enabled = true
ORDER BY p.name
LIMIT 100
```

### 回答
```
夜間料金が有効な駐車場は以下の通りです（最大100件表示）:

| No | 駐車場名 | コード | 夜間開始 | 夜間終了 | 夜間料金 |
|----|----------|--------|----------|----------|----------|
| 1  | 渋谷駅前パーキング | SBY001 | 22:00 | 08:00 | 500円 |
| 2  | 新宿西口パーキング | SJK002 | 23:00 | 07:00 | 400円 |
| 3  | 東京中央パーキング | TKY001 | 22:00 | 06:00 | 600円 |
...

合計: XX件の駐車場で夜間料金が設定されています。
```

---

## セキュリティに関する補足

### 拒否される操作の例

以下のような操作は自動的に拒否されます：

```
✗ DELETE FROM parkings WHERE id = 1
  → エラー: SELECT文のみが許可されています

✗ SELECT * FROM users
  → エラー: 許可されていないテーブルが参照されています: users

✗ SELECT * FROM parkings; DROP TABLE parkings;
  → エラー: 複数のSQL文の実行は許可されていません

✗ SELECT SLEEP(10) FROM parkings
  → エラー: 禁止された関数が含まれています: SLEEP
```

### LIMIT の自動制御

```
入力: SELECT * FROM parkings
実行: SELECT * FROM parkings LIMIT 100  ← 自動付与

入力: SELECT * FROM parkings LIMIT 5000
実行: SELECT * FROM parkings LIMIT 1000  ← 最大値に制限
```
