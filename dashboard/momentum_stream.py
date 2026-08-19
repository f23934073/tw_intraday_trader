"""Cursor-safe, bounded fan-out for the realtime Momentum dashboard."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from threading import Condition, Event, Lock, RLock, Thread
from time import monotonic
from typing import Any, Mapping, Protocol
from uuid import uuid4

from config.momentum_stream import MomentumStreamConfig


SCHEMA_VERSION = "momentum_dashboard_stream_v1"
RESUME_PATH = "/ws/dashboard/momentum"


class MomentumSnapshotService(Protocol):
    def snapshot(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class StreamReplay:
    events: tuple[dict[str, Any], ...] = ()
    reason: str | None = None
    current_revision: int = 0


class MomentumStreamHub:
    """Cache complete snapshots and replay bounded projection deltas.

    The watcher reads the already-computed dashboard projection at a bounded
    cadence. Provider callbacks never serialize JSON or perform socket I/O.
    Clients independently replay from the shared ring, so a slow client cannot
    grow an unbounded per-client queue.
    """

    def __init__(
        self,
        service: MomentumSnapshotService,
        *,
        config: MomentumStreamConfig,
    ) -> None:
        self._service = service
        self._config = config
        self._stream_id = uuid4().hex
        self._condition = Condition(RLock())
        self._start_lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._started = False
        self._closed = False
        self._revision = 0
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_digest: str | None = None
        self._generated_at: str | None = None
        self._events: deque[dict[str, Any]] = deque(
            maxlen=config.replay_capacity
        )
        self._last_error: str | None = None
        self._client_count = 0

    @property
    def service(self) -> MomentumSnapshotService:
        return self._service

    @property
    def config(self) -> MomentumStreamConfig:
        return self._config

    def start(self) -> None:
        with self._start_lock:
            if self._closed:
                raise RuntimeError("Momentum stream hub is closed")
            if self._started:
                return
            self._publish_snapshot(self._service.snapshot())
            self._started = True
            self._thread = Thread(
                target=self._watch_loop,
                name="momentum-dashboard-stream",
                daemon=True,
            )
            self._thread.start()

    def bootstrap(self) -> dict[str, Any]:
        self.start()
        with self._condition:
            assert self._snapshot is not None
            payload = deepcopy(self._snapshot)
            payload["stream"] = self._stream_metadata_locked()
            return payload

    def capture_now(self, snapshot: Mapping[str, Any] | None = None) -> bool:
        self.start()
        candidate = self._service.snapshot() if snapshot is None else snapshot
        return self._publish_snapshot(candidate)

    def events_after(self, stream_id: str, revision: int) -> StreamReplay:
        with self._condition:
            return self._events_after_locked(stream_id, revision)

    def wait_for_events(
        self,
        stream_id: str,
        revision: int,
        *,
        timeout: float,
    ) -> StreamReplay:
        deadline = monotonic() + timeout
        with self._condition:
            while True:
                replay = self._events_after_locked(stream_id, revision)
                if replay.reason is not None or replay.events:
                    return replay
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return replay
                self._condition.wait(remaining)

    def ready_message(self) -> dict[str, Any]:
        self.start()
        with self._condition:
            return {
                "schema_version": SCHEMA_VERSION,
                "type": "ready",
                "stream_id": self._stream_id,
                "current_revision": self._revision,
                "heartbeat_seconds": self._config.heartbeat_seconds,
            }

    def heartbeat_message(self) -> dict[str, Any]:
        with self._condition:
            return {
                "schema_version": SCHEMA_VERSION,
                "type": "heartbeat",
                "stream_id": self._stream_id,
                "revision": self._revision,
                "sent_at": _now_iso(),
            }

    def resync_message(self, reason: str) -> dict[str, Any]:
        with self._condition:
            return {
                "schema_version": SCHEMA_VERSION,
                "type": "resync_required",
                "reason": reason,
                "stream_id": self._stream_id,
                "current_revision": self._revision,
            }

    def try_register_client(self) -> bool:
        with self._condition:
            if self._closed or self._client_count >= self._config.max_clients:
                return False
            self._client_count += 1
            return True

    def unregister_client(self) -> None:
        with self._condition:
            self._client_count = max(0, self._client_count - 1)

    def close(self) -> None:
        with self._start_lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            with self._condition:
                self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, self._config.send_timeout_seconds))
            if thread.is_alive():
                raise RuntimeError("Momentum stream watcher did not stop")

    def _watch_loop(self) -> None:
        while not self._stop.wait(self._config.coalesce_seconds):
            try:
                self._publish_snapshot(self._service.snapshot())
                with self._condition:
                    self._last_error = None
            except Exception as error:
                with self._condition:
                    self._last_error = str(error)

    def _publish_snapshot(self, snapshot: Mapping[str, Any]) -> bool:
        prepared = _prepare_snapshot(snapshot)
        digest = _digest(prepared)
        generated_at = _now_iso()
        with self._condition:
            if self._closed:
                return False
            if digest == self._snapshot_digest:
                return False
            previous = self._snapshot
            base_revision = self._revision
            self._revision += 1
            self._snapshot = prepared
            self._snapshot_digest = digest
            self._generated_at = generated_at
            if previous is not None:
                self._events.append(
                    _build_delta(
                        previous,
                        prepared,
                        stream_id=self._stream_id,
                        base_revision=base_revision,
                        revision=self._revision,
                        emitted_at=generated_at,
                    )
                )
            self._condition.notify_all()
            return True

    def _events_after_locked(
        self,
        stream_id: str,
        revision: int,
    ) -> StreamReplay:
        current = self._revision
        if self._closed:
            return StreamReplay(reason="SERVER_SHUTDOWN", current_revision=current)
        if stream_id != self._stream_id:
            return StreamReplay(reason="STREAM_CHANGED", current_revision=current)
        if revision < 0 or revision > current:
            return StreamReplay(reason="INVALID_CURSOR", current_revision=current)
        if revision == current:
            return StreamReplay(current_revision=current)
        if not self._events or revision < self._events[0]["base_revision"]:
            return StreamReplay(
                reason="REVISION_TOO_OLD",
                current_revision=current,
            )
        events = tuple(
            deepcopy(event)
            for event in self._events
            if event["revision"] > revision
        )
        return StreamReplay(events=events, current_revision=current)

    def _stream_metadata_locked(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "enabled": self._config.enabled,
            "stream_id": self._stream_id,
            "revision": self._revision,
            "generated_at": self._generated_at,
            "resume_path": RESUME_PATH,
            "heartbeat_seconds": self._config.heartbeat_seconds,
            "last_error": self._last_error,
        }


def _prepare_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(dict(snapshot))
    prepared.pop("stream", None)
    items = prepared.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Momentum snapshot items must be a list")
    symbols: set[str] = set()
    prepared_items: list[dict[str, Any]] = []
    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            raise ValueError("Momentum snapshot item must be an object")
        item = deepcopy(dict(raw_item))
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("Momentum snapshot item symbol must not be empty")
        if symbol in symbols:
            raise ValueError(f"Duplicate Momentum snapshot symbol: {symbol}")
        symbols.add(symbol)
        item["symbol"] = symbol
        item.pop("item_digest", None)
        item["item_digest"] = _digest(item)
        prepared_items.append(item)
    prepared["items"] = prepared_items
    return prepared


def _build_delta(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    stream_id: str,
    base_revision: int,
    revision: int,
    emitted_at: str,
) -> dict[str, Any]:
    previous_items = {
        item["symbol"]: item for item in previous.get("items", [])
    }
    current_items = {
        item["symbol"]: item for item in current.get("items", [])
    }
    ordered_symbols = list(current_items)
    upserts = [
        deepcopy(item)
        for symbol, item in current_items.items()
        if previous_items.get(symbol, {}).get("item_digest")
        != item.get("item_digest")
    ]
    removed = [
        symbol for symbol in previous_items if symbol not in current_items
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "delta",
        "stream_id": stream_id,
        "base_revision": base_revision,
        "revision": revision,
        "emitted_at": emitted_at,
        "status": current.get("status"),
        "mode": current.get("mode"),
        "source": deepcopy(current.get("source", {})),
        "summary": deepcopy(current.get("summary", {})),
        "item_upserts": upserts,
        "removed_symbols": removed,
        "ordered_symbols": ordered_symbols,
        "alerts": deepcopy(current.get("alerts", [])),
        "disclaimer": current.get("disclaimer"),
        "notice": current.get("notice"),
        "projection_digest": current.get("summary", {}).get(
            "projection_digest"
        ),
    }


def _digest(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()
