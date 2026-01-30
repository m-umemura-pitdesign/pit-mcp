# MCP Parking Server

駐車場管理システム用の読み取り専用MCPサーバーです。
自然言語の質問に対して、データベースを参照し日本語で回答します。

## 機能

- 駐車場の検索（名前・コード・ID）
- 課金設定の取得（再課金猶予時間、夜間料金など）
- 読み取り専用SQLの実行
- スキーマコンテキストによる業務理解支援
- クエリ履歴の管理・統計
- 店舗WebDBへの動的接続（入出庫履歴取得）

### DB階層構造
```
Commons DB（親）
  └── 店舗WebDB（stores.domain/port）← 動的接続
```

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -e .
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# .env ファイルを編集してデータベース接続情報を設定
```

必要な環境変数：

```bash
# Commons DB接続
DB_HOST=localhost
DB_PORT=3306
DB_USER=readonly_user
DB_PASSWORD=xxx
DB_NAME=commons_management_api_development
DB_READ_ONLY=true

# 店舗WebDB接続（stores.domain/portで各店舗に接続する際の認証情報）
STORE_DB_USER=readonly_user
STORE_DB_PASSWORD=xxx
STORE_DB_NAME=smartparkdb_phase3
```

### 3. データベースユーザーの作成（推奨）

```sql
-- Commons DB用：読み取り専用ユーザーを作成
CREATE USER 'readonly_user'@'%' IDENTIFIED BY 'secure_password';

-- SELECT権限のみを付与
GRANT SELECT ON commons_management_api_development.* TO 'readonly_user'@'%';

FLUSH PRIVILEGES;
```

```sql
-- 店舗WebDB用：各店舗DBで同様に設定
GRANT SELECT ON smartparkdb_phase3.tbl_in_out_mgr TO 'readonly_user'@'%';
```

### 4. サーバーの起動

```bash
mcp-parking-server
```

## MCP クライアントからの接続

### Claude Desktop での設定例

`claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "parking": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/mcp-parking-server",
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "3306",
        "DB_USER": "readonly_user",
        "DB_PASSWORD": "secure_password",
        "DB_NAME": "commons_management_api_development",
        "STORE_DB_USER": "readonly_user",
        "STORE_DB_PASSWORD": "secure_password",
        "STORE_DB_NAME": "smartparkdb_phase3"
      }
    }
  }
}
```

## ツール一覧

### Commons DB操作

| ツール名 | 説明 |
|---------|------|
| `search_parking` | 駐車場を検索（名前・コード・ID） |
| `get_parking_config` | 駐車場の設定を取得 |
| `get_night_rate_config` | 夜間料金設定を取得 |
| `execute_readonly_sql` | 読み取り専用SQLを実行 |
| `get_schema_context` | スキーマの業務コンテキストを取得 |
| `explain_term` | 業務用語を説明 |
| `suggest_approach` | クエリアプローチを提案 |

### クエリ履歴

| ツール名 | 説明 |
|---------|------|
| `get_query_history` | クエリ履歴一覧を取得 |
| `get_query_history_detail` | クエリ履歴の詳細を取得 |
| `get_query_statistics` | クエリ実行の統計情報を取得 |
| `clear_query_history` | クエリ履歴をクリア |

### 店舗WebDB操作

| ツール名 | 説明 |
|---------|------|
| `get_store_servers` | 接続可能な店舗WebDB一覧を取得 |
| `get_entry_exit_history` | 店舗WebDBから入出庫履歴を取得 |

## プロジェクト構造

```
mcp-parking-server/
├── src/
│   ├── __init__.py
│   ├── server.py          # MCPサーバー本体
│   ├── database.py        # Commons DB接続
│   ├── store_database.py  # 店舗WebDB動的接続
│   ├── schema_context.py  # スキーマコンテキスト管理
│   ├── sql_validator.py   # SQLバリデーション
│   ├── query_history.py   # クエリ履歴管理
│   └── tools.py           # ツール定義
├── config/
│   └── schema_context.json # スキーマ定義
├── docs/
│   └── examples.md        # 使用例
├── .env.example
├── pyproject.toml
└── README.md
```

## セキュリティ

詳細は下記「セキュリティガードレール」セクションを参照してください。

---

# セキュリティガードレール

このMCPサーバーは、エンタープライズ環境での安全な運用を前提に設計されています。

## 1. 多層防御アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Client (Claude)                  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 1: ツールレベル制限                               │
│  - 事前定義されたツールのみ使用可能                       │
│  - 入力パラメータのバリデーション                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: SQLバリデーション (sql_validator.py)          │
│  - SELECT文のみ許可                                      │
│  - 禁止キーワード・関数のブロック                        │
│  - テーブルホワイトリスト                                │
│  - LIMIT強制                                             │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: データベース接続 (database.py)                │
│  - 読み取り専用トランザクション                          │
│  - クエリタイムアウト                                    │
│  - 接続プール制限                                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 4: データベースユーザー権限                       │
│  - SELECT権限のみ付与                                    │
│  - 対象テーブル限定                                      │
└─────────────────────────────────────────────────────────┘
```

## 2. SQLバリデーション詳細

### 2.1 禁止キーワード

以下のキーワードを含むクエリは拒否されます：

| カテゴリ | 禁止キーワード |
|---------|---------------|
| DML（データ変更） | INSERT, UPDATE, DELETE, REPLACE, TRUNCATE, MERGE |
| DDL（スキーマ変更） | CREATE, ALTER, DROP, RENAME |
| DCL（権限管理） | GRANT, REVOKE |
| トランザクション | COMMIT, ROLLBACK, SAVEPOINT |
| その他 | LOAD, HANDLER, CALL, EXECUTE, PREPARE |
| ファイル操作 | INTO OUTFILE, INTO DUMPFILE, LOAD_FILE |

### 2.2 禁止関数

SQLインジェクション対策として、以下の関数を禁止：

- `SLEEP()` - 時間ベース攻撃
- `BENCHMARK()` - 時間ベース攻撃
- `LOAD_FILE()` - ファイル読み取り

### 2.3 テーブルホワイトリスト

アクセス可能なテーブルを明示的に制限：

```python
# Commons DB
ALLOWED_TABLES = [
    "parkings", "stores", "servers", "labels",
    "vehicles", "unpaid_information", "paid_arrears",
    # ... など
]

# 店舗WebDB
ALLOWED_STORE_TABLES = [
    "tbl_in_out_mgr",
]
```

### 2.4 その他の制限

| 制限項目 | 内容 |
|---------|------|
| 複文実行 | セミコロンによる複数SQL実行を禁止 |
| コメント | `--`, `/**/`, `#` を禁止 |
| UNION | UNIONインジェクション対策として禁止 |
| サブクエリ | 最大1階層まで |
| LIMIT | 必須（自動付与）、最大1000件 |

## 3. データベースレベルの保護

### 3.1 読み取り専用トランザクション

```python
# 接続時に読み取り専用モードを設定
await cursor.execute("SET SESSION TRANSACTION READ ONLY")
```

### 3.2 タイムアウト制御

```python
# クエリタイムアウト（デフォルト30秒）
await asyncio.wait_for(
    cursor.execute(query, params),
    timeout=self.config.query_timeout
)
```

### 3.3 接続プール制限

```python
# 同時接続数を制限
pool_min_size=1
pool_max_size=5
```

## 4. 推奨されるデータベース設定

### 4.1 専用の読み取り専用ユーザー

```sql
-- 最小権限の原則に従ったユーザー作成
CREATE USER 'mcp_readonly'@'%' IDENTIFIED BY 'strong_password';

-- Commons DB：必要なテーブルにのみSELECT権限を付与
GRANT SELECT ON commons_management_api_development.parkings TO 'mcp_readonly'@'%';
GRANT SELECT ON commons_management_api_development.stores TO 'mcp_readonly'@'%';
GRANT SELECT ON commons_management_api_development.servers TO 'mcp_readonly'@'%';
-- ... 他のテーブルも同様

-- 権限を反映
FLUSH PRIVILEGES;
```

### 4.2 リードレプリカの使用（推奨）

本番環境では、リードレプリカに接続することを推奨します：

```
DB_HOST=replica.parking-db.internal
```

## 5. 監査とログ

### 5.1 アプリケーションログ

```python
# 全てのツール呼び出しをログ記録
logger.info(f"Tool called: {name} with args: {arguments}")
```

### 5.2 推奨される追加対策

- クエリログの永続化（CloudWatch Logs等）
- 異常なクエリパターンのアラート設定
- 定期的なアクセスログレビュー

## 6. プライバシー保護

### 6.1 個人情報の取り扱い

車両番号（`vehicles.car_number`、`tbl_in_out_mgr.CAR_NUMBER`）は個人情報に該当する可能性があります。
スキーマコンテキストでこれを明示し、不必要なアクセスを抑制します：

```json
{
  "privacy_note": "車両番号は個人情報に該当する可能性があるため、必要最小限の参照に留める"
}
```

### 6.2 データマスキング（オプション）

必要に応じて、機密カラムのマスキングを実装できます：

```sql
-- マスキングの例
SELECT
    INOUT_NO,
    CONCAT('****', RIGHT(CAR_NUMBER, 2)) as car_number_masked
FROM tbl_in_out_mgr
```

## 7. 障害対策

| 障害シナリオ | 対策 |
|-------------|------|
| DB接続失敗 | 明確なエラーメッセージを返却 |
| クエリタイムアウト | 30秒でタイムアウト、エラー返却 |
| 不正なSQL | バリデーションエラーを返却 |
| 大量データ | LIMITによる件数制限 |

## 8. セキュリティチェックリスト

デプロイ前に以下を確認してください：

- [ ] Commons DBユーザーはSELECT権限のみ持っている
- [ ] 店舗WebDBユーザーはSELECT権限のみ持っている
- [ ] 環境変数でパスワードを管理している（ハードコードしていない）
- [ ] リードレプリカまたは専用の参照用DBに接続している
- [ ] ネットワークアクセスが制限されている（VPC内など）
- [ ] アプリケーションログが有効になっている
- [ ] schema_context.json のテーブル一覧が実際のホワイトリストと一致している
