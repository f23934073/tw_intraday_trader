from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from institutional_data.domain import (
    CorrectionPolicy,
    ScopeCompatibility,
    TradeCategory,
    TradeScope,
)
from institutional_data.serialization import (
    deserialize_flow_rows,
    deserialize_partition_manifest,
    flow_rows_sha256,
)
from institutional_data.validation import (
    ValidationStatus,
    assess_trade_scope_compatibility,
    validate_flow_row,
    validate_partition,
)


FIXTURES = Path(__file__).parent / "fixtures" / "institutional"


def load_valid(market: str):  # type: ignore[no-untyped-def]
    rows = deserialize_flow_rows(
        (FIXTURES / f"{market}_flow_rows_valid.json").read_text(encoding="utf-8")
    )
    manifest = deserialize_partition_manifest(
        (FIXTURES / f"{market}_partition_manifest_valid.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest.normalized_sha256 == flow_rows_sha256(rows)
    return rows, manifest


@pytest.mark.parametrize("market", ["twse", "tpex"])
def test_valid_normalized_partition_passes_all_formula_and_identity_checks(
    market: str,
) -> None:
    rows, manifest = load_valid(market)

    report = validate_partition(manifest, rows)

    assert report.is_valid
    assert report.issues == ()


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("foreign_ex_dealer_net_shares", 1, "COMPONENT_NET_MISMATCH"),
        ("dealer_total_net_shares", 1, "DEALER_TOTAL_MISMATCH"),
        ("published_total_net_shares", 1, "PUBLISHED_TOTAL_MISMATCH"),
    ],
)
def test_flow_formula_mismatches_are_reported_without_mutating_the_row(
    field: str,
    value: int,
    code: str,
) -> None:
    rows, _ = load_valid("twse")
    invalid = replace(rows[0], **{field: value})

    report = validate_flow_row(invalid)

    assert not report.is_valid
    assert code in {issue.code for issue in report.issues}
    assert rows[0].foreign_ex_dealer_net_shares == 6000


def test_unpublished_dealer_components_do_not_quarantine_partition() -> None:
    rows, manifest = load_valid("twse")
    unsplit_row = replace(
        rows[0],
        dealer_proprietary_buy_shares=None,
        dealer_proprietary_sell_shares=None,
        dealer_proprietary_net_shares=None,
        dealer_hedge_buy_shares=None,
        dealer_hedge_sell_shares=None,
        dealer_hedge_net_shares=None,
    )
    unsplit_rows = (unsplit_row,)
    unsplit_manifest = replace(
        manifest,
        normalized_sha256=flow_rows_sha256(unsplit_rows),
    )

    report = validate_partition(unsplit_manifest, unsplit_rows)
    statuses = {check.name: check.status for check in report.checks}

    assert report.is_valid
    assert report.issues == ()
    assert statuses["dealer_total_validation"] is ValidationStatus.PASS
    assert (
        statuses["dealer_proprietary_validation"] is ValidationStatus.UNKNOWN_COMPONENT
    )
    assert statuses["dealer_hedge_validation"] is ValidationStatus.UNKNOWN_COMPONENT
    assert (
        statuses["dealer_component_reconciliation"] is ValidationStatus.NOT_APPLICABLE
    )


def test_available_dealer_components_reconcile_or_fail_explicitly() -> None:
    rows, _ = load_valid("twse")
    valid_report = validate_flow_row(rows[0])
    invalid_report = validate_flow_row(
        replace(rows[0], dealer_proprietary_net_shares=999)
    )

    valid_statuses = {check.name: check.status for check in valid_report.checks}
    invalid_statuses = {check.name: check.status for check in invalid_report.checks}

    assert valid_statuses["dealer_component_reconciliation"] is ValidationStatus.PASS
    assert invalid_statuses["dealer_component_reconciliation"] is ValidationStatus.FAIL
    assert not invalid_report.is_valid


def test_partition_reports_duplicates_identity_and_digest_mismatches() -> None:
    rows, manifest = load_valid("twse")
    mismatched = replace(rows[0], partition_id="different-partition")

    report = validate_partition(manifest, (rows[0], mismatched))
    codes = {issue.code for issue in report.issues}

    assert not report.is_valid
    assert "DUPLICATE_SYMBOL" in codes
    assert "PARTITION_ID_MISMATCH" in codes
    assert "NORMALIZED_ROW_COUNT_MISMATCH" in codes
    assert "NORMALIZED_DIGEST_MISMATCH" in codes


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("retrieved_at", "RETRIEVED_AT_MISMATCH"),
        ("first_observed_at", "FIRST_OBSERVED_AT_MISMATCH"),
    ],
)
def test_partition_reports_row_observation_time_mismatch(
    field: str,
    code: str,
) -> None:
    rows, manifest = load_valid("twse")
    mismatched = replace(
        rows[0], **{field: getattr(rows[0], field) - timedelta(minutes=1)}
    )

    report = validate_partition(manifest, (mismatched,))

    assert code in {issue.code for issue in report.issues}


def test_empty_partition_fails_closed() -> None:
    _, manifest = load_valid("twse")

    report = validate_partition(manifest, ())

    assert not report.is_valid
    assert "EMPTY_PARTITION" in {issue.code for issue in report.issues}


def scope(
    scope_id: str,
    *,
    include_block: bool,
    correction_policy: CorrectionPolicy = CorrectionPolicy.ORIGINAL_TRADES,
) -> TradeScope:
    included = {
        TradeCategory.REGULAR,
        TradeCategory.ODD_LOT,
        TradeCategory.AFTER_HOURS_FIXED_PRICE,
    }
    if include_block:
        included.add(TradeCategory.BLOCK)
    return TradeScope(
        scope_id=scope_id,
        included_categories=frozenset(included),
        excluded_categories=frozenset(set(TradeCategory) - included),
        correction_policy=correction_policy,
    )


def test_scope_compatibility_is_explicit_and_fail_closed() -> None:
    numerator = scope("TWSE_T86_FINAL_WITH_BLOCK_V1", include_block=True)
    compatible_denominator = scope("OFFICIAL_VOLUME_FINAL_V1", include_block=True)
    no_block_denominator = scope("OFFICIAL_VOLUME_NO_BLOCK_V1", include_block=False)
    corrected_denominator = scope(
        "OFFICIAL_VOLUME_CORRECTED_V1",
        include_block=True,
        correction_policy=CorrectionPolicy.CORRECTED_ACCOUNTS,
    )

    assert (
        assess_trade_scope_compatibility(numerator, compatible_denominator).status
        is ScopeCompatibility.COMPATIBLE
    )
    assert (
        assess_trade_scope_compatibility(numerator, no_block_denominator).status
        is ScopeCompatibility.SCOPE_INCOMPATIBLE
    )
    assert (
        assess_trade_scope_compatibility(numerator, corrected_denominator).status
        is ScopeCompatibility.SCOPE_INCOMPATIBLE
    )
    assert (
        assess_trade_scope_compatibility(numerator, None).status
        is ScopeCompatibility.UNKNOWN
    )
