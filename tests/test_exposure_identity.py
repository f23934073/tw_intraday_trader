from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from trading.exposure import (
    AccountScopeIdentity,
    ExecutionReasonCategory,
    HoldingHorizon,
    PolicyFamilyIdentity,
    PositionAction,
    build_exposure_identity,
    build_legacy_exposure_identity,
    build_semantic_action_key,
)


ACCOUNT_SCOPE_ID = "local-paper-main-v1"
POLICY_FAMILY_ID = "no-overnight-equity-v1"
POLICY_DIGEST = "a" * 64


def test_scope_and_policy_family_are_immutable_validated_identities() -> None:
    account = AccountScopeIdentity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        execution_mode="LOCAL_PAPER_SIMULATION",
        ledger_id="local-paper-ledger-v1",
    )
    family = PolicyFamilyIdentity(
        policy_family_id=POLICY_FAMILY_ID,
        account_scope_id=account.account_scope_id,
    )

    assert account.identity_schema_version == "account-scope-identity-v1"
    assert family.policy_kind == "NO_OVERNIGHT"
    assert len(account.digest) == 64
    assert len(family.digest) == 64

    with pytest.raises(FrozenInstanceError):
        account.account_scope_id = "different"  # type: ignore[misc]
    with pytest.raises(ValueError, match="account_scope_id"):
        AccountScopeIdentity(
            account_scope_id=" generated at startup ",
            execution_mode="LOCAL_PAPER_SIMULATION",
            ledger_id="local-paper-ledger-v1",
        )


def test_exposure_identity_is_deterministic_and_policy_managed_is_derived() -> None:
    first = build_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="local-researcher",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest=POLICY_DIGEST,
        entry_identity="manual-order:001",
    )
    repeated = build_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="local-researcher",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest=POLICY_DIGEST,
        entry_identity="manual-order:001",
    )
    long_term = build_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="local-researcher",
        holding_horizon=HoldingHorizon.LONG_TERM,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest=POLICY_DIGEST,
        entry_identity="manual-order:002",
    )

    assert first == repeated
    assert first.exposure_id.startswith("exposure_v1_")
    assert first.no_overnight_managed is True
    assert long_term.no_overnight_managed is False
    assert first.exposure_id != long_term.exposure_id
    assert PositionAction.OPEN_LONG.value == "OPEN_LONG"
    assert ExecutionReasonCategory.OPERATIONAL_RISK.value == "OPERATIONAL_RISK"


def test_policy_revision_rotation_keeps_scope_and_family_identity() -> None:
    first = build_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="local-researcher",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v1",
        entry_policy_digest="a" * 64,
        entry_identity="manual-order:rotation",
    )
    rotated = build_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="local-researcher",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="exposure-policy-v2",
        entry_policy_digest="b" * 64,
        entry_identity="manual-order:rotation",
    )

    assert rotated.account_scope_id == first.account_scope_id
    assert rotated.policy_family_id == first.policy_family_id
    assert rotated.exposure_id != first.exposure_id
    assert first.no_overnight_managed is rotated.no_overnight_managed is True


def test_legacy_mapping_is_deterministic_and_never_silently_managed() -> None:
    first = build_legacy_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        source_session_id="local-paper-runtime-v1",
        symbol="2330",
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
    )
    repeated = build_legacy_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        source_session_id="local-paper-runtime-v1",
        symbol="2330",
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
    )

    assert first == repeated
    assert first.exposure_id.startswith("legacy_exposure_v1_")
    assert first.holding_horizon is HoldingHorizon.UNCLASSIFIED_LEGACY
    assert first.no_overnight_managed is False


def test_exposure_reader_rejects_unknown_or_non_string_identity_fields() -> None:
    exposure = build_legacy_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        source_session_id="local-paper-runtime-v1",
        symbol="2330",
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
    )
    payload = exposure.to_payload()

    with pytest.raises(ValueError, match="unknown exposure identity fields"):
        type(exposure).from_payload({**payload, "managed": True})
    with pytest.raises(ValueError, match="invalid type"):
        type(exposure).from_payload({**payload, "owner_id": None})


def test_semantic_action_key_excludes_mutable_planner_evidence() -> None:
    common = {
        "account_scope_id": ACCOUNT_SCOPE_ID,
        "policy_family_id": POLICY_FAMILY_ID,
        "session_date": date(2026, 8, 23),
        "exposure_id": "exposure_v1_" + "b" * 64,
        "action": "CLOSE_LONG",
        "attempt": 1,
    }

    first = build_semantic_action_key(**common)
    repeated = build_semantic_action_key(**common)
    successor = build_semantic_action_key(**{**common, "attempt": 2})

    assert first == repeated
    assert first.startswith("no_overnight_action_v1_")
    assert first != successor
