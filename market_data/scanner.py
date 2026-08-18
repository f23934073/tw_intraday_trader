"""Low-frequency market Scanner contracts and Shioaji adapter.

Scanner rows are discovery evidence only.  They must not be reused as
realtime Momentum features after a symbol enters the subscribed universe.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence


class ScannerRankType(StrEnum):
    CHANGE_PERCENT = "CHANGE_PERCENT"
    VOLUME = "VOLUME"
    AMOUNT = "AMOUNT"
    TICK_COUNT = "TICK_COUNT"


@dataclass(frozen=True)
class ScannerRow:
    symbol: str
    rank: int
    fields: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("scanner row symbol must not be empty")
        if self.rank <= 0:
            raise ValueError("scanner row rank must be positive")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "fields", _freeze_mapping(self.fields))


@dataclass(frozen=True)
class ScannerResponse:
    rank_type: ScannerRankType
    observed_at: datetime
    ascending: bool
    requested_count: int
    rows: tuple[ScannerRow, ...]

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("scanner observed_at must be timezone-aware")
        if not 1 <= self.requested_count <= 200:
            raise ValueError("scanner requested_count must be between 1 and 200")
        object.__setattr__(self, "rows", tuple(self.rows))

    @property
    def digest(self) -> str:
        payload = {
            "rank_type": self.rank_type.value,
            "observed_at": self.observed_at.isoformat(),
            "ascending": self.ascending,
            "requested_count": self.requested_count,
            "rows": [
                {
                    "symbol": row.symbol,
                    "rank": row.rank,
                    "fields": _json_safe_mapping(row.fields),
                }
                for row in self.rows
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class ScannerClient(Protocol):
    def scan(
        self,
        rank_type: ScannerRankType,
        *,
        count: int,
        ascending: bool,
    ) -> ScannerResponse: ...


class ShioajiScannerClient:
    """Defensive adapter around the installed Shioaji Scanner API.

    The adapter intentionally owns no polling cadence.  Its caller must supply
    a reviewed scheduler/cache policy before this is connected to a runtime.
    """

    _FIELD_NAMES = (
        "code",
        "name",
        "ts",
        "open",
        "high",
        "low",
        "close",
        "change_price",
        "change_rate",
        "change_percent",
        "average_price",
        "volume",
        "total_volume",
        "amount",
        "total_amount",
        "tick_type",
        "tick_count",
        "buy_price",
        "buy_volume",
        "sell_price",
        "sell_volume",
    )

    def __init__(
        self,
        api: object,
        *,
        clock: Callable[[], datetime],
        native_rank_types: Mapping[ScannerRankType, object] | None = None,
    ) -> None:
        self._api = api
        self._clock = clock
        self._native_rank_types = dict(
            native_rank_types or self._load_native_rank_types()
        )

    def scan(
        self,
        rank_type: ScannerRankType,
        *,
        count: int,
        ascending: bool = False,
    ) -> ScannerResponse:
        if not 1 <= count <= 200:
            raise ValueError("Shioaji Scanner count must be between 1 and 200")
        try:
            native_type = self._native_rank_types[rank_type]
        except KeyError as error:
            raise ValueError(f"unsupported Scanner rank type: {rank_type}") from error

        raw_rows = self._api.scanners(
            scanner_type=native_type,
            ascending=ascending,
            count=count,
        )
        observed_at = self._clock()
        if observed_at.tzinfo is None:
            raise ValueError("scanner clock must return a timezone-aware datetime")

        rows: list[ScannerRow] = []
        for index, raw_row in enumerate(raw_rows or (), start=1):
            fields = self._row_fields(raw_row)
            symbol = str(fields.get("code") or fields.get("symbol") or "")
            if not symbol.strip():
                continue
            rows.append(ScannerRow(symbol=symbol, rank=index, fields=fields))

        return ScannerResponse(
            rank_type=rank_type,
            observed_at=observed_at,
            ascending=ascending,
            requested_count=count,
            rows=tuple(rows),
        )

    @staticmethod
    def _load_native_rank_types() -> Mapping[ScannerRankType, object]:
        try:
            import shioaji as sj  # type: ignore[import]
        except ImportError as error:
            raise ImportError(
                "shioaji is required to construct ShioajiScannerClient"
            ) from error

        return {
            ScannerRankType.CHANGE_PERCENT: sj.ScannerType.ChangePercentRank,
            ScannerRankType.VOLUME: sj.ScannerType.VolumeRank,
            ScannerRankType.AMOUNT: sj.ScannerType.AmountRank,
            ScannerRankType.TICK_COUNT: sj.ScannerType.TickCountRank,
        }

    @classmethod
    def _row_fields(cls, row: object) -> dict[str, object]:
        if isinstance(row, Mapping):
            source = dict(row)
        else:
            source = {}
            for dump_name in ("model_dump", "dict"):
                dump = getattr(row, dump_name, None)
                if callable(dump):
                    try:
                        value = dump()
                    except Exception:
                        continue
                    if isinstance(value, Mapping):
                        source.update(value)
                        break
            for name in cls._FIELD_NAMES:
                if name not in source and hasattr(row, name):
                    source[name] = getattr(row, name)
        return {
            str(key): _json_safe_value(value)
            for key, value in source.items()
            if value is not None
        }


def _json_safe_mapping(values: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): _json_safe_value(value)
        for key, value in sorted(values.items(), key=lambda item: str(item[0]))
    }


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe_value(item) for item in value]
    return str(value)


def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {str(key): _freeze_value(value) for key, value in values.items()}
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_freeze_value(item) for item in value)
    return value
