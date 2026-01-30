"""
MCP ツール定義
駐車場管理システム用の読み取り専用ツール
"""

from dataclasses import dataclass
from typing import Any

from .database import ReadOnlyDatabase, QueryResult
from .schema_context import SchemaContext


@dataclass
class ToolResponse:
    """ツール実行結果"""
    success: bool
    data: Any
    message: str
    context: str = ""  # 業務コンテキスト補足


class ParkingTools:
    """
    駐車場管理システム用MCPツール

    提供ツール:
    - search_parking: 駐車場を検索
    - get_parking_config: 駐車場設定を取得
    - execute_readonly_sql: 読み取り専用SQLを実行
    - get_schema_context: スキーマの業務コンテキストを取得
    """

    def __init__(self, db: ReadOnlyDatabase, schema: SchemaContext):
        self.db = db
        self.schema = schema

    # ========================================
    # Tool: search_parking
    # ========================================
    async def search_parking(
        self,
        query: str,
        search_type: str = "name"
    ) -> ToolResponse:
        """
        駐車場を検索する

        Args:
            query: 検索クエリ（名前、コード、またはID）
            search_type: 検索タイプ ("name", "code", "id")

        Returns:
            ToolResponse: 検索結果

        Example:
            search_parking("東京", search_type="name")
            search_parking("TKY001", search_type="code")
            search_parking("123", search_type="id")
        """
        if search_type == "name":
            result = await self.db.find_parking_by_name(query)
        elif search_type == "code":
            result = await self.db.find_parking_by_code(query)
        elif search_type == "id":
            try:
                parking_id = int(query)
            except ValueError:
                return ToolResponse(
                    success=False,
                    data=None,
                    message="IDは数値で指定してください"
                )
            sql = "SELECT id, name, code, address, status FROM parkings WHERE id = %s LIMIT 1"
            result = await self.db.execute_query(sql, (parking_id,))
        else:
            return ToolResponse(
                success=False,
                data=None,
                message=f"不正な検索タイプ: {search_type}"
            )

        if not result.success:
            return ToolResponse(
                success=False,
                data=None,
                message=result.message
            )

        if not result.data:
            return ToolResponse(
                success=True,
                data=[],
                message="該当する駐車場が見つかりませんでした",
                context="検索条件を変えて再度お試しください"
            )

        return ToolResponse(
            success=True,
            data=result.data,
            message=f"{len(result.data)}件の駐車場が見つかりました",
            context="駐車場IDを使って詳細設定を確認できます"
        )

    # ========================================
    # Tool: get_parking_config
    # ========================================
    async def get_parking_config(self, parking_id: int) -> ToolResponse:
        """
        駐車場の設定を取得する

        Args:
            parking_id: 駐車場ID

        Returns:
            ToolResponse: 設定情報

        業務ルール:
        - re_charge_grace_time が NULL の場合は default_re_charge_time を使用
        - 回答には「デフォルト」か「個別設定」かを明示する
        """
        result = await self.db.get_parking_config(parking_id)

        if not result.success:
            return ToolResponse(
                success=False,
                data=None,
                message=result.message
            )

        if not result.data:
            return ToolResponse(
                success=True,
                data=None,
                message=f"駐車場ID {parking_id} の設定が見つかりませんでした",
                context="駐車場IDが正しいか確認してください"
            )

        config = result.data[0]

        # 業務コンテキストを付与
        context_lines = []

        # 再課金猶予時間の説明
        if config.get("re_charge_time_type") == "デフォルト":
            context_lines.append(
                f"再課金猶予時間: {config.get('effective_re_charge_time')}分（デフォルト値を使用）"
            )
        else:
            context_lines.append(
                f"再課金猶予時間: {config.get('effective_re_charge_time')}分（個別設定）"
            )

        # 夜間料金の説明
        if config.get("night_rate_enabled"):
            context_lines.append(
                f"夜間料金: 有効（{config.get('night_rate_start_time')} - "
                f"{config.get('night_rate_end_time')}, {config.get('night_rate_amount')}円）"
            )
        else:
            context_lines.append("夜間料金: 無効")

        # 最大日額の説明
        if config.get("max_daily_charge"):
            context_lines.append(f"1日最大料金: {config.get('max_daily_charge')}円")
        else:
            context_lines.append("1日最大料金: 上限なし")

        return ToolResponse(
            success=True,
            data=config,
            message=f"{config.get('parking_name')} の設定を取得しました",
            context="\n".join(context_lines)
        )

    # ========================================
    # Tool: get_night_rate_config
    # ========================================
    async def get_night_rate_config(self, parking_id: int) -> ToolResponse:
        """
        夜間料金設定を取得する

        Args:
            parking_id: 駐車場ID

        Returns:
            ToolResponse: 夜間料金設定
        """
        result = await self.db.get_night_rate_config(parking_id)

        if not result.success:
            return ToolResponse(
                success=False,
                data=None,
                message=result.message
            )

        if not result.data:
            return ToolResponse(
                success=True,
                data=None,
                message=f"駐車場ID {parking_id} の夜間設定が見つかりませんでした"
            )

        config = result.data[0]
        parking_name = config.get("parking_name", f"ID:{parking_id}")

        if not config.get("night_rate_enabled"):
            return ToolResponse(
                success=True,
                data=config,
                message=f"{parking_name} では夜間料金は無効です",
                context="通常料金が24時間適用されます"
            )

        context = (
            f"夜間料金適用時間: {config.get('night_rate_start_time')} - "
            f"{config.get('night_rate_end_time')}\n"
            f"夜間料金: {config.get('night_rate_amount')}円"
        )

        if config.get("max_daily_charge"):
            context += f"\n1日最大料金: {config.get('max_daily_charge')}円"

        return ToolResponse(
            success=True,
            data=config,
            message=f"{parking_name} の夜間料金設定を取得しました",
            context=context
        )

    # ========================================
    # Tool: execute_readonly_sql
    # ========================================
    async def execute_readonly_sql(
        self,
        query: str,
        params: tuple | None = None
    ) -> ToolResponse:
        """
        読み取り専用SQLを実行する

        セキュリティ:
        - SELECT文のみ許可
        - LIMIT必須（自動付与）
        - 禁止キーワードチェック
        - タイムアウト制御

        Args:
            query: 実行するSQLクエリ（SELECT文のみ）
            params: クエリパラメータ

        Returns:
            ToolResponse: クエリ結果

        Example:
            execute_readonly_sql(
                "SELECT * FROM parkings WHERE name LIKE %s",
                ("%東京%",)
            )
        """
        result = await self.db.execute_query(query, params, tool_name="execute_readonly_sql")

        if not result.success:
            return ToolResponse(
                success=False,
                data=None,
                message=result.message,
                context="クエリを修正して再実行してください"
            )

        return ToolResponse(
            success=True,
            data=result.data,
            message=result.message,
            context=f"実行されたクエリ: {result.executed_query}"
        )

    # ========================================
    # Tool: get_schema_context
    # ========================================
    def get_schema_context(
        self,
        table_name: str | None = None
    ) -> ToolResponse:
        """
        スキーマの業務コンテキストを取得する

        Args:
            table_name: テーブル名（省略時は全テーブル）

        Returns:
            ToolResponse: スキーマコンテキスト

        用途:
        - AIがクエリを生成する前にテーブル構造を理解する
        - カラムの業務的意味を確認する
        - 業務ルールを確認する
        """
        if table_name:
            if table_name not in self.schema.tables:
                return ToolResponse(
                    success=False,
                    data=None,
                    message=f"テーブル '{table_name}' は存在しません",
                    context=f"利用可能なテーブル: {', '.join(self.schema.tables.keys())}"
                )
            context = self.schema.get_table_context(table_name)
        else:
            context = self.schema.get_full_context()

        return ToolResponse(
            success=True,
            data={"context": context},
            message="スキーマコンテキストを取得しました"
        )

    # ========================================
    # Tool: explain_term
    # ========================================
    def explain_term(self, term: str) -> ToolResponse:
        """
        業務用語を説明する

        Args:
            term: 説明を求める用語

        Returns:
            ToolResponse: 用語の説明
        """
        if term in self.schema.glossary:
            return ToolResponse(
                success=True,
                data={"term": term, "definition": self.schema.glossary[term]},
                message=f"用語「{term}」の説明を取得しました"
            )

        return ToolResponse(
            success=False,
            data=None,
            message=f"用語「{term}」の定義が見つかりません",
            context=f"登録済みの用語: {', '.join(self.schema.glossary.keys())}"
        )

    # ========================================
    # Tool: suggest_approach
    # ========================================
    def suggest_approach(self, question: str) -> ToolResponse:
        """
        質問に対するアプローチを提案する

        Args:
            question: ユーザーの質問

        Returns:
            ToolResponse: 推奨アプローチ
        """
        suggestion = self.schema.suggest_query_approach(question)

        return ToolResponse(
            success=True,
            data={"suggestion": suggestion},
            message="クエリアプローチを提案しました",
            context="この提案を参考にクエリを生成してください"
        )

    # ========================================
    # Tool: get_query_history
    # ========================================
    def get_query_history(
        self,
        limit: int = 20,
        success_only: bool = False,
        failed_only: bool = False,
        keyword: str | None = None
    ) -> ToolResponse:
        """
        クエリ実行履歴を取得する

        Args:
            limit: 取得件数（デフォルト20件）
            success_only: 成功したクエリのみ
            failed_only: 失敗したクエリのみ
            keyword: クエリに含まれるキーワード

        Returns:
            ToolResponse: 履歴リスト
        """
        if keyword or success_only or failed_only:
            entries = self.db.history.search(
                keyword=keyword,
                success_only=success_only,
                failed_only=failed_only,
                limit=limit
            )
        else:
            entries = self.db.history.get_all(limit=limit)

        history_data = [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "query": e.query[:100] + "..." if len(e.query) > 100 else e.query,
                "success": e.success,
                "row_count": e.row_count,
                "execution_time_ms": e.execution_time_ms,
                "error": e.error_message
            }
            for e in entries
        ]

        return ToolResponse(
            success=True,
            data=history_data,
            message=f"{len(history_data)}件の履歴を取得しました"
        )

    # ========================================
    # Tool: get_query_history_detail
    # ========================================
    def get_query_history_detail(self, history_id: int) -> ToolResponse:
        """
        クエリ履歴の詳細を取得する

        Args:
            history_id: 履歴ID

        Returns:
            ToolResponse: 履歴詳細
        """
        entry = self.db.history.get_by_id(history_id)

        if not entry:
            return ToolResponse(
                success=False,
                data=None,
                message=f"履歴ID {history_id} が見つかりません"
            )

        return ToolResponse(
            success=True,
            data={
                "id": entry.id,
                "timestamp": entry.timestamp,
                "query": entry.query,
                "params": entry.params,
                "success": entry.success,
                "row_count": entry.row_count,
                "execution_time_ms": entry.execution_time_ms,
                "error_message": entry.error_message,
                "tool_name": entry.tool_name
            },
            message="履歴詳細を取得しました",
            context="このクエリを再実行するには execute_readonly_sql を使用してください"
        )

    # ========================================
    # Tool: get_query_statistics
    # ========================================
    def get_query_statistics(self) -> ToolResponse:
        """
        クエリ実行の統計情報を取得する

        Returns:
            ToolResponse: 統計情報
        """
        stats = self.db.history.get_statistics()

        return ToolResponse(
            success=True,
            data=stats,
            message="クエリ統計を取得しました",
            context=f"成功率: {stats['success_rate']}%, 平均実行時間: {stats['avg_execution_time_ms']}ms"
        )

    # ========================================
    # Tool: clear_query_history
    # ========================================
    def clear_query_history(self) -> ToolResponse:
        """
        クエリ履歴をクリアする

        Returns:
            ToolResponse: 削除件数
        """
        count = self.db.history.clear()

        return ToolResponse(
            success=True,
            data={"deleted_count": count},
            message=f"{count}件の履歴を削除しました"
        )


# ツール定義（MCP形式）
TOOL_DEFINITIONS = [
    {
        "name": "search_parking",
        "description": "駐車場を検索します。名前、コード、またはIDで検索できます。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ（駐車場名、コード、またはID）"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["name", "code", "id"],
                    "default": "name",
                    "description": "検索タイプ: name=名前検索（部分一致）, code=コード検索（完全一致）, id=ID検索"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_parking_config",
        "description": "指定した駐車場の設定（再課金猶予時間、夜間料金など）を取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parking_id": {
                    "type": "integer",
                    "description": "駐車場ID"
                }
            },
            "required": ["parking_id"]
        }
    },
    {
        "name": "get_night_rate_config",
        "description": "指定した駐車場の夜間料金設定を取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parking_id": {
                    "type": "integer",
                    "description": "駐車場ID"
                }
            },
            "required": ["parking_id"]
        }
    },
    {
        "name": "execute_readonly_sql",
        "description": "読み取り専用のSQLクエリを実行します。SELECT文のみ許可されています。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "実行するSELECT文。LIMITは自動付与されます。"
                },
                "params": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "クエリパラメータ（プレースホルダー %s に対応）"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_schema_context",
        "description": "テーブルの業務コンテキスト（カラムの意味、業務ルールなど）を取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "テーブル名（省略時は全テーブルの情報を取得）"
                }
            }
        }
    },
    {
        "name": "explain_term",
        "description": "業務用語の意味を説明します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "term": {
                    "type": "string",
                    "description": "説明を求める用語"
                }
            },
            "required": ["term"]
        }
    },
    {
        "name": "suggest_approach",
        "description": "質問に対する推奨クエリアプローチを提案します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "ユーザーの質問"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "get_query_history",
        "description": "実行されたSQLクエリの履歴を取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "取得件数（デフォルト20件、最大100件）"
                },
                "success_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "成功したクエリのみ取得"
                },
                "failed_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "失敗したクエリのみ取得"
                },
                "keyword": {
                    "type": "string",
                    "description": "クエリに含まれるキーワードでフィルタ"
                }
            }
        }
    },
    {
        "name": "get_query_history_detail",
        "description": "指定したIDのクエリ履歴の詳細（完全なSQL文、パラメータ等）を取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "history_id": {
                    "type": "integer",
                    "description": "履歴ID"
                }
            },
            "required": ["history_id"]
        }
    },
    {
        "name": "get_query_statistics",
        "description": "クエリ実行の統計情報（成功率、平均実行時間など）を取得します。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "clear_query_history",
        "description": "全てのクエリ履歴を削除します。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]
