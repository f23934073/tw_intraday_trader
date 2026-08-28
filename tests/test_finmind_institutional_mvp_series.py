"""Digest, lineage, and fail-closed gates for the 60-session MVP series."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from config import twse_calendar_2026
from config.institutional_mvp import CALENDAR_SCOPE, load_daily_policy
from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.domain import (
    InstitutionalMvpCalendarEvidence,
    InstitutionalMvpCandidateBatchV1,
    InstitutionalMvpSourceEvidence,
    source_fingerprint,
)
from institutional_mvp.series import (
    InstitutionalMvpSeriesError,
    build_candidate_series_manifest,
    build_candidate_series_plan,
    dataset_reference,
    load_canonical_artifact,
    publish_content_addressed_json,
    verify_candidate_series_manifest,
    verify_candidate_series_plan,
)
from market_data.equity_calendar import ReviewedEquityCalendar


TAIPEI = ZoneInfo("Asia/Taipei")


def _calendar() -> ReviewedEquityCalendar:
    return ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)


def _dataset_reference() -> dict[str, object]:
    manifest = {
        "bar_count": 51_213_436,
        "bars_sha256": "e" * 64,
        "dataset_id": "dataset-finmind-test",
        "end_date": "2026-08-18",
        "issues": ["CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED"],
        "manifest_digest": "d" * 64,
        "observed_symbols": ["1101"],
        "payload_order": "TIMESTAMP_SYMBOL",
        "plan_identity_digest": "c" * 64,
        "profile": "KBAR_1M_V1",
        "research_eligible": False,
        "source": "FINMIND_SPONSOR_TAIWAN_STOCK_KBAR",
        "source_snapshot_digest": "b" * 64,
        "start_date": "2023-08-19",
        "storage_format": "JSONL_FULL_V1",
        "universe_scope": "CURRENT_SNAPSHOT",
        "universe_selection": "FINMIND_COMPLETE_SYMBOLS_V1",
    }
    return dataset_reference(manifest, selection_audit_digest="a" * 64)


def _plan() -> dict[str, object]:
    return build_candidate_series_plan(
        calendar=_calendar(),
        policy=load_daily_policy(),
        price_dataset_reference=_dataset_reference(),
        target_end=date(2026, 8, 18),
        session_count=60,
    )


def _batches(plan: dict[str, object]) -> list[dict[str, object]]:
    calendar = _calendar()
    policy = load_daily_policy()
    evidence = InstitutionalMvpCalendarEvidence(
        schema_version=calendar.schema_version,
        timezone=calendar.timezone,
        coverage_start=calendar.coverage_start,
        coverage_end=calendar.coverage_end,
        source_digest=calendar.source_digest,
        scope=CALENDAR_SCOPE,
    )
    batches: list[dict[str, object]] = []
    for pair in plan["session_pairs"]:
        source_session = date.fromisoformat(pair["source_session"])
        target_session = date.fromisoformat(pair["target_session"])
        flow_digest = hashlib.sha256(source_session.isoformat().encode()).hexdigest()
        stock_digest = hashlib.sha256(b"stock-info").hexdigest()
        source = InstitutionalMvpSourceEvidence(
            provider="FINMIND",
            source_version="FINMIND_API_V4",
            retrieved_at=datetime(2026, 8, 27, 14, 0, tzinfo=TAIPEI),
            flow_raw_sha256=flow_digest,
            stock_info_raw_sha256=stock_digest,
            stock_info_source_rows=1,
            flow_source_rows=1,
            mapped_flow_rows=1,
            unmapped_flow_rows=0,
            candidate_count_before_limit=0,
            published_candidate_count=0,
            usage_user_count_before=100,
            usage_request_limit=1000,
            usage_remaining_before=900,
        )
        fingerprint = source_fingerprint(
            source_session=source_session,
            target_session=target_session,
            policy_digest=policy.canonical_sha256,
            calendar_digest=calendar.source_digest,
            provider=source.provider,
            source_version=source.source_version,
            flow_raw_sha256=flow_digest,
            stock_info_raw_sha256=stock_digest,
        )
        batch = InstitutionalMvpCandidateBatchV1(
            source_session=source_session,
            target_session=target_session,
            generated_at=datetime(2026, 8, 27, 14, 1, tzinfo=TAIPEI),
            expires_at=datetime.combine(target_session, time(13, 30), tzinfo=TAIPEI),
            source_fingerprint=fingerprint,
            policy=policy,
            calendar=evidence,
            source=source,
            candidates=(),
        )
        batches.append(json.loads(canonical_json(batch.to_dict())))
    return batches


def _rehash(payload: dict[str, object], prefix: str) -> None:
    body = dict(payload)
    body.pop("artifact_digest", None)
    body.pop("artifact_id", None)
    digest = sha256_text(canonical_json(body))
    payload["artifact_digest"] = digest
    payload["artifact_id"] = f"{prefix}-{digest[:20]}"


def test_plan_freezes_exactly_60_unique_overlapping_next_sessions() -> None:
    plan = _plan()
    pairs = verify_candidate_series_plan(
        plan,
        calendar=_calendar(),
        policy=load_daily_policy(),
        price_dataset_reference=_dataset_reference(),
    )

    assert len(pairs) == 60
    assert len({target for _, target in pairs}) == 60
    assert pairs[-1][1] == date(2026, 8, 18)
    assert all(_calendar().next_trading_day(source) == target for source, target in pairs)
    assert all(date(2023, 8, 19) <= target <= date(2026, 8, 18) for _, target in pairs)
    assert plan["execution_permissions"]["outcome_generation_allowed"] is False
    assert plan["execution_permissions"]["order_submission_allowed"] is False


def test_plan_rejects_fewer_than_60_or_drifted_dataset() -> None:
    with pytest.raises(ValueError, match="at least 60"):
        build_candidate_series_plan(
            calendar=_calendar(),
            policy=load_daily_policy(),
            price_dataset_reference=_dataset_reference(),
            target_end=date(2026, 8, 18),
            session_count=59,
        )
    plan = _plan()
    drifted = deepcopy(_dataset_reference())
    drifted["manifest_digest"] = "0" * 64
    with pytest.raises(ValueError, match="differs from reviewed reconstruction"):
        verify_candidate_series_plan(
            plan,
            calendar=_calendar(),
            policy=load_daily_policy(),
            price_dataset_reference=drifted,
        )


def test_series_pins_every_batch_and_preserves_all_downstream_locks() -> None:
    plan = _plan()
    batches = _batches(plan)
    series = build_candidate_series_manifest(
        plan=plan,
        batches=batches,
        calendar=_calendar(),
        policy=load_daily_policy(),
    )
    verify_candidate_series_manifest(
        series,
        plan=plan,
        batches=batches,
        calendar=_calendar(),
        policy=load_daily_policy(),
    )

    assert series["batch_count"] == 60
    assert series["overlapping_target_session_count"] == 60
    assert len({item["artifact_digest"] for item in series["batch_references"]}) == 60
    assert series["research_eligibility"]["research_eligible"] is False
    assert series["evidence_scope"] == {
        "backtest_or_holdout_read": False,
        "institutional_flow_fields_read": True,
        "price_or_kbar_read": False,
        "return_or_pnl_read": False,
    }
    assert series["execution_permissions"]["evaluation_universe_freeze_allowed"] is False
    assert series["execution_permissions"]["outcome_generation_allowed"] is False


def test_series_rejects_rehashed_batch_calendar_claim_drift() -> None:
    plan = _plan()
    batches = _batches(plan)
    drifted = deepcopy(batches)
    drifted[0]["calendar_evidence"]["coverage_start"] = "2020-01-01"
    body = dict(drifted[0])
    body.pop("artifact_digest")
    body.pop("artifact_id")
    digest = sha256_text(canonical_json(body))
    drifted[0]["artifact_digest"] = digest
    drifted[0]["artifact_id"] = (
        f"finmind-institutional-mvp-batch-v1-{drifted[0]['target_session']}-{digest[:16]}"
    )

    with pytest.raises(ValueError, match="calendar evidence differs"):
        build_candidate_series_manifest(
            plan=plan,
            batches=drifted,
            calendar=_calendar(),
            policy=load_daily_policy(),
        )


def test_series_manifest_tamper_rejected_even_when_identity_is_rehashed() -> None:
    plan = _plan()
    batches = _batches(plan)
    series = build_candidate_series_manifest(
        plan=plan,
        batches=batches,
        calendar=_calendar(),
        policy=load_daily_policy(),
    )
    changed = deepcopy(series)
    changed["execution_permissions"]["outcome_generation_allowed"] = True
    _rehash(changed, "finmind-institutional-mvp-candidate-series-v1")

    with pytest.raises(ValueError, match="differs from exact batch reconstruction"):
        verify_candidate_series_manifest(
            changed,
            plan=plan,
            batches=batches,
            calendar=_calendar(),
            policy=load_daily_policy(),
        )


def test_content_addressed_publish_is_canonical_and_idempotent(tmp_path: Path) -> None:
    plan = _plan()
    path, created = publish_content_addressed_json(tmp_path, category="plans", payload=plan)
    replay_path, replay_created = publish_content_addressed_json(
        tmp_path, category="plans", payload=plan
    )

    assert created is True
    assert replay_created is False
    assert replay_path == path
    assert load_canonical_artifact(path) == plan


def test_content_addressed_publish_rejects_false_body_digest(tmp_path: Path) -> None:
    plan = deepcopy(_plan())
    plan["artifact_digest"] = "0" * 64
    plan["artifact_id"] = f"finmind-institutional-mvp-series-plan-v1-{'0' * 20}"

    with pytest.raises(InstitutionalMvpSeriesError, match="digest"):
        publish_content_addressed_json(tmp_path, category="plans", payload=plan)

    assert not list(tmp_path.rglob("*.json"))


def test_content_addressed_load_rejects_false_body_digest(tmp_path: Path) -> None:
    plan = deepcopy(_plan())
    plan["artifact_digest"] = "0" * 64
    plan["artifact_id"] = f"finmind-institutional-mvp-series-plan-v1-{'0' * 20}"
    path = tmp_path / f"{plan['artifact_digest']}.json"
    path.write_text(canonical_json(plan) + "\n", encoding="utf-8")

    with pytest.raises(InstitutionalMvpSeriesError, match="digest"):
        load_canonical_artifact(path)


def test_content_addressed_publish_rejects_symlinked_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises((InstitutionalMvpSeriesError, OSError)):
        publish_content_addressed_json(
            linked_root,
            category="plans",
            payload=_plan(),
        )

    assert not list(real_root.rglob("*.json"))


def test_content_addressed_load_rejects_symlink_and_external_hardlink(
    tmp_path: Path,
) -> None:
    plan = _plan()
    path, _ = publish_content_addressed_json(tmp_path, category="plans", payload=plan)
    symlink = tmp_path / f"{plan['artifact_digest']}.json"
    symlink.symlink_to(path)

    with pytest.raises((InstitutionalMvpSeriesError, OSError)):
        load_canonical_artifact(symlink)

    hardlink = tmp_path / "outside-hardlink.json"
    os.link(path, hardlink)
    with pytest.raises(InstitutionalMvpSeriesError, match="link"):
        load_canonical_artifact(path)


def test_content_addressed_publish_rejects_symlinked_category_and_destination(
    tmp_path: Path,
) -> None:
    plan = _plan()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "plans").symlink_to(outside, target_is_directory=True)

    with pytest.raises(InstitutionalMvpSeriesError):
        publish_content_addressed_json(root, category="plans", payload=plan)
    assert not list(outside.glob("*.json"))

    (root / "plans").unlink()
    (root / "plans").mkdir()
    victim = outside / "victim.json"
    victim.write_text("do-not-touch\n", encoding="utf-8")
    destination = root / "plans" / f"{plan['artifact_digest']}.json"
    destination.symlink_to(victim)
    with pytest.raises(InstitutionalMvpSeriesError):
        publish_content_addressed_json(root, category="plans", payload=plan)
    assert victim.read_text(encoding="utf-8") == "do-not-touch\n"


def test_content_addressed_concurrent_exact_publish_has_one_creator(
    tmp_path: Path,
) -> None:
    plan = _plan()
    root = tmp_path / "repository"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: publish_content_addressed_json(
                    root, category="plans", payload=plan
                ),
                range(8),
            )
        )

    assert sum(created for _, created in results) == 1
    assert {path for path, _ in results} == {
        root / "plans" / f"{plan['artifact_digest']}.json"
    }


def test_content_addressed_publish_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)
    root = linked_parent / "repository"

    with pytest.raises(InstitutionalMvpSeriesError, match="symlink"):
        publish_content_addressed_json(root, category="plans", payload=_plan())

    assert not (outside / "repository").exists()


def test_content_addressed_publish_recovers_own_stale_hardlink(
    tmp_path: Path,
) -> None:
    plan = _plan()
    path, created = publish_content_addressed_json(
        tmp_path, category="plans", payload=plan
    )
    assert created is True
    stale = path.parent / f".{plan['artifact_digest']}.{'a' * 32}.tmp"
    os.link(path, stale)
    assert path.stat().st_nlink == 2

    replay_path, replay_created = publish_content_addressed_json(
        tmp_path, category="plans", payload=plan
    )

    assert replay_path == path
    assert replay_created is False
    assert path.stat().st_nlink == 1
    assert not stale.exists()
