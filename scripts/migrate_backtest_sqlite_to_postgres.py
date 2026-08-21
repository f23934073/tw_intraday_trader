"""Copy the Backtest SQLite authority into PostgreSQL and verify exact parity."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from backtest.sqlite_postgres_migration import migrate_sqlite_to_postgres


def _postgres_dsn(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    for name in (
        "BACKTEST_DATABASE_URL",
        "DATABASE_URL",
        "POSTGRESQL_DSN",
        "PostgreSQL_DSN",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise ValueError(
        "請設定 --postgres-dsn、BACKTEST_DATABASE_URL 或共用 PostgreSQL DSN"
    )


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description=(
            "唯讀 SQLite、可重跑地複製到 PostgreSQL backtest schema，"
            "並在逐表筆數與內容 digest 全部一致後回報成功"
        )
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=PROJECT_ROOT / "data/backtest/backtest.sqlite3",
        help="來源 SQLite；只會以唯讀模式開啟",
    )
    parser.add_argument(
        "--postgres-dsn",
        help="目的 PostgreSQL DSN；省略時讀取環境設定（輸出不會包含 DSN）",
    )
    parser.add_argument(
        "--stale-minutes",
        type=int,
        default=30,
        help="超過此時間未更新的 RUNNING job 在目的端轉為 PAUSED",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="每次 PostgreSQL transaction 的最大列數",
    )
    args = parser.parse_args()

    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "執行搬遷前請安裝 tw-intraday-trader[postgres]"
        ) from error

    connection = psycopg.connect(_postgres_dsn(args.postgres_dsn))
    try:
        report = migrate_sqlite_to_postgres(
            sqlite_path=args.sqlite,
            postgres_connection=connection,
            stale_minutes=args.stale_minutes,
            batch_size=args.batch_size,
            report_progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
    finally:
        connection.close()
    print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
