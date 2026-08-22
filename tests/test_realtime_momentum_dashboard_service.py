from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Event, Thread
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from features.models import (
    FeatureStatus,
    FeatureValue,
    RequestedFeatureProjection,
)
from features.specifications import FeatureRequestSpec, FeatureSpecificationRegistry
from features.engine import FeatureEngine
from market_data.subscriptions import MissReason
from dashboard.momentum import (
    MomentumDashboardService,
    RealtimeMomentumDashboardService,
)
from runtime.momentum_shadow import MomentumShadowReadView


TAIPEI = ZoneInfo("Asia/Taipei")


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FakeLiveRuntime:
    def __init__(
        self,
        projection,
        clock: MutableClock,
        *,
        projections=None,
        requested_features=None,
    ) -> None:
        self._projections = {projection.symbol: projection}
        if projections is not None:
            self._projections.update(projections)
        self._clock = clock
        self.started = False
        self.closed = False
        self.discoveries = []
        self.symbols: tuple[str, ...] = ()
        self.read_view_calls = 0
        self.requested_features = requested_features or {}
        self.feature_request_calls = []

    def start(self) -> None:
        self.started = True

    def update_candidates(self, discoveries, *, evaluated_at: datetime) -> None:
        self.discoveries.append(tuple(discoveries))
        self.symbols = tuple(item.symbol for item in discoveries)

    def snapshot(self):
        return SimpleNamespace(
            mode="REALTIME_SHADOW_ALERT_ONLY",
            source_name="fake_tick_bidask",
            is_live_source=True,
            session_id="test-live-session",
            session_date=self._clock.now().date(),
            running=self.started,
            connection_state=SimpleNamespace(value="RUNNING"),
            health=SimpleNamespace(
                as_of=self._clock.now(),
                state=SimpleNamespace(value="HEALTHY"),
            ),
            subscription_max_symbols=100,
            subscriptions_in_use=len(self.symbols) * 2,
            discovered_symbols=self.symbols,
            active_episode_count=1,
        )

    def read_view(
        self,
        expected_symbols,
        feature_requests=(),
    ) -> MomentumShadowReadView:
        self.read_view_calls += 1
        self.feature_request_calls.append(tuple(feature_requests))
        normalized = tuple(str(symbol).strip().upper() for symbol in expected_symbols)
        return MomentumShadowReadView(
            snapshot=self.snapshot(),
            projections=tuple(
                (symbol, self._projections.get(symbol)) for symbol in normalized
            ),
            miss_reason_by_symbol=tuple(
                (symbol, MissReason.CAPACITY_EVICTED)
                for symbol in normalized
                if self._projections.get(symbol) is None
            ),
            pending_alerts=(),
            requested_features=tuple(
                (symbol, tuple(self.requested_features.get(symbol, ())))
                for symbol in normalized
            ),
        )

    def check_staleness(self, *, evaluated_at: datetime) -> bool:
        return False

    def projection(self, symbol: str):
        return self._projections.get(symbol)

    def classify_expected_symbol(self, symbol: str):
        return MissReason.CAPACITY_EVICTED

    def pending_alerts(self):
        return ()

    def acknowledge_alert(self, alert_id: str, *, acknowledged_at: datetime) -> None:
        raise KeyError(alert_id)

    def close(self) -> None:
        self.closed = True


def candidate(symbol: str, *, score: int, name: str) -> dict:
    return {
        "symbol": symbol,
        "sources": ["AUTO"],
        "matched_rules": ["gap_up"],
        "stock": {"name": name},
        "score": {"total": score, "max": 40},
    }


def test_live_service_evaluates_all_dashboard_candidates_and_exposes_values():
    clock = MutableClock(datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI))
    replay_projection = MomentumDashboardService()._store.get("8039")
    assert replay_projection is not None
    runtime = FakeLiveRuntime(replay_projection, clock)
    snapshots = [
        {"candidates": [candidate("8039", score=40, name="台虹"), candidate("2330", score=20, name="台積電")]},
        {"candidates": [candidate("8039", score=40, name="台虹")]},
    ]
    refreshed_candidates = Event()

    def load_candidates() -> dict:
        snapshot = snapshots.pop(0)
        if not snapshots:
            refreshed_candidates.set()
        return snapshot

    service = RealtimeMomentumDashboardService(
        runtime,
        candidate_snapshot_loader=load_candidates,
        clock=clock,
        candidate_refresh_interval=timedelta(milliseconds=10),
    )

    first = service.snapshot()
    evaluated, unavailable = first["items"]

    assert first["status"] == "live"
    assert first["source"]["is_live"] is True
    assert first["summary"]["candidate_count"] == 2
    assert first["summary"]["evaluated_candidate_count"] == 1
    assert evaluated["symbol"] == "8039"
    assert evaluated["signal"]["evidence_score"] == 100
    assert evaluated["signal"]["momentum_acceleration_confirmed"] is True
    assert evaluated["signal"]["details"][0]["observed_value"] is not None
    assert evaluated["intraday"]["price"] == {
        "value": "278",
        "status": "VALID",
        "source_as_of": "2026-08-18T09:18:00+08:00",
        "reason": None,
    }
    assert evaluated["intraday"]["volume_2m"]["value"] == 2306
    assert evaluated["intraday"]["bid_ask_ratio_5"]["value"] == (
        "1.833333333333333333333333333"
    )
    assert unavailable["symbol"] == "2330"
    assert unavailable["availability"] == "CAPACITY_EVICTED"
    assert unavailable["intraday"] is None
    assert unavailable["signal"] is None
    assert {item.symbol for item in runtime.discoveries[0]} == {"8039", "2330"}
    assert runtime.read_view_calls == 1

    clock.advance(31)
    assert refreshed_candidates.wait(0.5)
    refreshed = service.snapshot()

    assert [item["symbol"] for item in refreshed["items"]] == ["8039"]
    assert len(runtime.discoveries) == 2
    assert runtime.read_view_calls == 2
    service.close()
    assert runtime.closed is True


def test_live_service_preserves_stale_intraday_feature_provenance():
    clock = MutableClock(datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI))
    projection = MomentumDashboardService()._store.get("8039")
    assert projection is not None
    stale_at = datetime(2026, 8, 18, 9, 17, 50, tzinfo=TAIPEI)
    projection = replace(
        projection,
        feature_snapshot=replace(
            projection.feature_snapshot,
            price=FeatureValue(
                value=Decimal("277.5"),
                status=FeatureStatus.STALE,
                source_as_of=stale_at,
                reason="tick_too_old",
            ),
        ),
    )
    runtime = FakeLiveRuntime(projection, clock)
    service = RealtimeMomentumDashboardService(
        runtime,
        candidate_snapshot_loader=lambda: {
            "candidates": [candidate("8039", score=40, name="台虹")]
        },
        clock=clock,
    )

    item = service.symbol("8039")

    assert item["intraday"]["price"] == {
        "value": "277.5",
        "status": "STALE",
        "source_as_of": stale_at.isoformat(),
        "reason": "tick_too_old",
    }
    service.close()
    assert runtime.closed is True


def test_live_service_serializes_exact_requested_feature_evidence():
    clock = MutableClock(datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI))
    projection = MomentumDashboardService()._store.get("8039")
    assert projection is not None
    request = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})
    specification = FeatureSpecificationRegistry().get(request.feature_id)
    requested = RequestedFeatureProjection(
        feature_id=request.feature_id,
        adapter_identity=FeatureEngine.requested_feature_adapter_identity,
        request_digest=request.request_digest,
        parameter_digest=request.parameter_digest,
        specification_digest=specification.specification_digest,
        implementation_digest=specification.implementation_digest,
        parameters=request.parameters,
        state_key=request.state_key(
            adapter_identity=FeatureEngine.requested_feature_adapter_identity,
            cadence=specification.cadence,
            symbol="8039",
            session=clock.now().date().isoformat(),
        ),
        value=FeatureValue(
            value=Decimal("0.03"),
            status=FeatureStatus.VALID,
            source_as_of=clock.now().replace(minute=17, second=0),
        ),
        evidence={"window_minutes": 3},
    )
    runtime = FakeLiveRuntime(
        projection,
        clock,
        requested_features={"8039": (requested,)},
    )
    service = RealtimeMomentumDashboardService(
        runtime,
        candidate_snapshot_loader=lambda: {
            "candidates": [candidate("8039", score=40, name="台虹")]
        },
        clock=clock,
    )

    snapshot = service.snapshot(feature_requests=(request,))
    serialized = snapshot["items"][0]["requested_features"][0]

    assert runtime.feature_request_calls[-1] == (request,)
    assert serialized["request_digest"] == request.request_digest
    assert serialized["parameters"] == {"window_minutes": 3}
    assert serialized["value"]["value"] == "0.03"
    service.close()


def test_live_service_orders_candidates_by_descending_intraday_score():
    clock = MutableClock(datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI))
    high_score = MomentumDashboardService()._store.get("8039")
    assert high_score is not None
    lower_score = replace(
        high_score,
        symbol="2330",
        signal_result=replace(
            high_score.signal_result,
            symbol="2330",
            evidence_score=35,
        ),
    )
    runtime = FakeLiveRuntime(
        high_score,
        clock,
        projections={"2330": lower_score},
    )
    service = RealtimeMomentumDashboardService(
        runtime,
        candidate_snapshot_loader=lambda: {
            "candidates": [
                candidate("2330", score=40, name="台積電"),
                candidate("8039", score=20, name="台虹"),
                candidate("2317", score=40, name="鴻海"),
            ]
        },
        clock=clock,
    )

    snapshot = service.snapshot()

    assert [item["symbol"] for item in snapshot["items"]] == [
        "8039",
        "2330",
        "2317",
    ]
    service.close()


def test_candidate_scan_does_not_block_projection_snapshot():
    clock = MutableClock(datetime(2026, 8, 18, 9, 18, tzinfo=TAIPEI))
    projection = MomentumDashboardService()._store.get("8039")
    assert projection is not None
    runtime = FakeLiveRuntime(projection, clock)
    scan_started = Event()
    release_scan = Event()
    load_count = 0

    def load_candidates() -> dict:
        nonlocal load_count
        load_count += 1
        if load_count > 1:
            scan_started.set()
            assert release_scan.wait(0.5)
        return {"candidates": [candidate("8039", score=40, name="台虹")]}

    service = RealtimeMomentumDashboardService(
        runtime,
        candidate_snapshot_loader=load_candidates,
        clock=clock,
        candidate_refresh_interval=timedelta(milliseconds=10),
    )
    service.snapshot()
    clock.advance(31)
    assert scan_started.wait(0.5)

    snapshot_completed = Event()
    def read_snapshot() -> None:
        service.snapshot()
        snapshot_completed.set()

    snapshot_thread = Thread(
        target=read_snapshot,
        daemon=True,
    )
    snapshot_thread.start()
    completed_while_scan_blocked = snapshot_completed.wait(0.2)
    release_scan.set()
    snapshot_thread.join(timeout=0.5)
    service.close()

    assert completed_while_scan_blocked is True
