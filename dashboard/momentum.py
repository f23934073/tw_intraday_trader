"""Live Momentum Shadow dashboard projection with a deterministic test fixture."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from candidate.models import CandidateSource
from candidate.pool import CandidatePool, CandidatePoolConfig
from candidate.sources import CandidateDiscovery
from config.momentum import MOMENTUM_ENTRY_HYPOTHESIS_V0
from config.momentum import QuoteSubscriptionMode, SubscriptionCapacityConfig
from features.engine import FeatureEngine
from features.models import FeatureEvaluationContext, FeatureValue, IntradayFeatureSnapshot
from market_data.events import TickEvent
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.replay import ReplayDatasetLoader
from market_data.shioaji_momentum_stream import ShioajiMomentumStream
from market_data.subscriptions import SubscriptionManager, SubscriptionPolicy
from runtime.clock import Clock, SystemClock
from runtime.momentum_shadow import (
    MomentumShadowRuntime,
    MomentumShadowRuntimeConfig,
)
from signals.models import (
    EntryOpportunity,
    EvidenceUpdate,
    MomentumEpisode,
    RiskGateStatus,
    SignalDetail,
    StageTransition,
    evaluate_momentum_entry_opportunity,
)
from signals.momentum import MomentumSignalEngine
from signals.momentum_state import MomentumStateMachine
from signals.projection import (
    MomentumAlert,
    MomentumProjection,
    MomentumProjectionStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOMENTUM_REPLAY = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "8039_2026-08-18_phase3_enriched_replay.json"
)
TAIPEI = ZoneInfo("Asia/Taipei")

_STAGE_LABELS = {
    "WATCH": "觀察",
    "STRONG": "強勢",
    "BREAKOUT": "突破",
    "ACCELERATING": "加速",
    "NEAR_LIMIT_UP": "逼近漲停",
    "LIMIT_TOUCHED": "碰觸漲停",
}
_FAMILY_LABELS = {
    "OPENING_MOMENTUM": "開盤動能",
    "LIMIT_UP_MOMENTUM": "漲停加速",
}
_ENTRY_STATUS_LABELS = {
    "WAITING": "等待條件",
    "AVAILABLE": "可評估進場",
    "BLOCKED": "風險條件阻擋",
}
_ALERT_LABELS = {
    "BREAKOUT": "突破前高",
    "ACCELERATING": "強勢突破加速",
    "NEAR_LIMIT_UP": "正在逼近漲停",
    "LIMIT_TOUCHED": "已碰觸漲停",
    "LOCKED": "漲停鎖定",
    "UNLOCKED": "漲停已打開",
    "UNKNOWN": "五檔狀態不明",
    "INVALIDATED": "加速態勢失效",
    "EXPIRED": "加速 episode 到期",
    "DATA_BLOCKED": "行情資料阻擋",
}
_REASON_LABELS = {
    "risk_gate_not_passed": "RiskGate 尚未通過",
    "risk_decision_id_missing": "缺少可稽核的 RiskDecision",
    "episode_not_active": "目前 episode 已結束",
    "acceleration_not_confirmed": "尚未確認加速",
    "signal_family_not_enabled": "目前訊號 family 未開放 Momentum Entry",
}

_REALTIME_AVAILABILITY_LABELS = {
    "EVALUATED": "已評估",
    "CAPACITY_EVICTED": "超過即時訂閱上限",
    "DATA_INCOMPLETE": "等待 Tick／BidAsk 暖機",
    "SUBSCRIPTION_NOT_ACKED": "等待即時訂閱確認",
    "NOT_DISCOVERED": "不在目前候選池",
    "UNAVAILABLE": "暫時無法評估",
}


class RealtimeMomentumDashboardService:
    """Expose every current dashboard candidate through the live Shadow runtime.

    The candidate list remains a bounded snapshot-scanner input. Evidence scores
    are never derived from that snapshot: each score is produced by the paired
    Tick/BidAsk runtime after the symbol is subscribed and warmed up.
    """

    def __init__(
        self,
        runtime: MomentumShadowRuntime,
        *,
        candidate_snapshot_loader: Callable[[], Mapping[str, Any]],
        clock: Clock | None = None,
        candidate_refresh_interval: timedelta = timedelta(seconds=30),
    ) -> None:
        if candidate_refresh_interval <= timedelta(0):
            raise ValueError("candidate_refresh_interval must be positive")
        self._runtime = runtime
        self._candidate_snapshot_loader = candidate_snapshot_loader
        self._clock = clock or SystemClock()
        self._candidate_refresh_interval = candidate_refresh_interval
        self._lock = RLock()
        self._started = False
        self._last_candidate_refresh_at: datetime | None = None
        self._candidate_refresh_error: str | None = None
        self._candidate_metadata: dict[str, dict[str, Any]] = {}
        self._candidate_refresh_in_progress = False
        self._candidate_refresh_stop = Event()
        self._candidate_refresh_worker: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._runtime.start()
            self._started = True
            self._refresh_candidates(force=True)
            self._candidate_refresh_stop.clear()
            self._candidate_refresh_worker = Thread(
                target=self._candidate_refresh_loop,
                name="momentum-candidate-refresh",
                daemon=True,
            )
            self._candidate_refresh_worker.start()

    def snapshot(self) -> dict[str, Any]:
        self.start()
        with self._lock:
            now = self._clock.now()
            runtime_snapshot = self._runtime.snapshot()
            if now.date() == runtime_snapshot.session_date:
                self._runtime.check_staleness(evaluated_at=now)
            read_view = self._runtime.read_view(
                tuple(self._candidate_metadata)
            )
            runtime_snapshot = read_view.snapshot
            projections = dict(read_view.projections)
            books = dict(read_view.books)
            miss_reasons = dict(read_view.miss_reason_by_symbol)

            items = [
                self._serialize_candidate(
                    symbol,
                    projection=projections.get(symbol),
                    book=books.get(symbol),
                    miss_reason=miss_reasons.get(symbol),
                )
                for symbol in self._ordered_candidate_symbols(projections)
            ]
            alerts = [
                _serialize_realtime_alert(alert, self._candidate_metadata)
                for alert in read_view.pending_alerts
            ]
            evaluated_count = sum(
                item["availability"] == "EVALUATED" for item in items
            )
            triggered_count = sum(
                item.get("signal", {}).get("evaluation_status") == "TRIGGERED"
                for item in items
                if item.get("signal") is not None
            )
            source = {
                "name": runtime_snapshot.source_name,
                "is_live": runtime_snapshot.is_live_source,
                "session_id": runtime_snapshot.session_id,
                "session_date": runtime_snapshot.session_date.isoformat(),
                "as_of": runtime_snapshot.health.as_of.isoformat(),
                "connection_state": runtime_snapshot.connection_state.value,
                "data_health": runtime_snapshot.health.state.value,
                "candidate_as_of": _timestamp(self._last_candidate_refresh_at),
                "candidate_refresh_seconds": int(
                    self._candidate_refresh_interval.total_seconds()
                ),
                "candidate_refresh_error": self._candidate_refresh_error,
                "subscription_max_symbols": (
                    runtime_snapshot.subscription_max_symbols
                ),
                "subscriptions_in_use": runtime_snapshot.subscriptions_in_use,
            }
            summary = {
                "candidate_count": len(items),
                "evaluated_candidate_count": evaluated_count,
                "unavailable_candidate_count": len(items) - evaluated_count,
                "triggered_candidate_count": triggered_count,
                "active_episode_count": runtime_snapshot.active_episode_count,
                "pending_alert_count": len(alerts),
            }
            summary["projection_digest"] = _realtime_digest(
                source=source,
                items=items,
                alerts=alerts,
            )
            return {
                "status": (
                    "live"
                    if runtime_snapshot.is_live_source
                    and runtime_snapshot.running
                    else "unavailable"
                ),
                "mode": runtime_snapshot.mode,
                "source": source,
                "summary": summary,
                "items": items,
                "alerts": alerts,
                "disclaimer": (
                    "盤中分數是 Tick／BidAsk 規則證據，不代表漲停機率，"
                    "也不是買進或下單指令。"
                ),
                "notice": (
                    "候選清單每 30 秒由掃描快照更新；已訂閱候選的分數"
                    "則隨 Tick／BidAsk 持續重算。"
                ),
            }

    def symbol(self, symbol: str) -> dict[str, Any]:
        snapshot = self.snapshot()
        normalized = symbol.strip().upper()
        for item in snapshot["items"]:
            if item["symbol"] == normalized:
                return item
        raise KeyError(f"目前 Candidate 清單沒有：{normalized}")

    def acknowledge(self, alert_id: str) -> dict[str, Any]:
        with self._lock:
            self.start()
            self._runtime.acknowledge_alert(
                alert_id,
                acknowledged_at=self._clock.now(),
            )
            return self.snapshot()

    def close(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._candidate_refresh_stop.set()
            worker = self._candidate_refresh_worker
        if worker is not None:
            worker.join(timeout=30)
            if worker.is_alive():
                raise RuntimeError("Momentum candidate refresh worker did not stop")
        with self._lock:
            self._runtime.close()
            self._started = False
            self._candidate_refresh_worker = None

    def _candidate_refresh_loop(self) -> None:
        interval = self._candidate_refresh_interval.total_seconds()
        while not self._candidate_refresh_stop.wait(interval):
            self._refresh_candidates(force=False)

    def _refresh_is_due(self, now: datetime) -> bool:
        return (
            self._last_candidate_refresh_at is None
            or now - self._last_candidate_refresh_at
            >= self._candidate_refresh_interval
        )

    def _refresh_candidates(self, *, force: bool) -> None:
        now = self._clock.now()
        with self._lock:
            if self._candidate_refresh_in_progress:
                return
            if not force and not self._refresh_is_due(now):
                return
            self._candidate_refresh_in_progress = True
        try:
            payload = self._candidate_snapshot_loader()
            candidates = payload.get("candidates", ())
            if not isinstance(candidates, (list, tuple)):
                raise ValueError("Dashboard candidates payload must be a list")
            metadata, discoveries = _dashboard_candidate_discoveries(
                candidates,
                observed_at=now,
                expires_at=now + self._candidate_refresh_interval,
            )
            with self._lock:
                self._runtime.update_candidates(
                    discoveries,
                    evaluated_at=now,
                )
                self._candidate_metadata = metadata
                self._last_candidate_refresh_at = now
                self._candidate_refresh_error = None
        except Exception as error:
            with self._lock:
                self._candidate_refresh_error = str(error)
                self._last_candidate_refresh_at = now
        finally:
            with self._lock:
                self._candidate_refresh_in_progress = False

    def _ordered_candidate_symbols(
        self,
        projections: Mapping[str, MomentumProjection | None],
    ) -> list[str]:
        symbols = set(self._candidate_metadata)

        def sort_key(symbol: str) -> tuple[int, int, str]:
            projection = projections.get(symbol)
            intraday_score = (
                projection.signal_result.evidence_score
                if projection is not None
                else -1
            )
            candidate_score = int(
                self._candidate_metadata.get(symbol, {}).get("candidate_score", 0)
            )
            return (-intraday_score, -candidate_score, symbol)

        return sorted(
            symbols,
            key=sort_key,
        )

    def _serialize_candidate(
        self,
        symbol: str,
        *,
        projection: MomentumProjection | None,
        book: Any = None,
        miss_reason: Any,
    ) -> dict[str, Any]:
        metadata = self._candidate_metadata.get(symbol, {"symbol": symbol})
        if projection is None:
            availability = str(
                getattr(miss_reason, "value", None) or "UNAVAILABLE"
            ).upper()
            return {
                **metadata,
                "availability": availability,
                "availability_label": _REALTIME_AVAILABILITY_LABELS.get(
                    availability,
                    availability,
                ),
                "as_of": None,
                "current_stage": None,
                "current_stage_label": "等待資料",
                "intraday": None,
                "execution_book": None,
                "signal": None,
            }
        signal = projection.signal_result
        return {
            **metadata,
            "availability": "EVALUATED",
            "availability_label": _REALTIME_AVAILABILITY_LABELS[
                "EVALUATED"
            ],
            "as_of": projection.as_of.isoformat(),
            "current_stage": projection.current_stage.value,
            "current_stage_label": _STAGE_LABELS[projection.current_stage.value],
            "intraday": _serialize_intraday(projection.feature_snapshot),
            "execution_book": _serialize_execution_book(book),
            "signal": {
                "family": signal.signal_family.value,
                "family_label": _FAMILY_LABELS[signal.signal_family.value],
                "signal": signal.signal.value,
                "evaluation_status": signal.evaluation_status.value,
                "momentum_acceleration_confirmed": (
                    signal.momentum_acceleration_confirmed
                ),
                "evidence_score": signal.evidence_score,
                "evidence_max_score": signal.evidence_max_score,
                "passed_rule_count": signal.passed_rule_count,
                "total_rule_count": signal.total_rule_count,
                "coverage": signal.coverage,
                "config_version": signal.config_version,
                "feature_version": signal.feature_version,
                "data_health": signal.data_health,
                "block_reasons": list(signal.block_reasons),
                "details": [_serialize_detail(detail) for detail in signal.details],
                "digest": signal.digest,
            },
        }


class UnavailableMomentumDashboardService:
    """Truthful non-fixture state when the live stream cannot be configured."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "mode": "REALTIME_SHADOW_ALERT_ONLY",
            "source": {
                "name": "Shioaji Tick/BidAsk",
                "is_live": False,
                "as_of": None,
                "candidate_as_of": None,
                "candidate_refresh_error": self._reason,
            },
            "summary": {
                "candidate_count": 0,
                "evaluated_candidate_count": 0,
                "unavailable_candidate_count": 0,
                "triggered_candidate_count": 0,
                "active_episode_count": 0,
                "pending_alert_count": 0,
                "projection_digest": _realtime_digest(
                    source={"reason": self._reason}, items=[], alerts=[]
                ),
            },
            "items": [],
            "alerts": [],
            "disclaimer": "盤中訊號需要即時 Tick／BidAsk 資料。",
            "notice": f"即時盤中動能未啟動：{self._reason}",
        }

    def symbol(self, symbol: str) -> dict[str, Any]:
        raise KeyError(f"目前 Candidate 清單沒有：{symbol.strip().upper()}")

    def acknowledge(self, alert_id: str) -> dict[str, Any]:
        raise KeyError(f"unknown Momentum alert: {alert_id}")

    def close(self) -> None:
        return None


def create_realtime_momentum_dashboard_service(
    *,
    candidate_snapshot_loader: Callable[[], Mapping[str, Any]],
    clock: Clock | None = None,
) -> RealtimeMomentumDashboardService:
    """Build the dashboard-owned, market-data-only Shadow runtime."""
    resolved_clock = clock or SystemClock()
    started_at = resolved_clock.now()
    session_id = f"dashboard-momentum-{started_at:%Y%m%d-%H%M%S%z}"
    stream = ShioajiMomentumStream.connect_from_env(
        session_id=session_id,
        clock=resolved_clock,
    )
    subscriptions = SubscriptionManager(
        SubscriptionPolicy(
            version="dashboard_momentum_subscription_v0",
            capacity=SubscriptionCapacityConfig(
                account_subscription_limit=200,
                reserved_headroom=0,
                mode=QuoteSubscriptionMode.TICK_BIDASK,
            ),
            ack_timeout=timedelta(seconds=5),
            retry_backoff=timedelta(seconds=5),
            minimum_dwell=timedelta(seconds=30),
        )
    )
    runtime = MomentumShadowRuntime(
        config=MomentumShadowRuntimeConfig(
            version="dashboard_momentum_shadow_v0",
            session_id=session_id,
            session_date=started_at.date(),
            queue_capacity=10_000,
            retention=timedelta(minutes=20),
            required_stream_max_age=timedelta(seconds=15),
            source_name="Shioaji Tick/BidAsk",
            is_live_source=True,
            aggressor_mapping_verified=False,
        ),
        stream=stream,
        candidate_pool=CandidatePool(
            CandidatePoolConfig(
                version="dashboard_momentum_candidate_pool_v0",
                grace_period=timedelta(seconds=30),
                scanner_min_observations=1,
            )
        ),
        subscriptions=subscriptions,
        clock=resolved_clock,
    )
    service = RealtimeMomentumDashboardService(
        runtime,
        candidate_snapshot_loader=candidate_snapshot_loader,
        clock=resolved_clock,
    )
    service.start()
    return service


def _dashboard_candidate_discoveries(
    candidates: list[object] | tuple[object, ...],
    *,
    observed_at: datetime,
    expires_at: datetime,
) -> tuple[dict[str, dict[str, Any]], list[CandidateDiscovery]]:
    metadata: dict[str, dict[str, Any]] = {}
    discoveries: list[CandidateDiscovery] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        symbol = str(candidate.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        stock = candidate.get("stock", {})
        stock_payload = stock if isinstance(stock, Mapping) else {}
        score = candidate.get("score", {})
        score_payload = score if isinstance(score, Mapping) else {}
        matched_rules = tuple(
            str(rule)
            for rule in candidate.get("matched_rules", ())
            if str(rule).strip()
        )
        candidate_score = int(score_payload.get("total", 0) or 0)
        metadata[symbol] = {
            "symbol": symbol,
            "name": str(stock_payload.get("name", "")),
            "candidate_sources": [
                str(source)
                for source in candidate.get("sources", ())
                if str(source).strip()
            ],
            "candidate_matched_rules": list(matched_rules),
            "candidate_score": candidate_score,
            "candidate_score_max": int(score_payload.get("max", 0) or 0),
        }
        discoveries.append(
            CandidateDiscovery(
                symbol=symbol,
                source=CandidateSource.AUTO,
                rank_types=matched_rules or ("dashboard_candidate",),
                best_rank=None,
                discovered_at=observed_at,
                expires_at=expires_at,
                priority=max(1, candidate_score),
            )
        )
    return metadata, discoveries


def _serialize_realtime_alert(
    alert: MomentumAlert,
    metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    name = str(metadata.get(alert.symbol, {}).get("name", ""))
    label = _ALERT_LABELS.get(
        alert.stage_or_lock_transition,
        alert.stage_or_lock_transition,
    )
    display_symbol = f"{alert.symbol} {name}".strip()
    return {
        "alert_id": alert.alert_id,
        "symbol": alert.symbol,
        "name": name,
        "headline": f"{display_symbol}：{label}",
        "occurred_at": alert.occurred_at.isoformat(),
        "config_version": alert.config_version,
        "acknowledged_at": (
            alert.acknowledged_at.isoformat()
            if alert.acknowledged_at is not None
            else None
        ),
    }


def _realtime_digest(
    *,
    source: Mapping[str, Any],
    items: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {"source": source, "items": items, "alerts": alerts},
            ensure_ascii=False,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class MomentumDashboardService:
    """Own one deterministic Replay projection and acknowledgement state."""

    def __init__(
        self,
        dataset_path: Path = DEFAULT_MOMENTUM_REPLAY,
        *,
        symbol_names: Mapping[str, str] | None = None,
    ) -> None:
        self._lock = RLock()
        self._dataset_path = dataset_path
        self._symbol_names = {"8039": "台虹", **(symbol_names or {})}
        self._dataset = ReplayDatasetLoader().load(dataset_path)
        self._references = {
            reference.symbol: reference for reference in self._dataset.references
        }
        self._store = MomentumProjectionStore(
            self._dataset.manifest.session_date
        )
        self._last_event_at: datetime | None = None
        self._build_projection()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [
                self._serialize_projection(projection)
                for projection in self._store.all()
            ]
            alerts = [
                self._serialize_alert(alert)
                for projection in self._store.all()
                for alert in self._store.alerts_for(projection.symbol)
            ]
            pending_count = sum(
                alert["acknowledged_at"] is None for alert in alerts
            )
            return {
                "status": "fixture",
                "mode": "REPLAY_ALERT_ONLY",
                "source": {
                    "dataset_id": self._dataset.manifest.dataset_id,
                    "schema_version": self._dataset.manifest.schema_version,
                    "content_sha256": self._dataset.manifest.content_sha256,
                    "fixture": self._dataset_path.name,
                    "session_date": (
                        self._dataset.manifest.session_date.isoformat()
                    ),
                    "as_of": (
                        self._last_event_at.isoformat()
                        if self._last_event_at is not None
                        else None
                    ),
                    "is_live": False,
                    "aggressor_mapping": "fixture_verified",
                },
                "summary": {
                    "symbol_count": len(items),
                    "active_episode_count": sum(
                        item["episode"]["status"] == "ACTIVE"
                        for item in items
                        if item["episode"] is not None
                    ),
                    "pending_alert_count": pending_count,
                    "projection_digest": self._store.digest,
                },
                "items": items,
                "alerts": alerts,
                "disclaimer": (
                    "Evidence Score 代表 hypothesis_v0 規則證據成立程度，"
                    "不代表漲停機率，也不是買進指令。"
                ),
                "notice": (
                    "目前顯示 immutable Replay fixture；Dashboard polling "
                    "只讀本機 projection，不會連線即時行情或"
                    "送出委託。"
                ),
            }

    def symbol(self, symbol: str) -> dict[str, Any]:
        normalized = symbol.strip()
        with self._lock:
            projection = self._store.get(normalized)
            if projection is None:
                raise KeyError(f"Momentum projection 沒有：{normalized}")
            return self._serialize_projection(projection)

    def acknowledge(
        self,
        alert_id: str,
        *,
        acknowledged_at: datetime | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._store.acknowledge(
                alert_id,
                acknowledged_at=acknowledged_at or datetime.now(TAIPEI),
            )
            return self.snapshot()

    def _build_projection(self) -> None:
        references = InstrumentReferenceStore(
            self._dataset.manifest.session_date
        )
        for reference in self._dataset.references:
            references.put(reference)
        bars = IntradayBarStore(
            self._dataset.manifest.session_date,
            retention=timedelta(minutes=20),
        )
        books = OrderBookStore(
            self._dataset.manifest.session_date,
            retention=timedelta(minutes=20),
        )
        if not self._dataset.events:
            raise ValueError("Momentum Dashboard Replay requires events")
        tick_coverage_started_at = next(
            (
                envelope.payload.event_time
                for envelope in self._dataset.events
                if isinstance(envelope.payload, TickEvent)
            ),
            None,
        )
        if tick_coverage_started_at is None:
            raise ValueError("Momentum Dashboard Replay requires Tick events")
        started_at = self._dataset.events[0].received_at
        health = DataHealth(
            self._dataset.manifest.session_date,
            started_at=started_at,
        )
        health.mark_ready(
            occurred_at=started_at,
            evidence="dashboard_replay_manifest_validated",
        )
        ingestor = MarketDataIngestor(
            session_id=self._dataset.manifest.session_id,
            session_date=self._dataset.manifest.session_date,
            references=references,
            bars=bars,
            books=books,
            health=health,
        )
        feature_engine = FeatureEngine(
            references=references,
            bars=bars,
            books=books,
        )
        signal_engine = MomentumSignalEngine()
        state_machine = MomentumStateMachine(
            self._dataset.manifest.session_date
        )
        for envelope in self._dataset.events:
            result = ingestor.ingest(envelope)
            self._last_event_at = envelope.event_at
            if not result.projection_applied:
                continue
            if not isinstance(envelope.payload, TickEvent):
                continue
            feature = feature_engine.evaluate(
                envelope.payload,
                FeatureEvaluationContext(
                    data_health=health.snapshot(),
                    tick_coverage_started_at=tick_coverage_started_at,
                    aggressor_mapping_verified=True,
                ),
            )
            signal = signal_engine.evaluate(feature)
            state = state_machine.evaluate(feature, signal)
            entry = None
            if state.episode is not None:
                entry = evaluate_momentum_entry_opportunity(
                    state.episode,
                    signal.digest,
                    MOMENTUM_ENTRY_HYPOTHESIS_V0,
                    RiskGateStatus.UNAVAILABLE,
                )
            self._store.apply(
                feature,
                signal,
                state,
                entry_opportunity=entry,
            )

    def _serialize_projection(
        self,
        projection: MomentumProjection,
    ) -> dict[str, Any]:
        feature = projection.feature_snapshot
        signal = projection.signal_result
        reference = self._references[projection.symbol]
        return {
            "symbol": projection.symbol,
            "name": self._symbol_names.get(projection.symbol, ""),
            "as_of": projection.as_of.isoformat(),
            "current_stage": projection.current_stage.value,
            "current_stage_label": _STAGE_LABELS[
                projection.current_stage.value
            ],
            "highest_stage": projection.highest_stage.value,
            "highest_stage_label": _STAGE_LABELS[
                projection.highest_stage.value
            ],
            "market": {
                "price": _number(feature.price.value),
                "vwap": _number(feature.vwap.value),
                "previous_intraday_high": _number(
                    feature.previous_intraday_high.value
                ),
                "limit_up_price": _number(reference.limit_up_price),
                "distance_to_limit_pct": _percent_value(
                    feature.distance_to_limit
                ),
                "return_2m_pct": _percent_value(feature.return_2m),
                "volume_acceleration_2m": _number(
                    feature.volume_acceleration_2m.value
                ),
                "external_ratio_pct": _percent_value(
                    feature.external_ratio_session
                ),
                "bid_ask_ratio_5": _number(
                    feature.bid_ask_ratio_5.value
                ),
            },
            "signal": {
                "family": signal.signal_family.value,
                "family_label": _FAMILY_LABELS[signal.signal_family.value],
                "signal": signal.signal.value,
                "evaluation_status": signal.evaluation_status.value,
                "evidence_score": signal.evidence_score,
                "evidence_max_score": signal.evidence_max_score,
                "passed_rule_count": signal.passed_rule_count,
                "total_rule_count": signal.total_rule_count,
                "coverage": signal.coverage,
                "config_version": signal.config_version,
                "feature_version": signal.feature_version,
                "data_health": signal.data_health,
                "block_reasons": list(signal.block_reasons),
                "details": [
                    _serialize_detail(detail) for detail in signal.details
                ],
                "digest": signal.digest,
            },
            "episode": _serialize_episode(projection.episode),
            "entry_opportunity": _serialize_entry(
                projection.entry_opportunity
            ),
            "alert_ids": list(projection.alert_ids),
            "projection_digest": projection.digest,
        }

    def _serialize_alert(self, alert: MomentumAlert) -> dict[str, Any]:
        name = self._symbol_names.get(alert.symbol, "")
        label = _ALERT_LABELS.get(
            alert.stage_or_lock_transition,
            alert.stage_or_lock_transition,
        )
        display_symbol = f"{alert.symbol} {name}".strip()
        return {
            "alert_id": alert.alert_id,
            "symbol": alert.symbol,
            "name": name,
            "episode_id": alert.episode_id,
            "event_type": alert.event_type.value,
            "stage_or_lock_transition": alert.stage_or_lock_transition,
            "event_label": label,
            "headline": f"{display_symbol}：{label}",
            "occurred_at": alert.occurred_at.isoformat(),
            "signal_family": alert.signal_family.value,
            "config_version": alert.config_version,
            "evidence_snapshot_id": alert.evidence_snapshot_id,
            "acknowledged_at": (
                alert.acknowledged_at.isoformat()
                if alert.acknowledged_at is not None
                else None
            ),
        }


def _serialize_detail(detail: SignalDetail) -> dict[str, Any]:
    return {
        "rule": detail.rule,
        "status": detail.status.value,
        "passed": detail.passed,
        "points_awarded": detail.points_awarded,
        "points_possible": detail.points_possible,
        "observed_value": (
            str(detail.observed_value)
            if detail.observed_value is not None
            else None
        ),
        "threshold": (
            str(detail.threshold) if detail.threshold is not None else None
        ),
        "source_as_of": (
            detail.source_as_of.isoformat()
            if detail.source_as_of is not None
            else None
        ),
        "missing_reason": detail.missing_reason,
    }


def _serialize_intraday(
    snapshot: IntradayFeatureSnapshot,
) -> dict[str, dict[str, Any]]:
    return {
        name: _serialize_feature_value(getattr(snapshot, name))
        for name in (
            "price",
            "vwap",
            "previous_intraday_high",
            "distance_to_limit",
            "return_2m",
            "volume_2m",
            "volume_acceleration_2m",
            "external_ratio_session",
            "bid_ask_ratio_5",
            "book_imbalance_5",
        )
    }


def _serialize_execution_book(event: Any) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "status": "VALID" if event.best_bid is not None and event.best_ask is not None else "MISSING",
        "best_bid": str(event.best_bid) if event.best_bid is not None else None,
        "best_ask": str(event.best_ask) if event.best_ask is not None else None,
        "bid_volume_lots": event.bid_volume_lots[0] if event.bid_volume_lots else None,
        "ask_volume_lots": event.ask_volume_lots[0] if event.ask_volume_lots else None,
        "event_at": event.event_time.isoformat(),
        "received_at": event.received_at.isoformat(),
        "event_id": event.event_id,
    }


def _serialize_feature_value(feature: FeatureValue) -> dict[str, Any]:
    value = feature.value
    return {
        "value": str(value) if isinstance(value, Decimal) else value,
        "status": feature.status.value,
        "source_as_of": _timestamp(feature.source_as_of),
        "reason": feature.reason,
    }


def _serialize_episode(
    episode: MomentumEpisode | None,
) -> dict[str, Any] | None:
    if episode is None:
        return None
    return {
        "episode_id": episode.episode_id,
        "status": episode.status.value,
        "created_at": episode.created_at.isoformat(),
        "created_by_signal_family": episode.created_by_signal_family.value,
        "created_by_signal_family_label": _FAMILY_LABELS[
            episode.created_by_signal_family.value
        ],
        "created_by_config_version": episode.created_by_config_version,
        "current_signal_family": episode.current_signal_family.value,
        "current_signal_family_label": _FAMILY_LABELS[
            episode.current_signal_family.value
        ],
        "current_config_version": episode.current_config_version,
        "breakout_level": _number(episode.breakout_level),
        "first_seen_at": _timestamp(episode.first_seen_at),
        "peak_price": _number(episode.peak_price),
        "last_progress_at": _timestamp(episode.last_progress_at),
        "closed_at": _timestamp(episode.closed_at),
        "close_reason": episode.close_reason,
        "cooldown_until": _timestamp(episode.cooldown_until),
        "limit_touched_at": _timestamp(episode.limit_touched_at),
        "limit_locked": episode.limit_locked,
        "limit_lock_evidence_as_of": _timestamp(
            episode.limit_lock_evidence_as_of
        ),
        "limit_locked_at": _timestamp(episode.limit_locked_at),
        "limit_unlocked_at": _timestamp(episode.limit_unlocked_at),
        "transitions": [
            _serialize_transition(transition)
            for transition in episode.transitions
        ],
        "evidence_updates": [
            _serialize_evidence(evidence)
            for evidence in episode.evidence_updates
        ],
        "digest": episode.digest,
    }


def _serialize_transition(transition: StageTransition) -> dict[str, Any]:
    return {
        "occurred_at": transition.occurred_at.isoformat(),
        "from_stage": transition.from_stage.value,
        "from_stage_label": _STAGE_LABELS[transition.from_stage.value],
        "to_stage": transition.to_stage.value,
        "to_stage_label": _STAGE_LABELS[transition.to_stage.value],
        "signal_family": transition.signal_family.value,
        "signal_family_label": _FAMILY_LABELS[transition.signal_family.value],
        "config_version": transition.config_version,
        "evidence_snapshot_id": transition.evidence_snapshot_id,
    }


def _serialize_evidence(evidence: EvidenceUpdate) -> dict[str, Any]:
    return {
        "occurred_at": evidence.occurred_at.isoformat(),
        "signal_family": evidence.signal_family.value,
        "signal_family_label": _FAMILY_LABELS[evidence.signal_family.value],
        "config_version": evidence.config_version,
        "evidence_snapshot_id": evidence.evidence_snapshot_id,
        "momentum_acceleration_confirmed": (
            evidence.momentum_acceleration_confirmed
        ),
    }


def _serialize_entry(
    entry: EntryOpportunity | None,
) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "mode": entry.mode.value,
        "status": entry.status.value,
        "status_label": _ENTRY_STATUS_LABELS[entry.status.value],
        "signal_id": entry.signal_id,
        "policy_version": entry.policy_version,
        "risk_decision_id": entry.risk_decision_id,
        "risk_level": entry.risk_level.value,
        "position_size_cap": _number(entry.position_size_cap),
        "invalidation_price": _number(entry.invalidation_price),
        "reasons": list(entry.reasons),
        "reason_labels": [
            _REASON_LABELS.get(reason, reason) for reason in entry.reasons
        ],
    }


def _percent_value(feature: FeatureValue) -> float | None:
    value = feature.value
    if isinstance(value, Decimal):
        return float(value * Decimal("100"))
    return None


def _number(value: object) -> int | float | str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
