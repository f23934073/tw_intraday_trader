"""Durable local-development SQLite adapter for historical backtests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backtest.repository import _JsonBacktestRepository


class SQLiteBacktestRepository(_JsonBacktestRepository):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        super().__init__(connection, placeholder="?", json_type="TEXT", blob_type="BLOB")
