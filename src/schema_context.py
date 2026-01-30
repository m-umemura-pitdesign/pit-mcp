"""
スキーマコンテキストモジュール
テーブル・カラムの業務的意味を管理し、AI推論を支援
"""

import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ColumnInfo:
    """カラム情報"""
    name: str
    type: str
    description: str
    business_meaning: str = ""
    nullable: bool = False
    default_value: any = None
    default_behavior: str = ""


@dataclass
class BusinessRule:
    """業務ルール"""
    rule_id: str
    description: str
    logic: str
    sql_expression: str = ""


@dataclass
class TableInfo:
    """テーブル情報"""
    name: str
    description: str
    business_context: str
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    business_rules: list[BusinessRule] = field(default_factory=list)
    common_queries: list[str] = field(default_factory=list)
    privacy_note: str = ""


class SchemaContext:
    """
    スキーマコンテキスト管理クラス

    役割:
    - テーブル・カラムの業務的意味を提供
    - AIが適切なクエリを生成するためのコンテキストを構築
    - 用語集の管理
    """

    def __init__(self, config_path: str | Path | None = None):
        self.tables: dict[str, TableInfo] = {}
        self.glossary: dict[str, str] = {}
        self.query_patterns: dict[str, dict] = {}

        if config_path:
            self.load_from_file(config_path)

    def load_from_file(self, config_path: str | Path) -> None:
        """JSONファイルからスキーマコンテキストを読み込む"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._parse_config(data)

    def _parse_config(self, data: dict) -> None:
        """設定データをパース"""
        # テーブル情報
        for table_name, table_data in data.get("tables", {}).items():
            columns = {}
            for col_name, col_data in table_data.get("columns", {}).items():
                columns[col_name] = ColumnInfo(
                    name=col_name,
                    type=col_data.get("type", ""),
                    description=col_data.get("description", ""),
                    business_meaning=col_data.get("business_meaning", ""),
                    nullable=col_data.get("nullable", False),
                    default_value=col_data.get("default_value"),
                    default_behavior=col_data.get("default_behavior", ""),
                )

            rules = []
            for rule_data in table_data.get("business_rules", []):
                rules.append(BusinessRule(
                    rule_id=rule_data.get("rule_id", ""),
                    description=rule_data.get("description", ""),
                    logic=rule_data.get("logic", ""),
                    sql_expression=rule_data.get("sql_expression", ""),
                ))

            self.tables[table_name] = TableInfo(
                name=table_name,
                description=table_data.get("description", ""),
                business_context=table_data.get("business_context", ""),
                columns=columns,
                business_rules=rules,
                common_queries=table_data.get("common_queries", []),
                privacy_note=table_data.get("privacy_note", ""),
            )

        # 用語集
        self.glossary = data.get("glossary", {})

        # クエリパターン
        self.query_patterns = data.get("query_patterns", {})

    def get_table_context(self, table_name: str) -> str:
        """
        テーブルの業務コンテキストを取得

        Args:
            table_name: テーブル名

        Returns:
            str: 業務コンテキストの説明文
        """
        if table_name not in self.tables:
            return f"テーブル '{table_name}' の情報はありません"

        table = self.tables[table_name]
        lines = [
            f"## {table_name}",
            f"説明: {table.description}",
            f"業務コンテキスト: {table.business_context}",
            "",
            "### カラム",
        ]

        for col_name, col in table.columns.items():
            col_line = f"- {col_name} ({col.type}): {col.description}"
            if col.business_meaning:
                col_line += f"\n  業務的意味: {col.business_meaning}"
            if col.default_behavior:
                col_line += f"\n  デフォルト動作: {col.default_behavior}"
            lines.append(col_line)

        if table.business_rules:
            lines.append("")
            lines.append("### 業務ルール")
            for rule in table.business_rules:
                lines.append(f"- [{rule.rule_id}] {rule.description}")
                lines.append(f"  ロジック: {rule.logic}")
                if rule.sql_expression:
                    lines.append(f"  SQL式: {rule.sql_expression}")

        if table.privacy_note:
            lines.append("")
            lines.append(f"⚠️ 注意: {table.privacy_note}")

        return "\n".join(lines)

    def get_full_context(self) -> str:
        """
        全テーブルの業務コンテキストを取得

        Returns:
            str: 全スキーマの説明文
        """
        sections = ["# 駐車場管理システム スキーマコンテキスト\n"]

        # 用語集
        if self.glossary:
            sections.append("## 用語集")
            for term, definition in self.glossary.items():
                sections.append(f"- **{term}**: {definition}")
            sections.append("")

        # 各テーブル
        for table_name in self.tables:
            sections.append(self.get_table_context(table_name))
            sections.append("")

        return "\n".join(sections)

    def get_column_info(self, table_name: str, column_name: str) -> ColumnInfo | None:
        """特定カラムの情報を取得"""
        if table_name not in self.tables:
            return None
        return self.tables[table_name].columns.get(column_name)

    def get_business_rule(self, table_name: str, rule_id: str) -> BusinessRule | None:
        """特定の業務ルールを取得"""
        if table_name not in self.tables:
            return None
        for rule in self.tables[table_name].business_rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def explain_term(self, term: str) -> str:
        """用語の説明を取得"""
        if term in self.glossary:
            return f"{term}: {self.glossary[term]}"
        return f"用語 '{term}' の定義はありません"

    def suggest_query_approach(self, question: str) -> str:
        """
        質問に対するクエリアプローチを提案

        Args:
            question: ユーザーの質問

        Returns:
            str: 推奨されるアプローチの説明
        """
        suggestions = []

        # 再課金猶予に関する質問
        if "再課金" in question or "猶予" in question:
            suggestions.append("""
### 再課金猶予時間の確認
1. まず `parkings` テーブルで対象の駐車場を特定
2. `parking_configs` テーブルで設定を取得
3. `re_charge_grace_time` が NULL の場合は `default_re_charge_time` を使用
4. SQL式: COALESCE(re_charge_grace_time, default_re_charge_time)
            """)

        # 夜間料金に関する質問
        if "夜間" in question or "ナイト" in question:
            suggestions.append("""
### 夜間料金設定の確認
1. `parking_configs` テーブルの `night_rate_enabled` を確認
2. true の場合、`night_rate_start_time` と `night_rate_end_time` で適用時間帯を確認
3. `night_rate_amount` で夜間料金を確認
            """)

        # デフォルト・例外に関する質問
        if "デフォルト" in question or "例外" in question:
            suggestions.append("""
### デフォルト値と例外設定の判定
- 値が NULL の場合 → デフォルト値を使用
- 値が設定されている場合 → 例外（個別設定）
- 回答時は必ずどちらかを明示する
            """)

        if not suggestions:
            suggestions.append("""
### 一般的なアプローチ
1. 対象の駐車場を特定（名前 or コード or ID）
2. 必要なテーブルを特定
3. 最小限のSELECT文を生成
4. 結果を業務文脈に沿って説明
            """)

        return "\n".join(suggestions)
