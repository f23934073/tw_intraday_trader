from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime

import pytest

from institutional_data.domain import (
    CorrectionPolicy,
    InstitutionalFlowDaily,
    InstitutionalMarket,
    InstitutionalPartitionManifest,
    PartitionStatus,
    ScopeCompatibility,
    ScopeCompatibilityDecision,
    TradeCategory,
    TradeScope,
)


def flow() -> InstitutionalFlowDaily:
    return InstitutionalFlowDaily(
        partition_id="twse-2026-08-19-final",
        market=InstitutionalMarket.TWSE,
        symbol=" 2330 ",
        session_date=date(2026, 8, 19),
        foreign_ex_dealer_buy_shares=10_000,
        foreign_ex_dealer_sell_shares=4_000,
        foreign_ex_dealer_net_shares=6_000,
        foreign_dealer_buy_shares=500,
        foreign_dealer_sell_shares=200,
        foreign_dealer_net_shares=300,
        investment_trust_buy_shares=3_000,
        investment_trust_sell_shares=1_000,
        investment_trust_net_shares=2_000,
        dealer_proprietary_buy_shares=2_000,
        dealer_proprietary_sell_shares=1_000,
        dealer_proprietary_net_shares=1_000,
        dealer_hedge_buy_shares=1_500,
        dealer_hedge_sell_shares=500,
        dealer_hedge_net_shares=1_000,
        dealer_total_buy_shares=3_500,
        dealer_total_sell_shares=1_500,
        dealer_total_net_shares=2_000,
        published_total_net_shares=10_000,
        trade_scope_id="TWSE_T86_FINAL_WITH_BLOCK_V1",
        correction_policy=CorrectionPolicy.ORIGINAL_TRADES,
        raw_artifact_id="twse-t86-2026-08-19-final",
        raw_sha256="a" * 64,
        retrieved_at=datetime.fromisoformat("2026-08-19T20:10:00+08:00"),
        first_observed_at=datetime.fromisoformat("2026-08-19T20:05:00+08:00"),
        usable_from_session=date(2026, 8, 20),
    )


def manifest() -> InstitutionalPartitionManifest:
    return InstitutionalPartitionManifest(
        partition_id="twse-2026-08-19-final",
        market=InstitutionalMarket.TWSE,
        session_date=date(2026, 8, 19),
        source_product="TWSE_T86_FINAL",
        trade_scope_id="TWSE_T86_FINAL_WITH_BLOCK_V1",
        correction_policy=CorrectionPolicy.ORIGINAL_TRADES,
        response_scope_note="Reviewed final scope.",
        raw_artifact_id="twse-t86-2026-08-19-final",
        raw_sha256="a" * 64,
        normalized_sha256="b" * 64,
        retrieved_at=datetime.fromisoformat("2026-08-19T20:10:00+08:00"),
        first_observed_at=datetime.fromisoformat("2026-08-19T20:05:00+08:00"),
        usable_from_session=date(2026, 8, 20),
        source_row_count=1,
        normalized_row_count=1,
        status=PartitionStatus.NORMALIZED,
    )


def test_flow_and_manifest_are_immutable_and_normalize_identity() -> None:
    row = flow()

    assert row.symbol == "2330"
    assert row.market is InstitutionalMarket.TWSE
    assert manifest().status is PartitionStatus.NORMALIZED
    with pytest.raises(FrozenInstanceError):
        row.symbol = "2317"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"foreign_ex_dealer_buy_shares": -1}, "non-negative"),
        ({"foreign_ex_dealer_buy_shares": True}, "integer"),
        ({"raw_sha256": "not-a-digest"}, "SHA256"),
        ({"retrieved_at": datetime(2026, 8, 19, 20, 10)}, "timezone"),
        ({"usable_from_session": date(2026, 8, 19)}, "after session_date"),
        ({"foreign_dealer_buy_shares": None}, "all present or all absent"),
    ],
)
def test_flow_rejects_structurally_invalid_values(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(flow(), **changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source_product": ""}, "source_product"),
        ({"normalized_row_count": -1}, "non-negative"),
        ({"normalized_sha256": "A" * 64}, "SHA256"),
        (
            {
                "first_observed_at": datetime(
                    2026, 8, 19, 20, 11, tzinfo=manifest().retrieved_at.tzinfo
                )
            },
            "first_observed_at",
        ),
    ],
)
def test_manifest_rejects_structurally_invalid_values(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(manifest(), **changes)


def test_trade_scope_requires_a_complete_non_overlapping_category_partition() -> None:
    included = frozenset(
        {
            TradeCategory.REGULAR,
            TradeCategory.ODD_LOT,
            TradeCategory.AFTER_HOURS_FIXED_PRICE,
            TradeCategory.BLOCK,
        }
    )
    scope = TradeScope(
        scope_id="TWSE_T86_FINAL_WITH_BLOCK_V1",
        included_categories=included,
        excluded_categories=frozenset({TradeCategory.AUCTION, TradeCategory.TENDER}),
        correction_policy=CorrectionPolicy.ORIGINAL_TRADES,
    )

    assert scope.included_categories == included
    with pytest.raises(ValueError, match="exactly once"):
        replace(scope, excluded_categories=frozenset({TradeCategory.AUCTION}))
    with pytest.raises(ValueError, match="overlap"):
        replace(
            scope,
            excluded_categories=frozenset(
                {TradeCategory.BLOCK, TradeCategory.AUCTION, TradeCategory.TENDER}
            ),
        )


@pytest.mark.parametrize(
    ("status", "reason_codes"),
    [
        (ScopeCompatibility.COMPATIBLE, ("MISMATCH",)),
        (ScopeCompatibility.SCOPE_INCOMPATIBLE, ()),
    ],
)
def test_scope_compatibility_decision_rejects_contradictory_state(
    status: ScopeCompatibility,
    reason_codes: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="scope compatibility"):
        ScopeCompatibilityDecision(
            status=status,
            numerator_scope_id="NUMERATOR",
            denominator_scope_id="DENOMINATOR",
            reason_codes=reason_codes,
        )
