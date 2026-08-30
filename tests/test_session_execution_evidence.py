import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from market_data.session_evidence import (
    BidAskEvidence,
    GuardHealth,
    InstrumentStatus,
    ServerExecutionEvidenceSnapshot,
    SessionPhase,
    SpecialSessionRegime,
)
from trading.no_overnight import NoOvernightState


NOW = datetime.fromisoformat("2026-08-24T13:25:00+08:00")


def _snapshot(**overrides: object) -> ServerExecutionEvidenceSnapshot:
    values: dict[str, object] = {
        "captured_at": NOW,
        "received_at": datetime.fromisoformat("2026-08-24T13:25:00.010000+08:00"),
        "calendar_schema_version": "twse-calendar-v1",
        "calendar_digest": "a" * 64,
        "calendar_coverage_start": date(2026, 1, 1),
        "calendar_coverage_end": date(2026, 12, 31),
        "session_date": date(2026, 8, 24),
        "session_phase": SessionPhase.CONTINUOUS,
        "symbol": "2330",
        "instrument_status": InstrumentStatus.TRADING,
        "tradable": True,
        "pit_reference_price": Decimal("100"),
        "pit_lower_limit_price": Decimal("90"),
        "pit_upper_limit_price": Decimal("110"),
        "pit_price_as_of": NOW,
        "special_session_regime": SpecialSessionRegime.NORMAL,
        "bid_ask": BidAskEvidence(
            source_as_of=NOW,
            received_at=NOW,
            best_bid_price=Decimal("99.5"),
            best_bid_quantity=5,
            best_ask_price=Decimal("100"),
            best_ask_quantity=8,
        ),
        "executable_book_policy_id": "provisional-book-v1",
        "book_staleness_policy_id": "provisional-age-v1",
        "max_book_age_milliseconds": 1250,
        "isolated_auction_event_id": None,
        "isolated_auction_event_at": None,
        "isolated_auction_price": None,
        "isolated_auction_matchable_volume": None,
        "isolated_auction_volume_unit": None,
        "isolated_auction_event_digest": None,
        "execution_policy_digest": "b" * 64,
        "cost_policy_digest": "c" * 64,
        "no_overnight_state": NoOvernightState.AGGRESSIVE_EXIT,
        "no_overnight_revision": 4,
        "breach_latched": False,
        "guard_identity": "guard-local-paper-main-v1",
        "guard_health": GuardHealth.HEALTHY,
    }
    values.update(overrides)
    return ServerExecutionEvidenceSnapshot(**values)


def test_snapshot_is_canonical_immutable_and_digest_stable() -> None:
    first = _snapshot()
    second = _snapshot()
    assert first.digest == second.digest
    assert json.dumps(first.canonical_payload(), sort_keys=True)
    assert first.canonical_payload()["bid_ask"]["best_bid_price"] == "99.5"
    with pytest.raises(Exception):
        first.symbol = "2317"  # type: ignore[misc]


def test_unknown_source_is_representable_and_fail_closed_inputs_stay_null() -> None:
    unknown = _snapshot(
        instrument_status=InstrumentStatus.UNKNOWN,
        tradable=None,
        special_session_regime=SpecialSessionRegime.UNKNOWN,
        bid_ask=None,
        executable_book_policy_id=None,
        book_staleness_policy_id=None,
        max_book_age_milliseconds=None,
        execution_policy_digest=None,
        cost_policy_digest=None,
        guard_identity=None,
        guard_health=GuardHealth.UNKNOWN,
    )
    assert unknown.canonical_payload()["tradable"] is None
    assert unknown.canonical_payload()["bid_ask"] is None


def test_partial_auction_or_book_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="auction evidence"):
        _snapshot(isolated_auction_event_id="auction-1")
    with pytest.raises(ValueError, match="present together"):
        _snapshot(executable_book_policy_id=None)
    with pytest.raises(ValueError, match="breach latch"):
        _snapshot(breach_latched=True)
