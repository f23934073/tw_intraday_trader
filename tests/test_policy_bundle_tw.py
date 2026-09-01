"""Current-parent tests for the unwired PolicyBundleTW v2 contract."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import date, time
from typing import Any, cast

import pytest

from backtest.cost_policy_tw import build_cost_policy_snapshot
from backtest.execution_policy_tw import build_execution_policy_snapshot
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from config.policy_bundle_tw import (
    ACTIVATION_AUTHORITY,
    BROKER_MARKET_ACCEPTANCE_STATUS,
    POLICY_BUNDLE_CONTRACT_VERSION,
    POLICY_BUNDLE_VALIDATION_VERSION,
    RUNTIME_CONSUMER_STATUS,
    WIRING_STATUS,
    BrokerPolicyTW,
    ExitOwnershipTW,
    LegalReferenceTW,
    PolicyBundleError,
    PolicyBundleProvenanceTW,
    PolicyBundleTW,
    RiskExitRatios,
    SessionCalendarTW,
    verify_policy_bundle_snapshot,
)


GOLDEN_BUNDLE_DIGEST = "77458d709187df6c00c88378f4f688b6bba9b36073df03a87bb2c528971388a5"


def _policy(
    *,
    timezone: str = "Asia/Taipei",
    mode: NoOvernightMode = NoOvernightMode.OBSERVE_ONLY,
) -> NoOvernightPolicyConfig:
    if mode is NoOvernightMode.DISABLED:
        return NoOvernightPolicyConfig.disabled(
            account_scope_id="account-001",
            policy_family_id="no-overnight-tw",
            policy_version="disabled-v2-fixture",
            timezone=timezone,
        )
    return NoOvernightPolicyConfig(
        mode=mode,
        account_scope_id="account-001",
        policy_family_id="no-overnight-tw",
        policy_version="policy-v2-fixture",
        timezone=timezone,
        market_open=time(9, 0),
        no_new_entry_at=time(13, 10),
        cancel_entry_at=time(13, 15),
        flatten_at=time(13, 20),
        aggressive_exit_at=time(13, 25),
        final_reconciliation_at=time(13, 28),
        reviewed_session_close=time(13, 30),
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
        executable_book_policy_id="book-policy-v2-fixture",
    )


def _legal() -> LegalReferenceTW:
    return LegalReferenceTW(
        authority="TWSE",
        rule_id="TWSE-RULE-94",
        source_ids=("twse-rule-94", "twse-trading-calendar"),
        instrument_class_scope=("TWSE_COMMON_STOCK", "TPEX_COMMON_STOCK"),
        effective_from=date(2026, 8, 6),
        effective_through=None,
        reviewed_on=date(2026, 8, 31),
        source_digest="c" * 64,
    )


def _broker() -> BrokerPolicyTW:
    return BrokerPolicyTW(
        broker_id="broker-fixture",
        account_scope_id="account-001",
        terms_version="terms-2026-08",
        commission_rate="0.001425",
        min_commission_twd="20",
        effective_from=date(2026, 8, 1),
        effective_through=None,
        reviewed_on=date(2026, 8, 31),
        terms_evidence_digest="d" * 64,
    )


def _calendar(*, timezone: str = "Asia/Taipei") -> SessionCalendarTW:
    return SessionCalendarTW(
        calendar_id="twse-calendar-2026-reviewed",
        calendar_digest="e" * 64,
        timezone=timezone,
        trading_date=date(2026, 9, 1),
        covered_from=date(2026, 1, 1),
        covered_through=date(2026, 12, 31),
        reviewed_on=date(2026, 8, 31),
    )


def _ownership() -> ExitOwnershipTW:
    return ExitOwnershipTW(
        revision=1,
        account_scope_id="account-001",
        policy_family_id="no-overnight-tw",
        entry_owner="entry-policy-v1",
        stop_loss_owner="stop-loss-v1",
        take_profit_owner="take-profit-v1",
        end_of_day_owner="end-of-day-v1",
        priority_order=("stop-loss-v1", "take-profit-v1", "end-of-day-v1"),
    )


def _provenance() -> PolicyBundleProvenanceTW:
    return PolicyBundleProvenanceTW(
        source_commit="dbcd9bcb0ba0c13f889f21575bdf0b6d3e5887af",
        source_tree="6dba3bf2f44aac7080abb9001626efb43cc94e78",
        requirements_digest=("21b845278395117a4460b8e6bbae8208488bc09e7718fcf4489954c730ffaa71"),
        builder_identity="task368-r9",
        fixture_id="policy-bundle-v2-golden",
    )


def _execution() -> dict[str, Any]:
    return build_execution_policy_snapshot(participation_calibration_digest="a" * 64)


def _cost() -> dict[str, Any]:
    return build_cost_policy_snapshot(
        slippage_bps="5",
        slippage_calibration_digest="b" * 64,
    )


def _bundle(
    *,
    execution: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
    policy: NoOvernightPolicyConfig | None = None,
    legal: LegalReferenceTW | None = None,
    broker: BrokerPolicyTW | None = None,
    calendar: SessionCalendarTW | None = None,
    ownership: ExitOwnershipTW | None = None,
) -> PolicyBundleTW:
    return PolicyBundleTW(
        execution_policy_snapshot=_execution() if execution is None else execution,
        cost_policy_snapshot=_cost() if cost is None else cost,
        no_overnight_policy=_policy() if policy is None else policy,
        legal_reference=_legal() if legal is None else legal,
        broker_policy=_broker() if broker is None else broker,
        exit_ratios=RiskExitRatios(stop_loss_ratio="0.05", take_profit_ratio="0.10"),
        session_calendar=_calendar() if calendar is None else calendar,
        exit_ownership=_ownership() if ownership is None else ownership,
        provenance=_provenance(),
    )


def _redigest(snapshot: dict[str, Any]) -> dict[str, Any]:
    rewritten = copy.deepcopy(snapshot)
    rewritten.pop("bundle_digest", None)
    encoded = json.dumps(
        rewritten,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    rewritten["bundle_digest"] = hashlib.sha256(encoded).hexdigest()
    return rewritten


def test_v2_golden_is_deterministic_and_seals_negative_authority() -> None:
    first = _bundle()
    second = _bundle()
    snapshot = first.sealed_snapshot()

    assert first.bundle_digest == second.bundle_digest
    assert first.bundle_digest == GOLDEN_BUNDLE_DIGEST
    assert snapshot == second.sealed_snapshot()
    assert snapshot["contract_version"] == POLICY_BUNDLE_CONTRACT_VERSION
    assert snapshot["validation_algorithm_version"] == POLICY_BUNDLE_VALIDATION_VERSION
    assert snapshot["wiring_status"] == WIRING_STATUS == "NOT_WIRED"
    assert snapshot["runtime_consumer_status"] == (RUNTIME_CONSUMER_STATUS) == "NO_RUNTIME_CONSUMER"
    assert snapshot["activation_authority"] == (ACTIVATION_AUTHORITY) == "NO_ACTIVATION_AUTHORITY"
    assert first.wiring_status == WIRING_STATUS
    assert first.runtime_consumer_status == RUNTIME_CONSUMER_STATUS
    assert first.activation_authority == ACTIVATION_AUTHORITY
    assert not hasattr(first, "evidence_readiness")


def test_derived_child_and_session_digests_are_sealed_not_caller_supplied() -> None:
    bundle = _bundle()
    snapshot = bundle.sealed_snapshot()
    derived = snapshot["provenance"]["derived_policy_digests"]

    assert (
        bundle.execution_policy_digest == snapshot["execution_policy_snapshot"]["snapshot_digest"]
    )
    assert bundle.cost_policy_digest == snapshot["cost_policy_snapshot"]["snapshot_digest"]
    assert bundle.session_policy_digest == bundle.no_overnight_policy.policy_digest
    assert derived == {
        "execution_policy_digest": bundle.execution_policy_digest,
        "cost_policy_digest": bundle.cost_policy_digest,
        "session_policy_digest": bundle.session_policy_digest,
    }
    assert snapshot["provenance"]["calibration_reasons"] == {
        "execution_policy": None,
        "cost_policy": None,
    }


def test_json_roundtrip_and_verifier_are_deterministic() -> None:
    snapshot = _bundle().sealed_snapshot()
    roundtripped = cast(dict[str, Any], json.loads(json.dumps(snapshot)))

    assert verify_policy_bundle_snapshot(roundtripped) == snapshot
    assert PolicyBundleTW.from_snapshot(roundtripped).sealed_snapshot() == snapshot


def test_constructor_defensively_copies_nested_child_inputs() -> None:
    execution = _execution()
    cost = _cost()
    bundle = _bundle(execution=execution, cost=cost)
    original = bundle.sealed_snapshot()

    execution["tick_bands"][0]["tick"] = "999"
    cost["securities_transaction_tax"]["standard_rate"] = "999"

    assert bundle.sealed_snapshot() == original
    assert bundle.bundle_digest == original["bundle_digest"]


def test_every_export_is_a_fresh_deep_copy() -> None:
    bundle = _bundle()
    first = bundle.sealed_snapshot()
    execution = bundle.execution_policy_snapshot
    cost = bundle.cost_policy_snapshot

    first["execution_policy_snapshot"]["tick_bands"][0]["tick"] = "999"
    first["legal_reference"]["source_ids"].append("attacker")
    execution["tick_bands"][0]["tick"] = "999"
    cost["securities_transaction_tax"]["standard_rate"] = "999"

    later = bundle.sealed_snapshot()
    assert later["execution_policy_snapshot"]["tick_bands"][0]["tick"] == "0.01"
    assert later["legal_reference"]["source_ids"] == [
        "twse-rule-94",
        "twse-trading-calendar",
    ]
    assert bundle.bundle_digest == later["bundle_digest"]


@pytest.mark.parametrize(
    "field_name",
    ("wiring_status", "runtime_consumer_status", "activation_authority"),
)
def test_negative_authority_values_cannot_be_changed_even_with_new_outer_digest(
    field_name: str,
) -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot[field_name] = "ALLOWED"

    with pytest.raises(PolicyBundleError, match="BUNDLE_INVALID"):
        verify_policy_bundle_snapshot(_redigest(snapshot))


@pytest.mark.parametrize(
    "field_name",
    ("wiring_status", "runtime_consumer_status", "activation_authority"),
)
def test_negative_authority_values_are_mandatory(field_name: str) -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot.pop(field_name)

    with pytest.raises(PolicyBundleError, match="exact-key"):
        verify_policy_bundle_snapshot(_redigest(snapshot))


def test_unknown_top_level_field_is_refused_even_when_redigested() -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot["runtime_readiness"] = "READY"

    with pytest.raises(PolicyBundleError, match="unknown=runtime_readiness"):
        verify_policy_bundle_snapshot(_redigest(snapshot))


def test_non_string_mapping_key_has_deterministic_refusal() -> None:
    snapshot = _bundle().sealed_snapshot()
    malformed = cast(dict[str, Any], {**snapshot, 1: "not-json"})

    with pytest.raises(PolicyBundleError, match="keys must be strings"):
        verify_policy_bundle_snapshot(malformed)


@pytest.mark.parametrize(
    "dead_key",
    (
        "evidence_readiness",
        "execution_policy_digest",
        "cost_policy_digest",
        "book_staleness_policy_id",
        "auction_allocation_policy_id",
    ),
)
def test_dead_controller_keys_are_unknown_and_refused(dead_key: str) -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot["no_overnight_policy"][dead_key] = "legacy"

    with pytest.raises(PolicyBundleError, match=f"unknown={dead_key}"):
        verify_policy_bundle_snapshot(_redigest(snapshot))


def test_current_no_overnight_payload_has_only_current_keys() -> None:
    payload = _bundle().sealed_snapshot()["no_overnight_policy"]

    assert set(payload) == {
        "schema_version",
        "validation_algorithm_version",
        "mode",
        "account_scope_id",
        "policy_family_id",
        "policy_version",
        "timezone",
        "market_open",
        "no_new_entry_at",
        "cancel_entry_at",
        "flatten_at",
        "aggressive_exit_at",
        "final_reconciliation_at",
        "reviewed_session_close",
        "max_exit_attempts",
        "retry_cooldown_seconds",
        "executable_book_policy_id",
        "controller_hosting_mode",
        "controller_guard_kind",
    }


@pytest.mark.parametrize(
    "malformed",
    (1, True, "source", {"id": "source"}, None, ("source",)),
)
@pytest.mark.parametrize("field_name", ("source_ids", "instrument_class_scope"))
def test_malformed_legal_collections_fail_closed_in_direct_parse(
    field_name: str,
    malformed: Any,
) -> None:
    payload = _legal().canonical_payload()
    payload[field_name] = malformed

    with pytest.raises(PolicyBundleError, match="JSON list"):
        LegalReferenceTW.from_payload(payload)


@pytest.mark.parametrize(
    "malformed",
    (1, True, "source", {"id": "source"}, None, ("source",)),
)
@pytest.mark.parametrize("field_name", ("source_ids", "instrument_class_scope"))
def test_malformed_legal_collections_fail_closed_in_sealed_admission(
    field_name: str,
    malformed: Any,
) -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot["legal_reference"][field_name] = malformed

    with pytest.raises(PolicyBundleError, match="JSON list"):
        verify_policy_bundle_snapshot(_redigest(snapshot))


@pytest.mark.parametrize(
    ("policy_timezone", "calendar_timezone"),
    (
        ("UTC", "UTC"),
        ("UTC", "Asia/Taipei"),
        ("Asia/Taipei", "UTC"),
        ("Asia/Tokyo", "Asia/Tokyo"),
    ),
)
def test_policy_and_calendar_require_exact_asia_taipei(
    policy_timezone: str,
    calendar_timezone: str,
) -> None:
    with pytest.raises(PolicyBundleError, match="Asia/Taipei|timezone mismatch"):
        _bundle(
            policy=_policy(timezone=policy_timezone),
            calendar=_calendar(timezone=calendar_timezone),
        )


def test_child_snapshot_digest_tamper_is_refused() -> None:
    execution = _execution()
    execution["max_participation_rate"] = "0.10"

    with pytest.raises(PolicyBundleError, match="child policy verification"):
        _bundle(execution=execution)


@pytest.mark.parametrize("child", ("execution", "cost"))
def test_missing_calibration_is_refused(child: str) -> None:
    if child == "execution":
        with pytest.raises(PolicyBundleError, match="MISSING_PARTICIPATION_CALIBRATION"):
            _bundle(execution=build_execution_policy_snapshot())
    else:
        with pytest.raises(PolicyBundleError, match="MISSING_SLIPPAGE_CALIBRATION"):
            _bundle(cost=build_cost_policy_snapshot())


def test_caller_cannot_override_derived_policy_digests() -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot["provenance"]["derived_policy_digests"]["cost_policy_digest"] = "f" * 64

    with pytest.raises(PolicyBundleError, match="caller-supplied|non-canonical"):
        verify_policy_bundle_snapshot(_redigest(snapshot))


def test_broker_terms_must_match_policy_account_and_current_cost_snapshot() -> None:
    mismatched_account = replace(_broker(), account_scope_id="other-account")
    mismatched_rate = replace(_broker(), commission_rate="0.001")

    with pytest.raises(PolicyBundleError, match="account scope"):
        _bundle(broker=mismatched_account)
    with pytest.raises(PolicyBundleError, match="commission_rate"):
        _bundle(broker=mismatched_rate)


def test_legal_and_broker_evidence_must_cover_trading_date() -> None:
    expired_legal = LegalReferenceTW(
        authority="TWSE",
        rule_id="TWSE-RULE-94",
        source_ids=("twse-rule-94",),
        instrument_class_scope=("TWSE_COMMON_STOCK",),
        effective_from=date(2026, 1, 1),
        effective_through=date(2026, 8, 31),
        reviewed_on=date(2026, 8, 31),
        source_digest="c" * 64,
    )
    expired_broker = BrokerPolicyTW(
        broker_id="broker-fixture",
        account_scope_id="account-001",
        terms_version="terms-old",
        commission_rate="0.001425",
        min_commission_twd="20",
        effective_from=date(2026, 1, 1),
        effective_through=date(2026, 8, 31),
        reviewed_on=date(2026, 8, 31),
        terms_evidence_digest="d" * 64,
    )

    with pytest.raises(PolicyBundleError, match="legal_reference is not effective"):
        _bundle(legal=expired_legal)
    with pytest.raises(PolicyBundleError, match="broker_policy is not effective"):
        _bundle(broker=expired_broker)


@pytest.mark.parametrize("take_profit", ("0", "1", "-0.01", "1.01"))
def test_take_profit_ratio_must_be_strictly_between_zero_and_one(take_profit: str) -> None:
    with pytest.raises(PolicyBundleError, match="take_profit_ratio"):
        RiskExitRatios(stop_loss_ratio="0.05", take_profit_ratio=take_profit)


def test_exit_ownership_priority_is_exact_and_account_scoped() -> None:
    with pytest.raises(PolicyBundleError, match="every exit owner"):
        ExitOwnershipTW(
            revision=1,
            account_scope_id="account-001",
            policy_family_id="no-overnight-tw",
            entry_owner="entry-policy-v1",
            stop_loss_owner="stop-loss-v1",
            take_profit_owner="take-profit-v1",
            end_of_day_owner="end-of-day-v1",
            priority_order=("stop-loss-v1", "take-profit-v1"),
        )

    wrong_scope = ExitOwnershipTW(
        revision=1,
        account_scope_id="other-account",
        policy_family_id="no-overnight-tw",
        entry_owner="entry-policy-v1",
        stop_loss_owner="stop-loss-v1",
        take_profit_owner="take-profit-v1",
        end_of_day_owner="end-of-day-v1",
        priority_order=("stop-loss-v1", "take-profit-v1", "end-of-day-v1"),
    )
    with pytest.raises(PolicyBundleError, match="ownership account scope"):
        _bundle(ownership=wrong_scope)


def test_calendar_requires_coverage_and_regular_session() -> None:
    with pytest.raises(PolicyBundleError, match="does not cover"):
        SessionCalendarTW(
            calendar_id="calendar",
            calendar_digest="e" * 64,
            timezone="Asia/Taipei",
            trading_date=date(2026, 9, 1),
            covered_from=date(2026, 1, 1),
            covered_through=date(2026, 8, 31),
            reviewed_on=date(2026, 8, 31),
        )
    with pytest.raises(PolicyBundleError, match="session_kind"):
        SessionCalendarTW(
            calendar_id="calendar",
            calendar_digest="e" * 64,
            timezone="Asia/Taipei",
            trading_date=date(2026, 9, 1),
            covered_from=date(2026, 1, 1),
            covered_through=date(2026, 12, 31),
            reviewed_on=date(2026, 8, 31),
            session_kind="SYNTHETIC",
        )


@pytest.mark.parametrize("mode", tuple(NoOvernightMode))
def test_every_mode_remains_unwired_and_has_no_activation_authority(
    mode: NoOvernightMode,
) -> None:
    bundle = _bundle(policy=_policy(mode=mode))

    assert bundle.wiring_status == "NOT_WIRED"
    assert bundle.runtime_consumer_status == "NO_RUNTIME_CONSUMER"
    assert bundle.activation_authority == "NO_ACTIVATION_AUTHORITY"


@pytest.mark.parametrize("mode", tuple(NoOvernightMode))
def test_legacy_v1_payload_is_never_operationally_admitted(mode: NoOvernightMode) -> None:
    snapshot = _bundle(policy=_policy(mode=mode)).sealed_snapshot()
    snapshot["contract_version"] = "tw-policy-bundle-v1"
    snapshot["bundle_digest"] = "532482918b6b3f0e24d1808a3d53b55aa5c0b72813aa44029d3453808ba7acb4"

    with pytest.raises(PolicyBundleError, match="contract_version"):
        verify_policy_bundle_snapshot(snapshot)


@pytest.mark.parametrize(
    ("section", "field_name", "replacement"),
    (
        ("legal_reference", "authority", "TPEx"),
        ("broker_policy", "terms_version", "terms-2026-09"),
        ("exit_ratios", "take_profit_ratio", "0.11"),
        ("session_calendar", "calendar_id", "revised-calendar"),
        ("exit_ownership", "revision", 2),
        ("no_overnight_policy", "policy_version", "policy-v2-revised"),
    ),
)
def test_each_policy_section_mutation_changes_outer_digest(
    section: str,
    field_name: str,
    replacement: Any,
) -> None:
    original = _bundle().sealed_snapshot()
    mutated = copy.deepcopy(original)
    mutated[section][field_name] = replacement
    redigested = _redigest(mutated)

    assert redigested["bundle_digest"] != original["bundle_digest"]


def test_market_acceptance_remains_blocked_by_commission_sot() -> None:
    broker = _bundle().sealed_snapshot()["broker_policy"]

    assert broker["market_acceptance_status"] == BROKER_MARKET_ACCEPTANCE_STATUS
    assert broker["market_acceptance_status"] == "MARKET_ACCEPTANCE_BLOCKED_COMMISSION_SOT"


def test_policy_bundle_error_has_stable_fail_closed_code() -> None:
    snapshot = _bundle().sealed_snapshot()
    snapshot["activation_authority"] = "NONE"

    with pytest.raises(PolicyBundleError) as raised:
        verify_policy_bundle_snapshot(_redigest(snapshot))

    assert raised.value.code == "BUNDLE_INVALID"
    assert str(raised.value).startswith("BUNDLE_INVALID:")
