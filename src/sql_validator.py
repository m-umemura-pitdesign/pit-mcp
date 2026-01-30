"""
SQL バリデーター
読み取り専用クエリの安全性を検証するモジュール
"""

import re
from dataclasses import dataclass
from enum import Enum


class ValidationError(Exception):
    """SQLバリデーションエラー"""
    pass


class RiskLevel(Enum):
    """リスクレベル"""
    SAFE = "safe"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class ValidationResult:
    """バリデーション結果"""
    is_valid: bool
    risk_level: RiskLevel
    message: str
    sanitized_query: str | None = None


# 禁止キーワード（大文字で定義）
FORBIDDEN_KEYWORDS = [
    # DML（データ変更）
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "TRUNCATE",
    "MERGE",
    # DDL（スキーマ変更）
    "CREATE",
    "ALTER",
    "DROP",
    "RENAME",
    # DCL（権限管理）
    "GRANT",
    "REVOKE",
    # トランザクション制御
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    # その他の危険操作
    "LOAD",
    "HANDLER",
    "CALL",
    "EXECUTE",
    "PREPARE",
    "DEALLOCATE",
    # ファイル操作
    "INTO OUTFILE",
    "INTO DUMPFILE",
    "LOAD_FILE",
]

# 禁止関数（SQLインジェクション対策）
FORBIDDEN_FUNCTIONS = [
    "SLEEP",
    "BENCHMARK",
    "LOAD_FILE",
    "INTO OUTFILE",
    "INTO DUMPFILE",
]

# 許可されたテーブル（ホワイトリスト）- Commons DB
ALLOWED_TABLES = [
    # 駐車場・物件関連
    "parkings",
    "stores",
    "servers",
    "labels",
    "labels_groups",
    "groups",
    # 車両関連
    "vehicles",
    "vehicle_notes",
    "vehicle_note_kinds",
    # 未払い・支払い関連
    "unpaid_information",
    "paid_arrears",
    "unpaid_barcode_read_history",
    "amount_after_applying_service_tickets",
    # 依頼ツール関連
    "request_client_stores",
    "request_client_users",
    "request_client_store_users",
    "request_client_user_authorities",
    "request_client_products",
    "request_client_parking_operation_logs",
    # 請求取消関連
    "delete_request_histories",
    "delete_request_periods",
    "delete_request_reasons",
    "delete_request_refuse_reasons",
    "delete_request_change_logs",
    # 決済関連
    "agencies",
    "agencies_machine_kinds",
    "payment_fees",
    "gmo_pg_orders",
    # 空き状況・統計
    "parking_availabilities",
    "areas",
    # マスター
    "products",
    "server_types",
    "place_masters",
    "roles",
    # その他
    "notifications",
    "labels_notifications",
    "notification_addresses",
    "erp_code_map",
    "lock_vehicles",
    "accessible_vehicle_reasons",
]

# 許可されたテーブル（ホワイトリスト）- 店舗DB
ALLOWED_STORE_TABLES = [
    # 入出庫管理
    "tbl_in_out_mgr",
]

# LIMIT の最大値
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def validate_sql(query: str) -> ValidationResult:
    """
    SQLクエリを検証する

    Args:
        query: 検証対象のSQLクエリ

    Returns:
        ValidationResult: 検証結果
    """
    if not query or not query.strip():
        return ValidationResult(
            is_valid=False,
            risk_level=RiskLevel.BLOCKED,
            message="クエリが空です"
        )

    # 正規化（大文字化、余分な空白除去）
    normalized = " ".join(query.upper().split())
    original_normalized = " ".join(query.split())

    # 1. SELECTで始まることを確認
    if not normalized.lstrip().startswith("SELECT"):
        return ValidationResult(
            is_valid=False,
            risk_level=RiskLevel.BLOCKED,
            message="SELECT文のみが許可されています"
        )

    # 2. 禁止キーワードのチェック
    for keyword in FORBIDDEN_KEYWORDS:
        # 単語境界でマッチするパターン
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, normalized):
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.BLOCKED,
                message=f"禁止されたキーワードが含まれています: {keyword}"
            )

    # 3. 禁止関数のチェック
    for func in FORBIDDEN_FUNCTIONS:
        pattern = r'\b' + re.escape(func) + r'\s*\('
        if re.search(pattern, normalized):
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.BLOCKED,
                message=f"禁止された関数が含まれています: {func}"
            )

    # 4. コメントインジェクション対策
    if "--" in query or "/*" in query or "#" in query:
        return ValidationResult(
            is_valid=False,
            risk_level=RiskLevel.BLOCKED,
            message="SQLコメントは許可されていません"
        )

    # 5. セミコロンによる複文実行の防止（文末以外）
    query_without_end = query.rstrip().rstrip(";")
    if ";" in query_without_end:
        return ValidationResult(
            is_valid=False,
            risk_level=RiskLevel.BLOCKED,
            message="複数のSQL文の実行は許可されていません"
        )

    # 6. UNION インジェクション対策（サブクエリ内以外の UNION を警告）
    if "UNION" in normalized:
        return ValidationResult(
            is_valid=False,
            risk_level=RiskLevel.BLOCKED,
            message="UNION句は許可されていません"
        )

    # 7. テーブルのホワイトリストチェック
    table_check = _check_allowed_tables(normalized)
    if not table_check.is_valid:
        return table_check

    # 8. LIMIT の確認と付与
    sanitized_query, limit_message = _ensure_limit(original_normalized)

    # 9. サブクエリの制限（深いネストを防ぐ）
    subquery_count = normalized.count("SELECT")
    if subquery_count > 2:  # メインクエリ + 1つのサブクエリまで許可
        return ValidationResult(
            is_valid=False,
            risk_level=RiskLevel.WARNING,
            message="サブクエリのネストが深すぎます（最大1階層）"
        )

    return ValidationResult(
        is_valid=True,
        risk_level=RiskLevel.SAFE,
        message=limit_message or "クエリは安全です",
        sanitized_query=sanitized_query
    )


def _check_allowed_tables(normalized_query: str) -> ValidationResult:
    """
    使用されているテーブルがホワイトリストに含まれているか確認
    """
    # FROM句とJOIN句からテーブル名を抽出
    # 簡易的な正規表現（実運用ではSQLパーサーを使用推奨）
    from_pattern = r'\bFROM\s+([A-Z_][A-Z0-9_]*)'
    join_pattern = r'\bJOIN\s+([A-Z_][A-Z0-9_]*)'

    tables = set()

    for match in re.finditer(from_pattern, normalized_query):
        tables.add(match.group(1).lower())

    for match in re.finditer(join_pattern, normalized_query):
        tables.add(match.group(1).lower())

    # ホワイトリストチェック
    for table in tables:
        if table not in ALLOWED_TABLES:
            return ValidationResult(
                is_valid=False,
                risk_level=RiskLevel.BLOCKED,
                message=f"許可されていないテーブルが参照されています: {table}"
            )

    return ValidationResult(
        is_valid=True,
        risk_level=RiskLevel.SAFE,
        message="テーブル参照は許可されています"
    )


def _ensure_limit(query: str) -> tuple[str, str | None]:
    """
    LIMIT句の確認と必要に応じた付与

    Returns:
        tuple[str, str | None]: (修正後のクエリ, メッセージ)
    """
    normalized = query.upper()

    # 既存のLIMITを確認
    limit_match = re.search(r'\bLIMIT\s+(\d+)', normalized)

    if limit_match:
        current_limit = int(limit_match.group(1))
        if current_limit > MAX_LIMIT:
            # LIMITが大きすぎる場合は制限
            modified = re.sub(
                r'\bLIMIT\s+\d+',
                f'LIMIT {MAX_LIMIT}',
                query,
                flags=re.IGNORECASE
            )
            return modified, f"LIMITを{MAX_LIMIT}に制限しました"
        return query, None
    else:
        # LIMITがない場合は追加
        # 末尾のセミコロンを考慮
        query = query.rstrip().rstrip(";")
        return f"{query} LIMIT {DEFAULT_LIMIT}", f"LIMIT {DEFAULT_LIMIT}を自動付与しました"


def sanitize_identifier(identifier: str) -> str:
    """
    識別子（テーブル名、カラム名）をサニタイズ
    """
    # 英数字とアンダースコアのみ許可
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValidationError(f"不正な識別子: {identifier}")
    return identifier


def sanitize_value(value: str) -> str:
    """
    値をサニタイズ（プレースホルダー使用推奨）
    """
    # シングルクォートをエスケープ
    return value.replace("'", "''")
