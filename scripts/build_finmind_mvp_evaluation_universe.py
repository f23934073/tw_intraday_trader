"""Build the offline FinMind MVP coverage audit and covered evaluation universe."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.finmind_snapshot import FinMindSnapshotPlan  # noqa: E402
from config import twse_calendar_2026  # noqa: E402
from config.institutional_mvp import (  # noqa: E402
    DEFAULT_CANDIDATE_SERIES,
    DEFAULT_CANDIDATE_SERIES_PLAN,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PRICE_DATASET_MANIFEST,
    DEFAULT_PRICE_DATASET_PLAN,
    load_daily_policy,
)
from institutional_data.serialization import canonical_json, sha256_text  # noqa: E402
from institutional_mvp.evaluation import (  # noqa: E402
    InstitutionalMvpEvaluationError,
    build_mvp_evaluation_universe,
    build_mvp_price_coverage_audit,
    verify_mvp_evaluation_universe,
    verify_mvp_price_coverage_audit,
)
from institutional_mvp.series import (  # noqa: E402
    InstitutionalMvpSeriesError,
    load_canonical_artifact,
    publish_content_addressed_json,
    verify_candidate_series_manifest,
    verify_candidate_series_plan,
)
from market_data.equity_calendar import ReviewedEquityCalendar  # noqa: E402
from scripts.run_finmind_institutional_mvp_series import (  # noqa: E402
    load_price_dataset_reference,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--dataset-manifest", type=Path, default=DEFAULT_PRICE_DATASET_MANIFEST
    )
    parser.add_argument("--dataset-plan", type=Path, default=DEFAULT_PRICE_DATASET_PLAN)
    parser.add_argument(
        "--candidate-series-plan", type=Path, default=DEFAULT_CANDIDATE_SERIES_PLAN
    )
    parser.add_argument("--candidate-series", type=Path, default=DEFAULT_CANDIDATE_SERIES)
    args = parser.parse_args(argv)

    try:
        price_reference = load_price_dataset_reference(
            manifest_path=args.dataset_manifest,
            dataset_plan_path=args.dataset_plan,
        )
        snapshot_raw = json.loads(args.dataset_plan.read_bytes())
        if not isinstance(snapshot_raw, Mapping):
            raise ValueError("Dataset snapshot plan must be one object")
        snapshot_plan = FinMindSnapshotPlan.from_dict(snapshot_raw)
        calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
        policy = load_daily_policy()
        series_plan = load_canonical_artifact(args.candidate_series_plan)
        verify_candidate_series_plan(
            series_plan,
            calendar=calendar,
            policy=policy,
            price_dataset_reference=price_reference,
        )
        candidate_series = load_canonical_artifact(args.candidate_series)
        batches = _load_exact_batches(args.output_root, candidate_series)
        verify_candidate_series_manifest(
            candidate_series,
            plan=series_plan,
            batches=batches,
            calendar=calendar,
            policy=policy,
        )
        coverage = build_mvp_price_coverage_audit(
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=candidate_series,
        )
        verify_mvp_price_coverage_audit(
            coverage,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=candidate_series,
        )
        coverage_path, coverage_created = publish_content_addressed_json(
            args.output_root, category="coverage_audits", payload=coverage
        )
        if coverage["execution_permissions"][
            "mvp_evaluation_universe_freeze_allowed"
        ] is not True:
            print(
                f"status=BLOCKED coverage_digest={coverage['artifact_digest']} "
                f"coverage_path={coverage_path}"
            )
            return 75
        universe = build_mvp_evaluation_universe(
            coverage_audit=coverage,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=candidate_series,
        )
        verify_mvp_evaluation_universe(
            universe,
            coverage_audit=coverage,
            price_dataset_reference=price_reference,
            snapshot_plan=snapshot_plan,
            candidate_series=candidate_series,
        )
        universe_path, universe_created = publish_content_addressed_json(
            args.output_root,
            category="evaluation_universes",
            payload=universe,
        )
    except (
        InstitutionalMvpEvaluationError,
        InstitutionalMvpSeriesError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"ERROR code=MVP_EVALUATION_UNIVERSE_BUILD_FAILED "
            f"type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    status = (
        "IDEMPOTENT_REPLAY"
        if not coverage_created and not universe_created
        else "PUBLISHED"
    )
    print(
        f"status={status} coverage_digest={coverage['artifact_digest']} "
        f"universe_digest={universe['artifact_digest']} "
        f"membership_count={universe['membership_count']} "
        f"symbol_count={universe['symbol_count']} "
        f"target_session_count={universe['target_session_count']} "
        f"coverage_path={coverage_path} universe_path={universe_path}"
    )
    return 0


def _load_exact_batches(
    root: Path, candidate_series: Mapping[str, object]
) -> list[Mapping[str, object]]:
    references = candidate_series.get("batch_references")
    if not isinstance(references, list):
        raise ValueError("candidate series batch references are invalid")
    batches: list[Mapping[str, object]] = []
    _require_no_symlink_components(Path(root))
    root_descriptor = _open_directory_nofollow(Path(root))
    try:
        for reference in references:
            if not isinstance(reference, Mapping):
                raise ValueError("candidate series batch reference is invalid")
            target = _canonical_date(reference.get("target_session"), "target_session")
            source = _canonical_date(reference.get("source_session"), "source_session")
            digest = _canonical_digest(reference.get("artifact_digest"))
            target_descriptor = _open_directory_at(root_descriptor, target)
            try:
                source_descriptor = _open_directory_at(target_descriptor, source)
                try:
                    encoded = _read_regular_at(
                        source_descriptor, f"{digest}.json"
                    )
                finally:
                    os.close(source_descriptor)
            finally:
                os.close(target_descriptor)
            payload = json.loads(encoded)
            if not isinstance(payload, Mapping):
                raise ValueError("candidate batch artifact must be one object")
            if encoded != (canonical_json(payload) + "\n").encode("utf-8"):
                raise ValueError("candidate batch artifact is not canonical")
            identity = dict(payload)
            observed_digest = identity.pop("artifact_digest", None)
            observed_id = identity.pop("artifact_id", None)
            expected_digest = sha256_text(canonical_json(identity))
            if (
                observed_digest != digest
                or expected_digest != digest
                or observed_id
                != f"finmind-institutional-mvp-batch-v1-{target}-{digest[:16]}"
                or payload.get("source_session") != source
                or payload.get("target_session") != target
            ):
                raise ValueError("candidate batch artifact path lineage drifted")
            batches.append(payload)
    finally:
        os.close(root_descriptor)
    return batches


def _canonical_date(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(f"{field_name} must be a canonical ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a canonical ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be a canonical ISO date")
    return value


def _canonical_digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("artifact_digest must be lowercase SHA-256")
    return value


def _open_directory_nofollow(path: Path) -> int:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    _require_owned(descriptor, directory=True)
    return descriptor


def _open_directory_at(parent_descriptor: int, name: str) -> int:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=parent_descriptor,
    )
    _require_owned(descriptor, directory=True)
    return descriptor


def _read_regular_at(directory_descriptor: int, name: str) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=directory_descriptor,
    )
    with os.fdopen(descriptor, "rb") as artifact:
        _require_owned(artifact.fileno(), directory=False)
        return artifact.read()


def _require_owned(descriptor: int, *, directory: bool) -> None:
    metadata = os.fstat(descriptor)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise InstitutionalMvpSeriesError("candidate batch path is unsafe")
    if not directory and metadata.st_nlink != 1:
        raise InstitutionalMvpSeriesError("candidate batch link count is unsafe")


def _require_no_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if stat.S_ISLNK(os.lstat(component).st_mode):
            raise InstitutionalMvpSeriesError("candidate batch path contains a symlink")


if __name__ == "__main__":
    raise SystemExit(main())
