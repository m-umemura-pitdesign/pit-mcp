"""
データベース接続モジュール
MySQL/Aurora への安全な読み取り専用接続を提供
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import aiomysql
from dotenv import load_dotenv

from .sql_validator import validate_sql, ValidationError, RiskLevel
from .query_history import QueryHistory

load_dotenv()


@dataclass
class DatabaseConfig:
    """データベース接続設定"""
    host: str
    port: int
    user: str
    password: str
    database: str
    # 読み取り専用接続の設定
    read_only: bool = True
    # 接続プール設定
    pool_min_size: int = 1
    pool_max_size: int = 5
    # タイムアウト設定（秒）
    connect_timeout: int = 10
    query_timeout: int = 30

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """環境変数から設定を読み込む"""
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "readonly_user"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "parking_system"),
            read_only=os.getenv("DB_READ_ONLY", "true").lower() == "true",
            pool_min_size=int(os.getenv("DB_POOL_MIN", "1")),
            pool_max_size=int(os.getenv("DB_POOL_MAX", "5")),
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
            query_timeout=int(os.getenv("DB_QUERY_TIMEOUT", "30")),
        )


@dataclass
class QueryResult:
    """クエリ実行結果"""
    success: bool
    data: list[dict[str, Any]] | None
    row_count: int
    message: str
    executed_query: str | None = None


class DatabaseError(Exception):
    """データベースエラー"""
    pass


class ReadOnlyDatabase:
    """
    読み取り専用データベース接続クラス

    セキュリティ機能:
    - SQLバリデーション（SELECT のみ許可）
    - クエリタイムアウト
    - 接続プール管理
    - 読み取り専用トランザクション
    - クエリ履歴の記録
    """

    def __init__(self, config: DatabaseConfig, history: QueryHistory | None = None):
        self.config = config
        self._pool: aiomysql.Pool | None = None
        self.history = history or QueryHistory()

    async def connect(self) -> None:
        """接続プールを初期化"""
        if self._pool is not None:
            return

        try:
            self._pool = await aiomysql.create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                db=self.config.database,
                minsize=self.config.pool_min_size,
                maxsize=self.config.pool_max_size,
                connect_timeout=self.config.connect_timeout,
                autocommit=True,  # 読み取り専用なので autocommit
                cursorclass=aiomysql.DictCursor,
            )
        except Exception as e:
            raise DatabaseError(f"データベース接続に失敗しました: {e}")

    async def disconnect(self) -> None:
        """接続プールをクローズ"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    @asynccontextmanager
    async def get_connection(self):
        """接続を取得するコンテキストマネージャー"""
        if self._pool is None:
            await self.connect()

        async with self._pool.acquire() as conn:
            # 読み取り専用トランザクションを設定
            if self.config.read_only:
                async with conn.cursor() as cur:
                    await cur.execute("SET SESSION TRANSACTION READ ONLY")
            yield conn

    async def execute_query(
        self,
        query: str,
        params: tuple | None = None,
        validate: bool = True,
        tool_name: str | None = None
    ) -> QueryResult:
        """
        読み取り専用クエリを実行

        Args:
            query: 実行するSQLクエリ
            params: クエリパラメータ（プレースホルダー用）
            validate: SQLバリデーションを行うか
            tool_name: 呼び出し元ツール名（履歴記録用）

        Returns:
            QueryResult: クエリ実行結果
        """
        start_time = time.time()

        # 1. SQLバリデーション
        if validate:
            validation = validate_sql(query)
            if not validation.is_valid:
                execution_time_ms = (time.time() - start_time) * 1000
                error_msg = f"クエリが拒否されました: {validation.message}"

                # 履歴に記録（バリデーション失敗）
                self.history.add(
                    query=query,
                    params=list(params) if params else None,
                    success=False,
                    row_count=0,
                    execution_time_ms=execution_time_ms,
                    error_message=error_msg,
                    tool_name=tool_name
                )

                return QueryResult(
                    success=False,
                    data=None,
                    row_count=0,
                    message=error_msg
                )
            # サニタイズされたクエリを使用
            query = validation.sanitized_query or query

        # 2. クエリ実行
        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cursor:
                    # タイムアウト設定
                    await asyncio.wait_for(
                        cursor.execute(query, params),
                        timeout=self.config.query_timeout
                    )
                    rows = await cursor.fetchall()

                    execution_time_ms = (time.time() - start_time) * 1000

                    # 履歴に記録（成功）
                    self.history.add(
                        query=query,
                        params=list(params) if params else None,
                        success=True,
                        row_count=len(rows),
                        execution_time_ms=execution_time_ms,
                        tool_name=tool_name
                    )

                    return QueryResult(
                        success=True,
                        data=list(rows),
                        row_count=len(rows),
                        message=f"{len(rows)}件の結果を取得しました",
                        executed_query=query
                    )

        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            error_msg = f"クエリがタイムアウトしました（{self.config.query_timeout}秒）"

            self.history.add(
                query=query,
                params=list(params) if params else None,
                success=False,
                row_count=0,
                execution_time_ms=execution_time_ms,
                error_message=error_msg,
                tool_name=tool_name
            )

            return QueryResult(
                success=False,
                data=None,
                row_count=0,
                message=error_msg
            )
        except aiomysql.Error as e:
            execution_time_ms = (time.time() - start_time) * 1000
            error_msg = f"データベースエラー: {e}"

            self.history.add(
                query=query,
                params=list(params) if params else None,
                success=False,
                row_count=0,
                execution_time_ms=execution_time_ms,
                error_message=error_msg,
                tool_name=tool_name
            )

            return QueryResult(
                success=False,
                data=None,
                row_count=0,
                message=error_msg
            )
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            error_msg = f"予期しないエラー: {e}"

            self.history.add(
                query=query,
                params=list(params) if params else None,
                success=False,
                row_count=0,
                execution_time_ms=execution_time_ms,
                error_message=error_msg,
                tool_name=tool_name
            )

            return QueryResult(
                success=False,
                data=None,
                row_count=0,
                message=error_msg
            )

    async def find_parking_by_name(self, name: str) -> QueryResult:
        """
        駐車場名で検索（部分一致）

        Args:
            name: 検索する駐車場名

        Returns:
            QueryResult: 検索結果
        """
        query = """
            SELECT id, name, code, address, status
            FROM parkings
            WHERE name LIKE %s
            LIMIT 10
        """
        return await self.execute_query(query, (f"%{name}%",))

    async def find_parking_by_code(self, code: str) -> QueryResult:
        """
        駐車場コードで検索（完全一致）

        Args:
            code: 検索する駐車場コード

        Returns:
            QueryResult: 検索結果
        """
        query = """
            SELECT id, name, code, address, status
            FROM parkings
            WHERE code = %s
            LIMIT 1
        """
        return await self.execute_query(query, (code,))

    async def get_parking_config(self, parking_id: int) -> QueryResult:
        """
        駐車場の設定を取得

        Args:
            parking_id: 駐車場ID

        Returns:
            QueryResult: 設定情報
        """
        query = """
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
            WHERE pc.parking_id = %s
            LIMIT 1
        """
        return await self.execute_query(query, (parking_id,))

    async def get_night_rate_config(self, parking_id: int) -> QueryResult:
        """
        夜間料金設定を取得

        Args:
            parking_id: 駐車場ID

        Returns:
            QueryResult: 夜間料金設定
        """
        query = """
            SELECT
                p.name as parking_name,
                pc.night_rate_enabled,
                pc.night_rate_start_time,
                pc.night_rate_end_time,
                pc.night_rate_amount,
                pc.max_daily_charge
            FROM parking_configs pc
            JOIN parkings p ON pc.parking_id = p.id
            WHERE pc.parking_id = %s
            LIMIT 1
        """
        return await self.execute_query(query, (parking_id,))
