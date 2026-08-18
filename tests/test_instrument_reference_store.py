from datetime import date
from decimal import Decimal

import pytest

from market_data.events import InstrumentReference
from market_data.instrument_reference import InstrumentReferenceStore


SESSION_DATE = date(2026, 8, 18)


def reference(
    *,
    symbol: str = "8039",
    session_date: date = SESSION_DATE,
    source_updated_at: date | None = SESSION_DATE,
) -> InstrumentReference:
    return InstrumentReference(
        symbol=symbol,
        exchange="TSE",
        session_date=session_date,
        reference_price=Decimal("258.5"),
        limit_up_price=Decimal("284.5"),
        limit_down_price=Decimal("232.5"),
        price_limit_applies=True,
        trading_unit_shares=1000,
        source_updated_at=source_updated_at,
    )


def test_reference_store_requires_current_session_and_clears_on_rollover():
    store = InstrumentReferenceStore(SESSION_DATE)
    store.put(reference())

    assert store.eligible("8039") is True
    first_digest = store.digest

    next_date = date(2026, 8, 19)
    store.begin_session(next_date)

    assert store.get("8039") is None
    assert store.digest != first_digest
    with pytest.raises(ValueError, match="session mismatch"):
        store.put(reference())


def test_reference_store_preserves_unverified_update_but_marks_it_ineligible():
    store = InstrumentReferenceStore(SESSION_DATE)
    store.put(reference(source_updated_at=None))

    assert store.get("8039") is not None
    assert store.eligible("8039") is False


def test_reference_digest_is_independent_of_insertion_order():
    first = InstrumentReferenceStore(SESSION_DATE)
    second = InstrumentReferenceStore(SESSION_DATE)
    references = [reference(symbol="8039"), reference(symbol="2330")]
    for item in references:
        first.put(item)
    for item in reversed(references):
        second.put(item)

    assert first.digest == second.digest
