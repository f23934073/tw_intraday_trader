#!/usr/bin/env python3
"""Capture one real-time, evidence-only no-overnight DISABLED baseline."""

from __future__ import annotations

import argparse
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
_CAPTURE_COMMON_PATH = PROJECT_ROOT / "scripts" / "no_overnight_capture_common.py"
_CAPTURE_COMMON_SPEC = spec_from_file_location(
    "_no_overnight_capture_common",
    _CAPTURE_COMMON_PATH,
)
if _CAPTURE_COMMON_SPEC is None or _CAPTURE_COMMON_SPEC.loader is None:
    raise RuntimeError("cannot load repository-owned capture helper")
_CAPTURE_COMMON = module_from_spec(_CAPTURE_COMMON_SPEC)
_CAPTURE_COMMON_SPEC.loader.exec_module(_CAPTURE_COMMON)
_active_settings_from_file = _CAPTURE_COMMON._active_settings_from_file
_code_identity = _CAPTURE_COMMON._code_identity
_environment_from_file = _CAPTURE_COMMON._environment_from_file


from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from market_data.provider import MockProvider
from runtime.clock import SystemClock
from runtime.composition import RuntimeComposition
from runtime.no_overnight_evidence_capture import capture_disabled_baseline
from runtime.trading_persistence import build_journal_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--session-date", required=True, type=date.fromisoformat)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--settings-file", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    persistence = TradingPersistenceConfig.from_environment(
        _environment_from_file(args.env_file)
    )
    if persistence.backend is not TradingJournalBackend.POSTGRESQL:
        raise ValueError("operational baseline requires the PostgreSQL Journal")

    code_identity = _code_identity()
    settings_file = args.settings_file
    _active_settings_from_file(settings_file)
    provider = MockProvider()
    report = capture_disabled_baseline(
        campaign_id=args.campaign_id,
        session_date=args.session_date,
        code_identity=code_identity,
        artifact_root=args.artifact_root,
        marker_journal_factory=lambda: build_journal_repository(persistence),
        provider=provider,
        clock=SystemClock(),
        runtime_factory=lambda **values: RuntimeComposition.create(
            **values,
            persistence_config=persistence,
        ),
        active_settings_reader=lambda: _active_settings_from_file(
            settings_file
        ),
    )
    print(
        json.dumps(
            report.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
