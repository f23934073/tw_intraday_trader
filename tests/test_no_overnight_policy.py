from datetime import date, datetime, time

import pytest

from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from trading.no_overnight import (
    ManagedExposureEvidence,
    NoOvernightEvidence,
    NoOvernightPlanningError,
    NoOvernightState,
    NoOvernightWouldAction,
    ReconciliationStatus,
    ReviewedSessionWindow,
    plan_no_overnight_transition,
)


def _config() -> NoOvernightPolicyConfig:
    return NoOvernightPolicyConfig(
        mode=NoOvernightMode.OBSERVE_ONLY,
        account_scope_id="local-paper-account-v2",
        policy_family_id="no-overnight-local-paper-v1",
        policy_version="observe-policy-v1",
        timezone="Asia/Taipei",
        market_open=time(9, 0),
        no_new_entry_at=time(13, 10),
        cancel_entry_at=time(13, 15),
        flatten_at=time(13, 20),
        aggressive_exit_at=time(13, 25),
        final_reconciliation_at=time(13, 28),
        reviewed_session_close=time(13, 30),
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
        executable_book_policy_id="local-paper-book-v1",
    )


def _window() -> ReviewedSessionWindow:
    return ReviewedSessionWindow(
        session_date=date(2026, 8, 24),
        timezone="Asia/Taipei",
        opens_at=datetime.fromisoformat("2026-08-24T09:00:00+08:00"),
        closes_at=datetime.fromisoformat("2026-08-24T13:30:00+08:00"),
        calendar_schema_version="twse_calendar_2026_v1",
        calendar_digest="a" * 64,
    )


def _empty_evidence(*, last_execution_sequence: int = 0) -> NoOvernightEvidence:
    now = datetime.fromisoformat("2026-08-24T13:00:00+08:00")
    return NoOvernightEvidence(
        session_date=date(2026, 8, 24),
        managed_exposures=(),
        pending_entry_quantity=(),
        pending_exit_quantity=(),
        unresolved_execution_ids=(),
        reconciliation_status=ReconciliationStatus.MATCH,
        reconciliation_digest="d" * 64,
        last_fill_journal_sequence=0,
        last_execution_fact_journal_sequence=last_execution_sequence,
        snapshot_covers_through_journal_sequence=last_execution_sequence,
        snapshot_journal_sequence=last_execution_sequence + 1,
        snapshot_source_as_of=now,
        snapshot_received_at=now,
    )


def test_policy_config_is_strict_and_digest_is_canonical() -> None:
    first = _config()
    second = _config()

    assert first.policy_digest == second.policy_digest
    assert first.canonical_payload()["mode"] == "OBSERVE_ONLY"

    with pytest.raises(ValueError, match="ordered"):
        NoOvernightPolicyConfig(
            **{
                **first.constructor_values(),
                "flatten_at": time(13, 14),
            }
        )

    with pytest.raises(ValueError, match="NoOvernightMode"):
        NoOvernightPolicyConfig(
            **{
                **first.constructor_values(),
                "mode": "OBSERVE_ONLY",
            }
        )


def test_policy_digest_preserves_cutoff_microseconds_and_rejects_fold() -> None:
    first = NoOvernightPolicyConfig(
        **{
            **_config().constructor_values(),
            "no_new_entry_at": time(13, 10, 0, 1),
        }
    )
    second = NoOvernightPolicyConfig(
        **{
            **_config().constructor_values(),
            "no_new_entry_at": time(13, 10, 0, 2),
        }
    )

    assert first.policy_digest != second.policy_digest
    assert first.canonical_payload()["no_new_entry_at"] == "13:10:00.000001"
    with pytest.raises(ValueError, match="fold"):
        NoOvernightPolicyConfig(
            **{
                **_config().constructor_values(),
                "no_new_entry_at": time(13, 10, fold=1),
            }
        )


@pytest.mark.parametrize(
    ("field_name", "unsupported"),
    (
        ("schema_version", "no_overnight_policy_config_v2"),
        ("validation_algorithm_version", "ordered_session_cutoffs_v2"),
    ),
)
def test_policy_rejects_unsupported_contract_versions(
    field_name: str,
    unsupported: str,
) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        NoOvernightPolicyConfig(
            **{
                **_config().constructor_values(),
                field_name: unsupported,
            }
        )

def test_pure_planner_is_deterministic_and_late_start_jumps_to_current_phase() -> None:
    now = datetime.fromisoformat("2026-08-24T13:26:00+08:00")
    config = _config()
    evidence = _empty_evidence()

    first = plan_no_overnight_transition(
        config=config,
        window=_window(),
        now=now,
        current_state=NoOvernightState.NORMAL,
        current_revision=0,
        evidence=evidence,
    )
    second = plan_no_overnight_transition(
        config=config,
        window=_window(),
        now=now,
        current_state=NoOvernightState.NORMAL,
        current_revision=0,
        evidence=evidence,
    )

    assert first == second
    assert first.state is NoOvernightState.AGGRESSIVE_EXIT
    assert first.would_actions == (
        NoOvernightWouldAction.WOULD_BLOCK_ENTRY,
        NoOvernightWouldAction.WOULD_EXIT,
    )
    assert first.digest == second.digest

    unchanged = plan_no_overnight_transition(
        config=config,
        window=_window(),
        now=datetime.fromisoformat("2026-08-24T13:27:00+08:00"),
        current_state=NoOvernightState.AGGRESSIVE_EXIT,
        current_revision=1,
        evidence=evidence,
    )
    assert unchanged.state is NoOvernightState.AGGRESSIVE_EXIT
    assert unchanged.revision == 1


def test_final_flat_proof_distinguishes_never_exposed_and_fill_derived() -> None:
    config = _config()
    closed = datetime.fromisoformat("2026-08-24T13:30:00+08:00")

    never_exposed = plan_no_overnight_transition(
        config=config,
        window=_window(),
        now=closed,
        current_state=NoOvernightState.FINAL_RECONCILIATION,
        current_revision=4,
        evidence=_empty_evidence(),
    )
    assert never_exposed.state is NoOvernightState.CONFIRMED_FLAT
    assert never_exposed.flat_proof_mode == "NEVER_EXPOSED"

    as_of = datetime.fromisoformat("2026-08-24T13:30:00+08:00")
    fill_derived_evidence = NoOvernightEvidence(
        session_date=date(2026, 8, 24),
        managed_exposures=(
            ManagedExposureEvidence(
                exposure_id="managed-1",
                current_quantity=0,
                max_quantity_during_session=1000,
                authoritative_open_fill_quantity=1000,
                authoritative_close_fill_quantity=1000,
            ),
        ),
        pending_entry_quantity=(),
        pending_exit_quantity=(),
        unresolved_execution_ids=(),
        reconciliation_status=ReconciliationStatus.MATCH,
        reconciliation_digest="d" * 64,
        last_fill_journal_sequence=20,
        last_execution_fact_journal_sequence=21,
        snapshot_covers_through_journal_sequence=21,
        snapshot_journal_sequence=22,
        snapshot_source_as_of=as_of,
        snapshot_received_at=as_of,
    )
    fill_derived = plan_no_overnight_transition(
        config=config,
        window=_window(),
        now=closed,
        current_state=NoOvernightState.FINAL_RECONCILIATION,
        current_revision=4,
        evidence=fill_derived_evidence,
    )
    assert fill_derived.state is NoOvernightState.CONFIRMED_FLAT
    assert fill_derived.flat_proof_mode == "FILL_DERIVED_CLOSE"


def test_planner_fails_closed_for_timezone_session_and_snapshot_fence_mismatch() -> None:
    config = _config()
    evidence = _empty_evidence(last_execution_sequence=10)
    stale = NoOvernightEvidence(
        **{
            **evidence.constructor_values(),
            "snapshot_covers_through_journal_sequence": 9,
        }
    )

    with pytest.raises(NoOvernightPlanningError, match="snapshot fence"):
        plan_no_overnight_transition(
            config=config,
            window=_window(),
            now=datetime.fromisoformat("2026-08-24T13:30:00+08:00"),
            current_state=NoOvernightState.FINAL_RECONCILIATION,
            current_revision=4,
            evidence=stale,
        )

    with pytest.raises(NoOvernightPlanningError, match="timezone"):
        plan_no_overnight_transition(
            config=config,
            window=_window(),
            now=datetime.fromisoformat("2026-08-24T05:30:00+00:00"),
            current_state=NoOvernightState.NORMAL,
            current_revision=0,
            evidence=evidence,
        )
