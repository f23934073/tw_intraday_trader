"""Run a bounded, data-only Tick/BidAsk freshness evidence capture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_data.freshness_calibration import run_live_quote_freshness_capture


def _symbol_tiers(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        symbol, separator, tier = value.partition(":")
        if not separator or not symbol.strip() or not tier.strip():
            raise argparse.ArgumentTypeError(
                "--symbol must use SYMBOL:LIQUIDITY_TIER, for example 2330:high"
            )
        result[symbol.strip().upper()] = tier.strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        help="repeatable SYMBOL:LIQUIDITY_TIER label; labels are reviewer supplied",
    )
    parser.add_argument(
        "--session-window",
        required=True,
        help="reviewer-supplied capture label such as open, continuous, or close",
    )
    parser.add_argument("--duration-seconds", type=int, default=900)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("research/captures/freshness_quote"),
    )
    args = parser.parse_args()
    artifact, report = run_live_quote_freshness_capture(
        symbol_tiers=_symbol_tiers(args.symbol),
        session_window=args.session_window,
        duration_seconds=args.duration_seconds,
        output_directory=args.output_directory,
    )
    print(json.dumps({"artifact": str(artifact), "review": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
