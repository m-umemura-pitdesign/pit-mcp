"""
MCP Parking Server
駐車場管理システム用の読み取り専用MCPサーバー
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
)

from .database import ReadOnlyDatabase, DatabaseConfig
from .schema_context import SchemaContext
from .tools import ParkingTools, TOOL_DEFINITIONS

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp-parking-server")

# 設定ファイルパス
CONFIG_DIR = Path(__file__).parent.parent / "config"
SCHEMA_CONTEXT_PATH = CONFIG_DIR / "schema_context.json"


class ParkingMCPServer:
    """
    駐車場管理システム用MCPサーバー

    機能:
    - 読み取り専用データベースアクセス
    - スキーマコンテキストによる業務理解支援
    - 安全なSQLバリデーション
    """

    def __init__(self):
        self.server = Server("parking-management-server")
        self.db: ReadOnlyDatabase | None = None
        self.schema: SchemaContext | None = None
        self.tools: ParkingTools | None = None

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """MCPハンドラーを設定"""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """利用可能なツール一覧を返す"""
            return [
                Tool(
                    name=t["name"],
                    description=t["description"],
                    inputSchema=t["inputSchema"]
                )
                for t in TOOL_DEFINITIONS
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
            """ツールを実行"""
            logger.info(f"Tool called: {name} with args: {arguments}")

            if self.tools is None:
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text="エラー: サーバーが初期化されていません"
                    )],
                    isError=True
                )

            try:
                result = await self._execute_tool(name, arguments)
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text=self._format_result(result)
                    )],
                    isError=not result.get("success", False)
                )
            except Exception as e:
                logger.error(f"Tool execution error: {e}", exc_info=True)
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text=f"エラーが発生しました: {str(e)}"
                    )],
                    isError=True
                )

        @self.server.list_prompts()
        async def list_prompts() -> list[Prompt]:
            """利用可能なプロンプト一覧を返す"""
            return [
                Prompt(
                    name="parking_query",
                    description="駐車場に関する質問を処理するためのプロンプト",
                    arguments=[
                        PromptArgument(
                            name="question",
                            description="駐車場に関する質問",
                            required=True
                        ),
                        PromptArgument(
                            name="parking_name",
                            description="対象の駐車場名（分かっている場合）",
                            required=False
                        )
                    ]
                )
            ]

        @self.server.get_prompt()
        async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
            """プロンプトを取得"""
            if name != "parking_query":
                raise ValueError(f"Unknown prompt: {name}")

            question = arguments.get("question", "") if arguments else ""
            parking_name = arguments.get("parking_name", "") if arguments else ""

            # スキーマコンテキストを取得
            schema_context = ""
            if self.schema:
                schema_context = self.schema.get_full_context()

            system_message = f"""あなたは駐車場管理システムの運用支援AIです。

## 役割
- ユーザーの質問に対して、データベースを参照して正確に回答します
- 回答は日本語で、業務担当者にわかりやすく説明します

## 制約
- 読み取り専用（SELECT のみ）
- 可能な限り特定の駐車場にスコープを絞る
- 曖昧な場合は確認質問をする

## スキーマコンテキスト
{schema_context}

## 回答スタイル
- 明確で簡潔
- 値がデフォルトか例外かを明示
- 推測が含まれる場合は注意書きを入れる
"""

            user_message = question
            if parking_name:
                user_message = f"【対象駐車場: {parking_name}】\n{question}"

            return GetPromptResult(
                messages=[
                    PromptMessage(role="user", content=TextContent(type="text", text=system_message)),
                    PromptMessage(role="user", content=TextContent(type="text", text=user_message))
                ]
            )

    async def _execute_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        """ツールを実行して結果を返す"""
        if name == "search_parking":
            result = await self.tools.search_parking(
                query=arguments.get("query", ""),
                search_type=arguments.get("search_type", "name")
            )
        elif name == "get_parking_config":
            result = await self.tools.get_parking_config(
                parking_id=arguments.get("parking_id")
            )
        elif name == "get_night_rate_config":
            result = await self.tools.get_night_rate_config(
                parking_id=arguments.get("parking_id")
            )
        elif name == "execute_readonly_sql":
            params = arguments.get("params")
            if params:
                params = tuple(params)
            result = await self.tools.execute_readonly_sql(
                query=arguments.get("query", ""),
                params=params
            )
        elif name == "get_schema_context":
            result = self.tools.get_schema_context(
                table_name=arguments.get("table_name")
            )
        elif name == "explain_term":
            result = self.tools.explain_term(
                term=arguments.get("term", "")
            )
        elif name == "suggest_approach":
            result = self.tools.suggest_approach(
                question=arguments.get("question", "")
            )
        elif name == "get_query_history":
            result = self.tools.get_query_history(
                limit=arguments.get("limit", 20),
                success_only=arguments.get("success_only", False),
                failed_only=arguments.get("failed_only", False),
                keyword=arguments.get("keyword")
            )
        elif name == "get_query_history_detail":
            result = self.tools.get_query_history_detail(
                history_id=arguments.get("history_id")
            )
        elif name == "get_query_statistics":
            result = self.tools.get_query_statistics()
        elif name == "clear_query_history":
            result = self.tools.clear_query_history()
        else:
            return {
                "success": False,
                "message": f"不明なツール: {name}"
            }

        return {
            "success": result.success,
            "data": result.data,
            "message": result.message,
            "context": result.context
        }

    def _format_result(self, result: dict) -> str:
        """結果をフォーマット"""
        lines = []

        if result.get("success"):
            lines.append(f"✓ {result.get('message', '成功')}")
        else:
            lines.append(f"✗ {result.get('message', 'エラー')}")

        if result.get("context"):
            lines.append("")
            lines.append("【補足情報】")
            lines.append(result["context"])

        if result.get("data"):
            lines.append("")
            lines.append("【データ】")
            if isinstance(result["data"], list):
                for i, item in enumerate(result["data"][:10], 1):  # 最大10件
                    lines.append(f"{i}. {json.dumps(item, ensure_ascii=False, default=str)}")
                if len(result["data"]) > 10:
                    lines.append(f"... 他 {len(result['data']) - 10} 件")
            elif isinstance(result["data"], dict):
                if "context" in result["data"]:
                    lines.append(result["data"]["context"])
                else:
                    lines.append(json.dumps(result["data"], ensure_ascii=False, indent=2, default=str))
            else:
                lines.append(str(result["data"]))

        return "\n".join(lines)

    async def initialize(self) -> None:
        """サーバーを初期化"""
        logger.info("Initializing MCP Parking Server...")

        # データベース接続
        config = DatabaseConfig.from_env()
        self.db = ReadOnlyDatabase(config)
        await self.db.connect()
        logger.info("Database connected")

        # スキーマコンテキスト読み込み
        if SCHEMA_CONTEXT_PATH.exists():
            self.schema = SchemaContext(SCHEMA_CONTEXT_PATH)
            logger.info("Schema context loaded")
        else:
            logger.warning(f"Schema context file not found: {SCHEMA_CONTEXT_PATH}")
            self.schema = SchemaContext()

        # ツール初期化
        self.tools = ParkingTools(self.db, self.schema)
        logger.info("Tools initialized")

    async def cleanup(self) -> None:
        """リソースをクリーンアップ"""
        if self.db:
            await self.db.disconnect()
            logger.info("Database disconnected")

    async def run(self) -> None:
        """サーバーを実行"""
        await self.initialize()

        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
        finally:
            await self.cleanup()


def main():
    """エントリーポイント"""
    server = ParkingMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
