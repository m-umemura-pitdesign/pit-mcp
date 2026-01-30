"""
クエリ履歴モジュール
実行されたSQLクエリの履歴を管理
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class QueryHistoryEntry:
    """クエリ履歴エントリ"""
    id: int
    timestamp: str
    query: str
    params: list[Any] | None
    success: bool
    row_count: int
    execution_time_ms: float
    error_message: str | None = None
    tool_name: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QueryHistoryEntry":
        return cls(**data)


class QueryHistory:
    """
    クエリ履歴管理クラス

    機能:
    - クエリ実行履歴の記録
    - 履歴のJSONファイル永続化
    - 履歴の検索・取得
    - 履歴のクリア
    """

    def __init__(self, history_file: str | Path | None = None, max_entries: int = 1000):
        """
        Args:
            history_file: 履歴ファイルのパス（省略時はdata/query_history.json）
            max_entries: 保持する最大エントリ数
        """
        if history_file is None:
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            self.history_file = data_dir / "query_history.json"
        else:
            self.history_file = Path(history_file)
            self.history_file.parent.mkdir(parents=True, exist_ok=True)

        self.max_entries = max_entries
        self._entries: list[QueryHistoryEntry] = []
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        """履歴ファイルから読み込み"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._entries = [
                        QueryHistoryEntry.from_dict(entry)
                        for entry in data.get("entries", [])
                    ]
                    self._next_id = data.get("next_id", 1)
            except (json.JSONDecodeError, KeyError) as e:
                # ファイルが壊れている場合は初期化
                self._entries = []
                self._next_id = 1

    def _save(self) -> None:
        """履歴ファイルに保存"""
        data = {
            "next_id": self._next_id,
            "entries": [entry.to_dict() for entry in self._entries]
        }
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(data, ensure_ascii=False, indent=2, fp=f)

    def add(
        self,
        query: str,
        params: list[Any] | None,
        success: bool,
        row_count: int,
        execution_time_ms: float,
        error_message: str | None = None,
        tool_name: str | None = None
    ) -> QueryHistoryEntry:
        """
        クエリ履歴を追加

        Args:
            query: 実行されたSQLクエリ
            params: クエリパラメータ
            success: 成功したか
            row_count: 結果の行数
            execution_time_ms: 実行時間（ミリ秒）
            error_message: エラーメッセージ（失敗時）
            tool_name: 呼び出し元ツール名

        Returns:
            QueryHistoryEntry: 追加されたエントリ
        """
        entry = QueryHistoryEntry(
            id=self._next_id,
            timestamp=datetime.now().isoformat(),
            query=query,
            params=list(params) if params else None,
            success=success,
            row_count=row_count,
            execution_time_ms=round(execution_time_ms, 2),
            error_message=error_message,
            tool_name=tool_name
        )

        self._entries.append(entry)
        self._next_id += 1

        # 最大エントリ数を超えた場合、古いものを削除
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

        self._save()
        return entry

    def get_all(self, limit: int = 100, offset: int = 0) -> list[QueryHistoryEntry]:
        """
        全履歴を取得（新しい順）

        Args:
            limit: 取得件数
            offset: オフセット

        Returns:
            list[QueryHistoryEntry]: 履歴リスト
        """
        sorted_entries = sorted(self._entries, key=lambda e: e.id, reverse=True)
        return sorted_entries[offset:offset + limit]

    def get_by_id(self, entry_id: int) -> QueryHistoryEntry | None:
        """IDで履歴を取得"""
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def search(
        self,
        keyword: str | None = None,
        success_only: bool = False,
        failed_only: bool = False,
        tool_name: str | None = None,
        limit: int = 100
    ) -> list[QueryHistoryEntry]:
        """
        履歴を検索

        Args:
            keyword: クエリに含まれるキーワード
            success_only: 成功したクエリのみ
            failed_only: 失敗したクエリのみ
            tool_name: ツール名でフィルタ
            limit: 取得件数

        Returns:
            list[QueryHistoryEntry]: 検索結果
        """
        results = []

        for entry in sorted(self._entries, key=lambda e: e.id, reverse=True):
            if keyword and keyword.lower() not in entry.query.lower():
                continue
            if success_only and not entry.success:
                continue
            if failed_only and entry.success:
                continue
            if tool_name and entry.tool_name != tool_name:
                continue

            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def get_statistics(self) -> dict:
        """
        履歴の統計情報を取得

        Returns:
            dict: 統計情報
        """
        if not self._entries:
            return {
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "success_rate": 0,
                "avg_execution_time_ms": 0,
                "total_rows_returned": 0
            }

        success_count = sum(1 for e in self._entries if e.success)
        failed_count = len(self._entries) - success_count
        total_time = sum(e.execution_time_ms for e in self._entries)
        total_rows = sum(e.row_count for e in self._entries if e.success)

        return {
            "total_count": len(self._entries),
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": round(success_count / len(self._entries) * 100, 1),
            "avg_execution_time_ms": round(total_time / len(self._entries), 2),
            "total_rows_returned": total_rows
        }

    def clear(self) -> int:
        """
        全履歴をクリア

        Returns:
            int: 削除された件数
        """
        count = len(self._entries)
        self._entries = []
        self._next_id = 1
        self._save()
        return count

    def export_to_json(self) -> str:
        """履歴をJSON文字列としてエクスポート"""
        return json.dumps(
            [entry.to_dict() for entry in self._entries],
            ensure_ascii=False,
            indent=2
        )

    def get_recent_queries(self, count: int = 10) -> list[str]:
        """最近のクエリ文字列のみを取得"""
        recent = self.get_all(limit=count)
        return [entry.query for entry in recent]
