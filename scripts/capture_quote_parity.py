"""CLI for a bounded, data-only Shioaji Quote parity capture."""

from __future__ import annotations

import argparse
from pathlib import Path

from market_data.shioaji_quote_capture import run_live_quote_capture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="8039")
    parser.add_argument("--duration-seconds", type=int, default=20)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("research/captures/quote_parity"),
    )
    args = parser.parse_args()

    output_path, report = run_live_quote_capture(
        symbol=args.symbol,
        duration_seconds=args.duration_seconds,
        output_directory=args.output_directory,
    )
    print(f"capture={output_path}")
    print(f"preliminary_status={report.status.value}")
    print(f"incomplete_reasons={','.join(report.incomplete_reasons)}")


if __name__ == "__main__":
    main()
