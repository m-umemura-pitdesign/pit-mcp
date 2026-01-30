# MCP Parking Server

Commons駐車場管理システム用の読み取り専用MCPサーバー。
自然言語の質問に対してデータベースを参照し、日本語で回答する。

## プロジェクト概要

- **目的**: 駐車場管理システムのDBを参照し、運用支援の質問に回答
- **制約**: 読み取り専用（SELECT のみ）、INSERT/UPDATE/DELETE は完全禁止
- **対象DB**:
  - Commons DB: commons_management_api_development（MySQL 8.0）
  - 店舗WebDB: stores.domain/portで各店舗のWebDBサーバー（smartparkdb_phase3）に動的接続

### DB階層構造
```
Commons DB（親）
  └── 店舗WebDB（stores.domain/port）← ここに接続
```

## クイックスタート

```bash
# インストール
python -m pip install -e .

# 起動（テスト）
python -m src.server

# Claude Desktop 用設定は %APPDATA%\Claude\claude_desktop_config.json に記載
```

## プロジェクト構造

```
mcp-parking-server/
├── src/
│   ├── server.py          # MCPサーバー本体（エントリーポイント: main()）
│   ├── database.py        # Commons DB接続（ReadOnlyDatabase クラス）
│   ├── store_database.py  # 店舗DB動的接続（StoreDatabase クラス）
│   ├── schema_context.py  # 業務意味レイヤー（SchemaContext クラス）
│   ├── sql_validator.py   # SQLセキュリティ検証（validate_sql()）
│   └── tools.py           # MCPツール定義（ParkingTools クラス）
├── config/
│   └── schema_context.json # テーブル・カラムの業務定義
├── docs/
│   ├── examples.md        # 質問→SQL→回答の例
│   └── sample_schema.sql  # サンプルDDL
└── pyproject.toml
```

## 主要コンポーネント

### sql_validator.py
- `validate_sql(query)`: SQLの安全性を検証
- `ALLOWED_TABLES`: アクセス可能なテーブルのホワイトリスト
- SELECT以外は全てブロック、LIMIT自動付与（最大1000件）

### database.py
- `ReadOnlyDatabase`: 読み取り専用DB接続クラス
- `SET SESSION TRANSACTION READ ONLY` で読み取り専用を強制
- タイムアウト: 30秒（設定変更可）

### schema_context.py
- `SchemaContext`: テーブル・カラムの業務的意味を管理
- `config/schema_context.json` から定義を読み込み
- AIがクエリ生成時に参照

### store_database.py
- `StoreDatabase`: 店舗WebDB動的接続クラス
- stores.domain/portを使用して各店舗のWebDBサーバーに接続
- `SET SESSION TRANSACTION READ ONLY` で読み取り専用を強制
- 接続タイムアウト: 30秒

### tools.py
MCPツール13種:

**Commons DB操作:**
1. `search_parking` - 駐車場検索（名前/ERPコード/ID）
2. `get_parking_config` - 駐車場設定取得
3. `get_night_rate_config` - 夜間料金設定取得
4. `execute_readonly_sql` - 読み取り専用SQL実行
5. `get_schema_context` - スキーマの業務コンテキスト取得
6. `explain_term` - 業務用語の説明
7. `suggest_approach` - クエリアプローチ提案

**クエリ履歴:**
8. `get_query_history` - クエリ履歴一覧
9. `get_query_history_detail` - クエリ履歴詳細
10. `get_query_statistics` - クエリ統計
11. `clear_query_history` - 履歴クリア

**店舗WebDB操作:**
12. `get_store_servers` - 接続可能な店舗WebDB一覧取得
13. `get_entry_exit_history` - 店舗WebDBから入出庫履歴取得

## 主要テーブル

### Commons DB

| テーブル | 説明 | 重要カラム |
|---------|------|-----------|
| `parkings` | 駐車場 | `default_re_charge_time`（再課金猶予時間） |
| `stores` | 物件 | `name`, `domain`, `is_outage`, `address`, `port`（WebDBサーバー接続情報） |
| `servers` | サーバー情報 | `lid`, `gid`, `erp_code`, `address`, `port`（gid=3: Localサーバー接続情報） |
| `server_type` | サーバー種別 | `id`（=gid）, `name`（種別名） |
| `labels` | ラベル | `label`（物件名） |
| `vehicles` | 車両情報 | `place`, `class_number`, `kana`, `car_number` |
| `unpaid_information` | 未払い情報 | `pay_arrears`, `penalty`, `pay_finished_flg` |

### 店舗WebDB（stores.domain/port）

| テーブル | 説明 | 重要カラム |
|---------|------|-----------|
| `tbl_in_out_mgr` | 入出庫履歴 | `ENTRANT_TIME`, `EXIT_TIME`, `VEHICLE_STATUS_ID`, `CAR_NUMBER` |

## 業務用語

- **再課金猶予時間**: 出庫後に再入庫した際、新たな課金が発生しない猶予期間（分）
- **ERPコード**: 社内管理用の物件識別コード
- **ラベルID (lid)**: Webサーバー単位での物件識別ID
- **gid**: サーバー種別ID（server_typeテーブルに紐づく。3=ローカルサーバー、5=SSHサーバー）
- **pid**: ローカルサーバー上での駐車場識別番号
- **店舗WebDB**: stores.domain/portで接続するWebDBサーバー上のMySQL DB（smartparkdb_phase3）
- **VEHICLE_STATUS_ID**: 車両ステータス（0=入庫中、1=未精算出庫、2=出庫済）
- **CHECKOUT_FLG**: 精算フラグ（0=未精算、1=精算済）

### 新機能追加時
1. まずプランモードで計画を立てる
2. 計画を私に確認させる
3. 承認後、テストを先に書く
4. テストが通る実装を行う
5. 完了後、動作確認を依頼する

## セキュリティ

### 4層防御
1. **ツールレベル**: 事前定義ツールのみ使用可能
2. **SQLバリデーション**: SELECT限定、禁止キーワード、テーブルホワイトリスト
3. **DB接続**: READ ONLYトランザクション、30秒タイムアウト
4. **DBユーザー**: SELECT権限のみ付与推奨

### 禁止されるSQL
- INSERT, UPDATE, DELETE, DROP, CREATE, ALTER
- UNION, サブクエリ2階層以上
- SLEEP(), BENCHMARK() 等の危険関数
- SQLコメント（--, /*, #）

## 環境変数

```bash
# Commons DB接続
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=readonly_user
DB_PASSWORD=xxx
DB_NAME=commons_management_api_development
DB_READ_ONLY=true
DB_QUERY_TIMEOUT=30

# 店舗WebDB接続（stores.domain/portで各店舗WebDBに接続する際の認証情報）
STORE_DB_USER=readonly_user
STORE_DB_PASSWORD=xxx
STORE_DB_NAME=smartparkdb_phase3
```

## テスト方法

```bash
# MCPプロトコルでテスト
cd mcp-parking-server
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python -m src.server

# ツール一覧取得
cat << 'EOF' | python -m src.server
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
EOF
```

## 想定される質問例

- 「〇〇駐車場の再課金猶予時間は何分？」
- 「この物件の再課金猶予はデフォルト？それとも例外？」
- 「ERPコード XXX の駐車場情報を教えて」
- 「未払い情報のテーブル構造を教えて」
- 「〇〇店舗の入出庫履歴を見せて」
- 「車両番号 1234 の入庫記録を検索」

## 変更時の注意

- Commons DBテーブル追加時は `sql_validator.py` の `ALLOWED_TABLES` に追加必須
- 店舗DBテーブル追加時は `sql_validator.py` の `ALLOWED_STORE_TABLES` に追加必須
- 業務ルール追加時は `config/schema_context.json` を更新
- ツール追加時は `tools.py` の `TOOL_DEFINITIONS` と `ParkingTools` クラスを更新
