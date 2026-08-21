"""Manifest-validated immutable market-data replay adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from market_data.clock import ReplayClock
from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.health import DataHealth, DataHealthSnapshot
from market_data.ingestion import IngestResult, MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore


REPLAY_SCHEMA_VERSION = "momentum-replay-v1"
TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class ReplayManifest:
    schema_version: str
    dataset_id: str
    session_id: str
    session_date: date
    timezone: str
    content_sha256: str
    row_count: int


@dataclass(frozen=True)
class ReplayDataset:
    manifest: ReplayManifest
    references: tuple[InstrumentReference, ...]
    events: tuple[EventEnvelope, ...]


@dataclass(frozen=True)
class ReplayRunResult:
    dataset_id: str
    content_sha256: str
    event_count: int
    ingest_results: tuple[IngestResult, ...]
    reference_digest: str
    bar_digest: str
    book_digest: str
    health: DataHealthSnapshot
    digest: str


class ReplayDatasetLoader:
    def load(self, path: Path) -> ReplayDataset:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("replay dataset root must be an object")
        manifest = self._manifest(raw)
        references_raw = self._object_list(raw, "references")
        events_raw = self._object_list(raw, "events")
        if len(events_raw) != manifest.row_count:
            raise ValueError("replay manifest row_count mismatch")
        actual_hash = content_sha256(references_raw, events_raw)
        if actual_hash != manifest.content_sha256:
            raise ValueError("replay manifest content_sha256 mismatch")

        references = tuple(
            self._reference(item, manifest.session_date)
            for item in references_raw
        )
        known_symbols = {item.symbol for item in references}
        events = tuple(
            self._event(item, index, manifest)
            for index, item in enumerate(events_raw)
        )
        if any(event.symbol not in known_symbols for event in events):
            raise ValueError("replay event has no instrument reference")
        if any(
            current.received_at < previous.received_at
            for previous, current in zip(events, events[1:])
        ):
            raise ValueError("replay rows must be ordered by received_at")
        return ReplayDataset(manifest, references, events)

    @staticmethod
    def _manifest(raw: Mapping[str, object]) -> ReplayManifest:
        schema_version = str(raw.get("schema_version", ""))
        if schema_version != REPLAY_SCHEMA_VERSION:
            raise ValueError("unsupported replay schema_version")
        timezone_name = str(raw.get("timezone", ""))
        if timezone_name != "Asia/Taipei":
            raise ValueError("replay timezone must be Asia/Taipei")
        content_hash = str(raw.get("content_sha256", ""))
        if len(content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in content_hash
        ):
            raise ValueError("replay content_sha256 must be a SHA-256 hex digest")
        raw_row_count = raw.get("row_count")
        if (
            isinstance(raw_row_count, bool)
            or not isinstance(raw_row_count, int)
            or raw_row_count < 0
        ):
            raise ValueError("replay row_count must be non-negative")
        dataset_id = str(raw.get("dataset_id", "")).strip()
        session_id = str(raw.get("session_id", "")).strip()
        if not dataset_id or not session_id:
            raise ValueError("replay dataset_id and session_id must not be empty")
        return ReplayManifest(
            schema_version=schema_version,
            dataset_id=dataset_id,
            session_id=session_id,
            session_date=date.fromisoformat(str(raw.get("session_date", ""))),
            timezone=timezone_name,
            content_sha256=content_hash,
            row_count=raw_row_count,
        )

    @staticmethod
    def _object_list(
        raw: Mapping[str, object],
        field_name: str,
    ) -> list[Mapping[str, object]]:
        value = raw.get(field_name)
        if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value
        ):
            raise ValueError(f"replay {field_name} must be a list of objects")
        return value

    @staticmethod
    def _reference(
        raw: Mapping[str, object],
        session_date: date,
    ) -> InstrumentReference:
        return InstrumentReference(
            symbol=str(raw["symbol"]),
            exchange=str(raw["exchange"]),
            session_date=session_date,
            reference_price=Decimal(str(raw["reference_price"])),
            limit_up_price=(
                Decimal(str(raw["limit_up_price"]))
                if raw.get("limit_up_price") is not None
                else None
            ),
            limit_down_price=(
                Decimal(str(raw["limit_down_price"]))
                if raw.get("limit_down_price") is not None
                else None
            ),
            price_limit_applies=bool(raw["price_limit_applies"]),
            trading_unit_shares=int(raw["trading_unit_shares"]),
            source_updated_at=(
                date.fromisoformat(str(raw["source_updated_at"]))
                if raw.get("source_updated_at") is not None
                else None
            ),
        )

    @staticmethod
    def _event(
        raw: Mapping[str, object],
        index: int,
        manifest: ReplayManifest,
    ) -> EventEnvelope:
        event_id = f"{manifest.content_sha256}:{index}"
        event_at = _parse_taipei_datetime(raw["event_at"])
        received_at = _parse_taipei_datetime(raw["received_at"])
        symbol = str(raw["symbol"])
        sequence = int(raw["ingress_sequence"])
        kind = MarketStreamKind(str(raw["kind"]))
        if event_at.date() != manifest.session_date:
            raise ValueError("replay event_at does not match session_date")

        if kind is MarketStreamKind.TICK:
            payload = TickEvent(
                event_id=event_id,
                source=MarketEventSource.REPLAY,
                symbol=symbol,
                session_date=manifest.session_date,
                event_time=event_at,
                received_at=received_at,
                ingress_sequence=sequence,
                price=Decimal(str(raw["price"])),
                tick_volume_lots=int(raw["tick_volume_lots"]),
                total_volume_lots=int(raw["total_volume_lots"]),
                average_price=(
                    Decimal(str(raw["average_price"]))
                    if raw.get("average_price") is not None
                    else None
                ),
                intraday_high=Decimal(str(raw["intraday_high"])),
                intraday_low=Decimal(str(raw["intraday_low"])),
                raw_tick_type=int(raw["raw_tick_type"]),
                aggressor_side=AggressorSide(str(raw["aggressor_side"])),
                buy_aggressor_total_lots=_optional_int(
                    raw.get("buy_aggressor_total_lots")
                ),
                sell_aggressor_total_lots=_optional_int(
                    raw.get("sell_aggressor_total_lots")
                ),
                suspended=bool(raw.get("suspended", False)),
                simulated_trade=bool(raw.get("simulated_trade", False)),
                intraday_odd=bool(raw.get("intraday_odd", False)),
            )
        else:
            payload = BidAskEvent(
                event_id=event_id,
                source=MarketEventSource.REPLAY,
                symbol=symbol,
                session_date=manifest.session_date,
                event_time=event_at,
                received_at=received_at,
                ingress_sequence=sequence,
                bid_prices=tuple(
                    Decimal(str(value)) for value in raw.get("bid_prices", ())
                ),
                bid_volume_lots=tuple(
                    int(value) for value in raw.get("bid_volume_lots", ())
                ),
                ask_prices=tuple(
                    Decimal(str(value)) for value in raw.get("ask_prices", ())
                ),
                ask_volume_lots=tuple(
                    int(value) for value in raw.get("ask_volume_lots", ())
                ),
                suspended=bool(raw.get("suspended", False)),
                simulated_trade=bool(raw.get("simulated_trade", False)),
                intraday_odd=bool(raw.get("intraday_odd", False)),
            )
        return EventEnvelope(
            event_id=event_id,
            schema_version=MARKET_EVENT_SCHEMA_VERSION,
            session_id=manifest.session_id,
            session_date=manifest.session_date,
            source=MarketEventSource.REPLAY,
            source_mode="IMMUTABLE_DATASET",
            stream_kind=kind,
            symbol=symbol,
            event_at=event_at,
            received_at=received_at,
            ingress_sequence=sequence,
            source_identity=f"{manifest.content_sha256}:{index}",
            payload=payload,
            raw_capture_id=manifest.dataset_id,
        )


class ReplayRunner:
    def __init__(self, *, retention: timedelta = timedelta(minutes=20)) -> None:
        self._retention = retention

    def run(self, dataset: ReplayDataset) -> ReplayRunResult:
        start_at = (
            dataset.events[0].received_at
            if dataset.events
            else datetime.combine(
                dataset.manifest.session_date,
                time(9, 0),
                tzinfo=TAIPEI,
            )
        )
        clock = ReplayClock(start_at)
        references = InstrumentReferenceStore(dataset.manifest.session_date)
        for reference in dataset.references:
            references.put(reference)
        bars = IntradayBarStore(
            dataset.manifest.session_date,
            retention=self._retention,
        )
        books = OrderBookStore(
            dataset.manifest.session_date,
            retention=self._retention,
        )
        health = DataHealth(dataset.manifest.session_date, started_at=start_at)
        health.mark_ready(
            occurred_at=start_at,
            evidence="manifest_hash_and_references_validated",
        )
        ingestor = MarketDataIngestor(
            session_id=dataset.manifest.session_id,
            session_date=dataset.manifest.session_date,
            references=references,
            bars=bars,
            books=books,
            health=health,
        )

        results: list[IngestResult] = []
        for envelope in dataset.events:
            clock.sleep_until(envelope.received_at)
            results.append(ingestor.ingest(envelope))

        reference_digest = references.digest
        bar_digest = bars.finalize_session()
        book_digest = books.finalize_session()
        health_snapshot = health.snapshot()
        digest_payload = {
            "dataset_id": dataset.manifest.dataset_id,
            "content_sha256": dataset.manifest.content_sha256,
            "clock_now": clock.now().isoformat(),
            "results": [
                {
                    "status": item.status.value,
                    "event_id": item.event_id,
                    "symbol": item.symbol,
                    "stream_kind": item.stream_kind.value,
                    "projection_applied": item.projection_applied,
                    "reason": item.reason,
                }
                for item in results
            ],
            "reference_digest": reference_digest,
            "bar_digest": bar_digest,
            "book_digest": book_digest,
            "health_digest": health_snapshot.digest,
        }
        digest = hashlib.sha256(
            json.dumps(
                digest_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return ReplayRunResult(
            dataset_id=dataset.manifest.dataset_id,
            content_sha256=dataset.manifest.content_sha256,
            event_count=len(dataset.events),
            ingest_results=tuple(results),
            reference_digest=reference_digest,
            bar_digest=bar_digest,
            book_digest=book_digest,
            health=health_snapshot,
            digest=digest,
        )


def content_sha256(
    references: list[Mapping[str, object]],
    events: list[Mapping[str, object]],
) -> str:
    payload = {"references": references, "events": events}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _parse_taipei_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("replay timestamps must be timezone-aware")
    normalized = parsed.astimezone(TAIPEI)
    if parsed.utcoffset() != normalized.utcoffset():
        raise ValueError("replay timestamps must use Asia/Taipei offset")
    return normalized


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
