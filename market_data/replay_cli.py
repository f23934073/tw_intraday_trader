"""CLI entry point for canonical market-event journal verification."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from market_data.exact_replay import verify_exact_projection_replay
from market_data.journal import verify_market_event_journal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a finalized market-event journal before deterministic replay"
        )
    )
    parser.add_argument(
        "--session",
        required=True,
        type=Path,
        help="Session directory containing records.jsonl and manifest.json",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify integrity, schema, row order, and disposition links",
    )
    parser.add_argument(
        "--bootstrap",
        type=Path,
        help="Finalized bootstrap-snapshot-v1 artifact for exact replay",
    )
    parser.add_argument(
        "--instrument-reference",
        type=Path,
        help="Finalized instrument-reference-v1 artifact for exact replay",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.verify:
        print("error: this P1.1 slice currently supports --verify only")
        return 2

    result = verify_market_event_journal(args.session)
    print("verification: journal-integrity-v1")
    print(f"events: {result.event_count}")
    print(f"records: {result.record_count}")
    print(f"accepted: {result.accepted_count}")
    print(f"rejected: {result.rejected_count}")
    print(f"incidents: {result.incident_count}")
    print(f"sha256: {result.calculated_sha256 or 'unavailable'}")
    print(f"match: {'true' if result.valid else 'false'}")
    for error in result.errors:
        print(f"error: {error}")
    if not result.valid:
        return 1

    exact_requested = (
        args.bootstrap is not None or args.instrument_reference is not None
    )
    if not exact_requested:
        print("projection_replay: pending-complete-reference-contract")
        return 0
    if args.bootstrap is None:
        print("projection_replay: FAILED")
        print("error: MISSING_BOOTSTRAP_ARTIFACT: --bootstrap is required")
        return 1
    if args.instrument_reference is None:
        print("projection_replay: FAILED")
        print(
            "error: MISSING_REFERENCE_ARTIFACT: "
            "--instrument-reference is required"
        )
        return 1

    exact = verify_exact_projection_replay(
        session_dir=args.session,
        bootstrap_path=args.bootstrap,
        instrument_reference_path=args.instrument_reference,
    )
    print(f"projection_replay: {'PASS' if exact.valid else 'FAILED'}")
    for comparison in exact.comparisons:
        print(f"{comparison.name}: {'MATCH' if comparison.match else 'MISMATCH'}")
        if not comparison.match:
            print(f"expected: {comparison.expected}")
            print(f"actual: {comparison.actual}")
            print(f"first_divergence: {comparison.first_divergence}")
    for error in exact.errors:
        print(f"error: {error}")
    return 0 if exact.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
