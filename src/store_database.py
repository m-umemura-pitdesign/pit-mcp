"""
店舗DB接続モジュール
各店舗のWebDBサーバー（stores.domain/port）への動的接続を提供（読み取り専用）
"""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import aiomysql
from dotenv import load_dotenv

load_dotenv()


@dataclass
class StoreDBConfig:
    """店舗DB接続設定"""
    address: str
    port: int
    user: str
    password: str
    database: str
    connect_timeout: int = 30
    query_timeout: int = 30


class StoreDBError(Exception):
    """店舗DB接続エラー"""
    pass


class StoreDatabase:
    """
    店舗DB接続クラス（読み取り専用）

    各店舗のWebDBサーバー（stores.domain/port）に動的接続し、
    入出庫履歴（tbl_in_out_mgr）などを取得する。

    セキュリティ機能:
    - 読み取り専用トランザクション
    - 接続タイムアウト
    - クエリタイムアウト
    """

    def __init__(self, config: StoreDBConfig):
        self.config = config
        self._conn: aiomysql.Connection | None = None

    @classmethod
    async def connect(
        cls,
        address: str,
        port: int,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None
    ) -> "StoreDatabase":
        """
        店舗DBに接続

        Args:
            address: サーバーアドレス
            port: ポート番号
            user: ユーザー名（省略時は環境変数 STORE_DB_USER）
            password: パスワード（省略時は環境変数 STORE_DB_PASSWORD）
            database: DB名（省略時は環境変数 STORE_DB_NAME または smartparkdb_phase3）

        Returns:
            StoreDatabase: 接続済みインスタンス
        """
        config = StoreDBConfig(
            address=address,
            port=port,
            user=user or os.getenv("STORE_DB_USER", "readonly_user"),
            password=password or os.getenv("STORE_DB_PASSWORD", ""),
            database=database or os.getenv("STORE_DB_NAME", "smartparkdb_phase3"),
        )

        instance = cls(config)
        await instance._connect()
        return instance

    async def _connect(self) -> None:
        """内部接続処理"""
        try:
            self._conn = await asyncio.wait_for(
                aiomysql.connect(
                    host=self.config.address,
                    port=self.config.port,
                    user=self.config.user,
                    password=self.config.password,
                    db=self.config.database,
                    connect_timeout=self.config.connect_timeout,
                    autocommit=True,
                    cursorclass=aiomysql.DictCursor,
                ),
                timeout=self.config.connect_timeout
            )

            # 読み取り専用トランザクションを設定
            async with self._conn.cursor() as cursor:
                await cursor.execute("SET SESSION TRANSACTION READ ONLY")

        except asyncio.TimeoutError:
            raise StoreDBError(
                f"店舗DB接続タイムアウト: {self.config.address}:{self.config.port}"
            )
        except Exception as e:
            raise StoreDBError(
                f"店舗DB接続エラー ({self.config.address}:{self.config.port}): {e}"
            )

    async def disconnect(self) -> None:
        """接続をクローズ"""
        if self._conn:
            self._conn.close()
            self._conn = None

    async def get_entry_exit_history(
        self,
        parking_id: int | None = None,
        car_number: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        入出庫履歴を取得

        Args:
            parking_id: 駐車場ID（フィルタ）
            car_number: 車両番号（部分一致フィルタ）
            date_from: 開始日（YYYY-MM-DD形式）
            date_to: 終了日（YYYY-MM-DD形式）
            limit: 取得件数上限（最大1000）

        Returns:
            list[dict]: 入出庫履歴リスト
        """
        if not self._conn:
            raise StoreDBError("店舗DBに接続されていません")

        # LIMIT制限
        limit = min(max(1, limit), 1000)

        # クエリ構築
        query = """
            SELECT
                INOUT_NO,
                ENTRANT_NO,
                ENTRANT_DTE,
                PARKING_ID,
                ENTRANT_TIME,
                EXIT_TIME,
                VEHICLE_STATUS_ID,
                CHECKOUT_FLG,
                PLACE,
                CLASS_NUMBER,
                KANA,
                CAR_NUMBER
            FROM tbl_in_out_mgr
            WHERE 1=1
        """
        params: list[Any] = []

        if parking_id is not None:
            query += " AND PARKING_ID = %s"
            params.append(parking_id)

        if car_number:
            query += " AND CAR_NUMBER LIKE %s"
            params.append(f"%{car_number}%")

        if date_from:
            query += " AND ENTRANT_DTE >= %s"
            params.append(date_from)

        if date_to:
            query += " AND ENTRANT_DTE <= %s"
            params.append(date_to)

        query += " ORDER BY ENTRANT_TIME DESC LIMIT %s"
        params.append(limit)

        try:
            async with self._conn.cursor() as cursor:
                await asyncio.wait_for(
                    cursor.execute(query, tuple(params)),
                    timeout=self.config.query_timeout
                )
                rows = await cursor.fetchall()
                return list(rows)

        except asyncio.TimeoutError:
            raise StoreDBError(
                f"クエリタイムアウト（{self.config.query_timeout}秒）"
            )
        except Exception as e:
            raise StoreDBError(f"クエリ実行エラー: {e}")

    async def __aenter__(self) -> "StoreDatabase":
        """async with 対応"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """async with 終了時に自動クローズ"""
        await self.disconnect()
