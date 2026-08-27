"""Manage provenance-preserving FinMind source-repair overlays."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.domain import HistoricalBar  # noqa: E402
from backtest.finmind_source_repair import (  # noqa: E402
    FinMindSourceRepairStore,
)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("datetime must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone")
    return parsed


def _bars(path: Path) -> tuple[HistoricalBar, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("bars file must contain a JSON array")
    if any(not isinstance(row, dict) for row in value):
        raise ValueError("bars file contains a non-object row")
    return tuple(HistoricalBar.from_dict(row) for row in value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "建立、審核或啟用 FinMind source-repair overlay；"
            "不覆寫原始 FinMind partition"
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/finmind_sponsor/history.sqlite3"),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    open_case = subcommands.add_parser(
        "open-case", help="以日級或其他差異證據隔離一個 EMPTY/INVALID partition"
    )
    open_case.add_argument("--job-id", required=True)
    open_case.add_argument("--symbol", required=True)
    open_case.add_argument("--session-date", type=_date, required=True)
    open_case.add_argument("--reason-code", required=True)
    open_case.add_argument("--evidence-kind", required=True)
    open_case.add_argument("--source-name", required=True)
    open_case.add_argument("--source-uri", required=True)
    open_case.add_argument("--observed-at", type=_datetime, required=True)
    open_case.add_argument("--evidence-file", type=Path, required=True)

    propose = subcommands.add_parser(
        "propose-minute", help="加入含明確分鐘時間的替代來源候選"
    )
    propose.add_argument("--case-id", required=True)
    propose.add_argument("--evidence-kind", default="ALTERNATE_MINUTE_BARS")
    propose.add_argument("--source-name", required=True)
    propose.add_argument("--source-uri", required=True)
    propose.add_argument("--observed-at", type=_datetime, required=True)
    propose.add_argument("--evidence-file", type=Path, required=True)
    propose.add_argument("--bars-file", type=Path, required=True)

    review = subcommands.add_parser(
        "review", help="核准或拒絕一個 minute-level candidate"
    )
    review.add_argument("--case-id", required=True)
    review.add_argument("--evidence-id", required=True)
    review.add_argument("--decision", choices=("APPROVE", "REJECT"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--rationale", required=True)

    activate = subcommands.add_parser(
        "activate", help="依明確 approval 啟用 overlay；原始 partition 保持不變"
    )
    activate.add_argument("--case-id", required=True)
    activate.add_argument("--review-id", required=True)
    activate.add_argument("--actor", required=True)
    activate.add_argument("--change-note", required=True)

    status = subcommands.add_parser("status", help="查看單一 repair case")
    status.add_argument("--case-id", required=True)
    subcommands.add_parser("audit", help="離線驗證所有 repair lineage 與 digest")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    database = args.database
    if not database.is_absolute():
        database = PROJECT_ROOT / database
    store = FinMindSourceRepairStore(database)
    try:
        if args.command == "open-case":
            result = store.open_case(
                job_id=args.job_id,
                symbol=args.symbol,
                session_date=args.session_date,
                reason_code=args.reason_code,
                evidence_kind=args.evidence_kind,
                source_name=args.source_name,
                source_uri=args.source_uri,
                observed_at=args.observed_at,
                evidence_body=args.evidence_file.read_bytes(),
            )
        elif args.command == "propose-minute":
            result = store.propose_minute_evidence(
                case_id=args.case_id,
                evidence_kind=args.evidence_kind,
                source_name=args.source_name,
                source_uri=args.source_uri,
                observed_at=args.observed_at,
                evidence_body=args.evidence_file.read_bytes(),
                bars=_bars(args.bars_file),
            )
        elif args.command == "review":
            result = store.review(
                case_id=args.case_id,
                evidence_id=args.evidence_id,
                decision=args.decision,
                reviewer=args.reviewer,
                rationale=args.rationale,
            )
        elif args.command == "activate":
            result = store.activate(
                case_id=args.case_id,
                review_id=args.review_id,
                actor=args.actor,
                change_note=args.change_note,
            )
        elif args.command == "status":
            result = store.case_status(args.case_id)
        else:
            result = store.audit()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
