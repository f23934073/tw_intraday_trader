"""Current-session authoritative instrument-reference projection."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from market_data.events import InstrumentReference


class InstrumentReferenceStore:
    """Never carries contract limits across trading sessions."""

    def __init__(self, session_date: date) -> None:
        self._session_date = session_date
        self._references: dict[str, InstrumentReference] = {}

    @property
    def session_date(self) -> date:
        return self._session_date

    def begin_session(self, session_date: date) -> None:
        if session_date != self._session_date:
            self._session_date = session_date
            self._references.clear()

    def put(self, reference: InstrumentReference) -> None:
        if reference.session_date != self._session_date:
            raise ValueError("instrument reference session mismatch")
        symbol = reference.symbol.strip().upper()
        if symbol != reference.symbol:
            raise ValueError("instrument reference symbol must be normalized")
        self._references[symbol] = reference

    def get(self, symbol: str) -> InstrumentReference | None:
        return self._references.get(symbol.strip().upper())

    def eligible(self, symbol: str) -> bool:
        reference = self.get(symbol)
        return bool(
            reference is not None
            and reference.eligible_for_limit_up_momentum
        )

    def all(self) -> tuple[InstrumentReference, ...]:
        return tuple(self._references[key] for key in sorted(self._references))

    @property
    def digest(self) -> str:
        payload = [
            {
                "symbol": item.symbol,
                "exchange": item.exchange,
                "session_date": item.session_date.isoformat(),
                "reference_price": str(item.reference_price),
                "limit_up_price": (
                    str(item.limit_up_price)
                    if item.limit_up_price is not None
                    else None
                ),
                "limit_down_price": (
                    str(item.limit_down_price)
                    if item.limit_down_price is not None
                    else None
                ),
                "price_limit_applies": item.price_limit_applies,
                "trading_unit_shares": item.trading_unit_shares,
                "source_updated_at": (
                    item.source_updated_at.isoformat()
                    if item.source_updated_at is not None
                    else None
                ),
            }
            for item in self.all()
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
