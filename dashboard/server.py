"""FastAPI 入口：提供儀表板與本機紙上模擬 API。"""

from __future__ import annotations

import asyncio
import csv
from contextlib import asynccontextmanager
from datetime import datetime
from io import StringIO
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlsplit

from fastapi import (
    FastAPI,
    HTTPException,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import build_provider
from backtest.application import BacktestApplicationService
from backtest.scheduler import AfterCloseIncrementalScheduler
from config import backtest as backtest_settings
from config import twse_calendar_2026
from config.momentum_stream import MOMENTUM_STREAM_CONFIG
from dashboard.momentum import (
    RealtimeMomentumDashboardService,
    UnavailableMomentumDashboardService,
    create_realtime_momentum_dashboard_service,
)
from dashboard.momentum_stream import (
    RESUME_PATH,
    SCHEMA_VERSION,
    MomentumStreamHub,
)
from dashboard.service import DashboardService
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MarketDataProvider
from runtime.composition import RuntimeComposition
from simulation.application import LocalPaperCommandService
from simulation.continuous_strategy import (
    AutomatedStrategyConfig,
    AutomatedStrategyStateError,
    ContinuousPaperStrategyController,
)
from simulation.service import (
    SimulationService,
    SimulationStateError,
    SimulationValidationError,
)
from simulation.strategy_flow import StrategyPaperFlowService, StrategyPaperIntent

STATIC_DIR = Path(__file__).parent / "static"
SIMULATION_STREAM_PATH = "/ws/simulation/projection"
SIMULATION_STREAM_SCHEMA_VERSION = "simulation_projection_stream_v1"
SIMULATION_STREAM_SAMPLE_SECONDS = 0.25
SIMULATION_STREAM_HEARTBEAT_SECONDS = 10.0
SIMULATION_STREAM_SEND_TIMEOUT_SECONDS = 2.0

_provider: MarketDataProvider | None = None
_service: DashboardService | None = None
_simulation_service: SimulationService | None = None
_composition: RuntimeComposition | None = None
_momentum_service: (
    RealtimeMomentumDashboardService | UnavailableMomentumDashboardService | None
) = None
_momentum_stream_hub: MomentumStreamHub | None = None
_backtest_service: BacktestApplicationService | None = None
_incremental_scheduler: AfterCloseIncrementalScheduler | None = None
_automated_strategy_controller: ContinuousPaperStrategyController | None = None
_runtime_composition_lock = RLock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """啟動收盤同步；關站時停止排程並排空背景 workers。"""
    scheduler = None
    if backtest_settings.BACKTEST_INCREMENTAL_SYNC_ENABLED:
        scheduler = get_incremental_scheduler()
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop()
        if _automated_strategy_controller is not None:
            _automated_strategy_controller.close()
        if _backtest_service is not None:
            _backtest_service.close()
        if _momentum_stream_hub is not None:
            _momentum_stream_hub.close()
        if _momentum_service is not None:
            _momentum_service.close()
        if _composition is not None:
            _composition.close()
        elif _provider is not None:
            _provider.close()


app = FastAPI(title="台股盤中雷達", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SimulationOrderRequest(BaseModel):
    symbol: str
    side: str
    lots: int
    limit_price: float
    idempotency_key: str


class SimulationCancelRequest(BaseModel):
    idempotency_key: str


class SimulationRetryRequest(BaseModel):
    idempotency_key: str
    limit_price: float | None = None


class SimulationStrategyIntentRequest(BaseModel):
    intent_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    side: str
    lots: int
    limit_price: str
    signaled_at: datetime


class AutomatedStrategyStartRequest(BaseModel):
    stop_loss_pct: str
    take_profit_pct: str
    max_daily_loss: str


class DatasetSyncRequest(BaseModel):
    years: int = Field(default=3, ge=1, le=10)
    symbols: list[str] | None = None
    symbol_limit: int | None = Field(default=None, ge=1, le=10_000)


class BacktestRunRequest(BaseModel):
    dataset_id: str
    entry_strategy_ids: list[str]
    exit_strategy_ids: list[str]
    entry_policy: str = "ANY"
    exit_policy: str = "ANY"
    entry_min_trigger_count: int = Field(default=1, ge=1)
    exit_min_trigger_count: int = Field(default=1, ge=1)
    priority_order: list[str] = Field(default_factory=list)
    starting_cash: str = "10000000"
    position_fraction: str = "0.10"
    commission_rate: str = "0.001425"
    sell_tax_rate: str = "0.003"
    slippage_bps: str = "5"
    target_win_rate: str = "0.50"
    minimum_oos_trades: int = Field(default=30, ge=1)
    max_drawdown_guardrail: str = "0.20"
    idempotency_key: str
    experiment_id: str | None = None
    baseline_run_id: str | None = None
    parent_run_id: str | None = None
    change_note: str = ""


class BacktestCloneRequest(BaseModel):
    idempotency_key: str
    change_note: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class BacktestCompareRequest(BaseModel):
    baseline_run_id: str
    challenger_run_id: str


class StrategyDefinitionRequest(BaseModel):
    """Flexible metadata contract; executable code remains server-side."""

    strategy_id: str
    display_name_zh_tw: str
    version: str
    role: str
    side: str | None = None
    session_phase: str = "ALL_SESSION"
    status: str = "DRAFT"
    description_zh_tw: str = ""
    execution_binding: str = ""
    required_capabilities: list[str] = Field(default_factory=lambda: ["OHLCV"])
    parameters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    code_identity: str = "database-strategy-v1"


def get_runtime_composition() -> RuntimeComposition:
    """建立一次本機 composition；保留舊 globals 供測試注入相容。"""
    global _composition, _provider, _service, _simulation_service

    with _runtime_composition_lock:
        current = _composition
        if (
            current is not None
            and _provider is current.provider
            and (_service is None or _service is current.dashboard_service)
            and (
                _simulation_service is None
                or _simulation_service is current.simulation_service
            )
        ):
            _service = current.dashboard_service
            _simulation_service = current.simulation_service
            return current

        provider = _provider or build_provider()
        _composition = RuntimeComposition.create(
            provider,
            dashboard_service=_service,
            simulation_service=_simulation_service,
        )
        _provider = _composition.provider
        _service = _composition.dashboard_service
        _simulation_service = _composition.simulation_service
        return _composition


def get_market_provider() -> MarketDataProvider:
    """讓掃描和本機模擬共用 composition 建立的資料來源實例。"""
    return get_runtime_composition().provider


def get_dashboard_service() -> DashboardService:
    """在 Web process 生命週期中共用同一個 Dashboard service。"""
    return get_runtime_composition().dashboard_service


def get_simulation_service() -> SimulationService:
    """在 Web process 生命週期中共用同一個本機紙上模擬 session。"""
    service = get_runtime_composition().simulation_service
    assert isinstance(service, SimulationService)
    return service


def get_local_paper_command_service() -> LocalPaperCommandService:
    """Return the Journal-first facade; it remains local-paper only."""
    return get_runtime_composition().local_paper_commands


def get_strategy_paper_flow_service() -> StrategyPaperFlowService:
    """Return the explicit strategy-intent facade for local paper only."""
    return get_runtime_composition().strategy_paper_flow


def get_automated_strategy_controller() -> ContinuousPaperStrategyController:
    """Build one explicitly started local-paper controller for this process."""
    global _automated_strategy_controller
    with _runtime_composition_lock:
        if _automated_strategy_controller is None:
            composition = get_runtime_composition()
            _automated_strategy_controller = ContinuousPaperStrategyController(
                flow=composition.strategy_paper_flow,
                projection_reader=get_simulation_service().projection,
                signal_reader=get_momentum_dashboard_service().snapshot,
                calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
                clock=composition.clock,
            )
        return _automated_strategy_controller


def get_momentum_dashboard_service(
) -> RealtimeMomentumDashboardService | UnavailableMomentumDashboardService:
    """建立一次即時 Shadow projection；無法連線時明確回報不可用。"""
    global _momentum_service
    if _momentum_service is None:
        try:
            _momentum_service = create_realtime_momentum_dashboard_service(
                candidate_snapshot_loader=(
                    get_dashboard_service().realtime_candidate_snapshot
                ),
            )
        except Exception as error:
            _momentum_service = UnavailableMomentumDashboardService(str(error))
    return _momentum_service


def get_momentum_stream_hub() -> MomentumStreamHub:
    """Keep one bounded stream hub for the process-local Momentum service."""
    global _momentum_stream_hub
    service = get_momentum_dashboard_service()
    if (
        _momentum_stream_hub is None
        or _momentum_stream_hub.service is not service
    ):
        if _momentum_stream_hub is not None:
            _momentum_stream_hub.close()
        _momentum_stream_hub = MomentumStreamHub(
            service,
            config=MOMENTUM_STREAM_CONFIG,
        )
    return _momentum_stream_hub


def get_backtest_service() -> BacktestApplicationService:
    """Create a separate historical-backtest composition without local orders."""
    global _backtest_service, _provider
    with _runtime_composition_lock:
        if _backtest_service is None:
            # RuntimeComposition creates SimulationService, which can register quote
            # callbacks. Historical backtest must not activate that path.
            _provider = _provider or build_provider()
            _backtest_service = BacktestApplicationService(_provider)
        return _backtest_service


def get_incremental_scheduler() -> AfterCloseIncrementalScheduler:
    """建立一次排程器；排程只呼叫 backtest application service。"""

    global _incremental_scheduler
    if _incremental_scheduler is None:
        service = get_backtest_service()
        _incremental_scheduler = AfterCloseIncrementalScheduler(
            trigger=lambda session_date: service.start_incremental_sync(
                session_date,
                overlap_days=backtest_settings.BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS,
            ),
            close_time=backtest_settings.BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME,
            poll_seconds=backtest_settings.BACKTEST_INCREMENTAL_SYNC_POLL_SECONDS,
            job_status=service.dataset_job,
        )
    return _incremental_scheduler


def _backtest_http_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, RuntimeError):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


def _dashboard_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    """避免改寫 DashboardService 快取，附加本機模擬投影。"""
    return {**snapshot, "simulation": get_simulation_service().projection()}


@app.get("/", include_in_schema=False)
def dashboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/dashboard/snapshot")
def dashboard_snapshot() -> dict[str, Any]:
    return _dashboard_payload(get_dashboard_service().snapshot())


@app.get("/api/dashboard/provider-usage")
def provider_usage_status() -> dict[str, Any]:
    return get_dashboard_service().provider_usage()


@app.post("/api/dashboard/refresh")
def refresh_dashboard_snapshot() -> dict[str, Any]:
    snapshot = get_dashboard_service().refresh()
    get_simulation_service().refresh_quotes()
    return _dashboard_payload(snapshot)


@app.get("/api/dashboard/candidates/{symbol}/history")
def candidate_history(symbol: str, period: str = "1d") -> dict[str, Any]:
    """回傳選定 Candidate 的按需 Kbar。"""
    try:
        return get_dashboard_service().candidate_history(symbol, period)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/dashboard/momentum")
def momentum_dashboard_snapshot() -> dict[str, Any]:
    """讀取所有目前候選的 Tick／BidAsk Momentum projection。"""
    if MOMENTUM_STREAM_CONFIG.enabled:
        return get_momentum_stream_hub().bootstrap()
    return _momentum_stream_disabled_snapshot(
        get_momentum_dashboard_service().snapshot()
    )


@app.post("/api/dashboard/momentum/alerts/{alert_id}/acknowledge")
def acknowledge_momentum_alert(alert_id: str) -> dict[str, Any]:
    """確認本機 Momentum Shadow 告警；不產生外部訊息或交易動作。"""
    try:
        snapshot = get_momentum_dashboard_service().acknowledge(alert_id)
        if not MOMENTUM_STREAM_CONFIG.enabled:
            return _momentum_stream_disabled_snapshot(snapshot)
        hub = get_momentum_stream_hub()
        hub.capture_now(snapshot)
        return hub.bootstrap()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.websocket(RESUME_PATH)
async def momentum_dashboard_stream(
    websocket: WebSocket,
    stream_id: str,
    since_revision: int,
) -> None:
    """Replay projection revisions, then push future coalesced deltas."""
    if not MOMENTUM_STREAM_CONFIG.enabled:
        await websocket.close(code=1008)
        return
    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008)
        return

    hub = get_momentum_stream_hub()
    hub.bootstrap()
    if not hub.try_register_client():
        await websocket.close(code=1013)
        return

    accepted = False
    try:
        await websocket.accept()
        accepted = True
        replay = hub.events_after(stream_id, since_revision)
        if replay.reason is not None:
            await _send_momentum_message(
                websocket,
                hub.resync_message(replay.reason),
            )
            await websocket.close(code=1012)
            return

        await _send_momentum_message(websocket, hub.ready_message())
        cursor = since_revision
        while True:
            if replay.events:
                for event in replay.events:
                    await _send_momentum_message(websocket, event)
                    cursor = event["revision"]
            else:
                await _send_momentum_message(
                    websocket,
                    hub.heartbeat_message(),
                )
            replay = await asyncio.to_thread(
                hub.wait_for_events,
                stream_id,
                cursor,
                timeout=hub.config.heartbeat_seconds,
            )
            if replay.reason is not None:
                await _send_momentum_message(
                    websocket,
                    hub.resync_message(replay.reason),
                )
                await websocket.close(code=1012)
                return
    except WebSocketDisconnect:
        return
    except TimeoutError:
        if accepted:
            await _close_websocket(websocket, code=1013)
    finally:
        hub.unregister_client()


@app.get("/api/dashboard/momentum/{symbol}")
def momentum_symbol_projection(symbol: str) -> dict[str, Any]:
    """讀取單一候選的即時 Momentum projection。"""
    try:
        return get_momentum_dashboard_service().symbol(symbol)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _momentum_stream_disabled_snapshot(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        **snapshot,
        "stream": {
            "schema_version": SCHEMA_VERSION,
            "enabled": False,
            "stream_id": None,
            "revision": None,
            "generated_at": None,
            "resume_path": RESUME_PATH,
            "heartbeat_seconds": MOMENTUM_STREAM_CONFIG.heartbeat_seconds,
            "last_error": None,
        },
    }


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    parsed = urlsplit(origin)
    host = websocket.headers.get("host", "").lower()
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host


async def _send_momentum_message(
    websocket: WebSocket,
    payload: dict[str, Any],
) -> None:
    await asyncio.wait_for(
        websocket.send_json(payload),
        timeout=MOMENTUM_STREAM_CONFIG.send_timeout_seconds,
    )


async def _close_websocket(websocket: WebSocket, *, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        return


@app.get("/api/simulation/session")
def simulation_session() -> dict[str, Any]:
    """讀取本機紙上模擬 session，不會呼叫券商或資料來源。"""
    return get_simulation_service().session()


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness without provider, broker account, or order API calls."""
    session = get_simulation_service().session()
    return {
        "status": "ok",
        "mode": session["mode"],
        "stream_health": session["stream_health"],
    }


@app.get("/readyz")
def readyz(response: Response) -> dict[str, Any]:
    """Fail closed only when the simulation quote ingress has overflowed."""
    session = get_simulation_service().session()
    ready = session["stream_health"] == "HEALTHY"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "blocked",
        "mode": session["mode"],
        "stream_health": session["stream_health"],
        "quote_queue_depth": session["quote_queue_depth"],
        "quote_queue_capacity": session["quote_queue_capacity"],
    }


@app.get("/api/simulation/projection")
def simulation_projection() -> dict[str, Any]:
    """一次讀取本機投影；不輪詢 Shioaji snapshot 或帳務 API。"""
    return get_simulation_service().projection()


@app.websocket(SIMULATION_STREAM_PATH)
async def simulation_projection_stream(websocket: WebSocket) -> None:
    """Push changed local-paper projections; never call a broker API."""
    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    revision = 0
    last_projection: dict[str, Any] | None = None
    last_sent_at = 0.0
    try:
        while True:
            projection = get_simulation_service().projection()
            sampled_at = loop.time()
            if projection != last_projection:
                revision += 1
                await _send_simulation_message(
                    websocket,
                    {
                        "schema_version": SIMULATION_STREAM_SCHEMA_VERSION,
                        "type": "simulation_projection",
                        "revision": revision,
                        "emitted_at": datetime.now().astimezone().isoformat(),
                        "projection": projection,
                    },
                )
                last_projection = projection
                last_sent_at = sampled_at
            elif sampled_at - last_sent_at >= SIMULATION_STREAM_HEARTBEAT_SECONDS:
                await _send_simulation_message(
                    websocket,
                    {
                        "schema_version": SIMULATION_STREAM_SCHEMA_VERSION,
                        "type": "heartbeat",
                        "current_revision": revision,
                        "emitted_at": datetime.now().astimezone().isoformat(),
                    },
                )
                last_sent_at = sampled_at

            try:
                event = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=SIMULATION_STREAM_SAMPLE_SECONDS,
                )
            except TimeoutError:
                continue
            if event["type"] == "websocket.disconnect":
                return
    except WebSocketDisconnect:
        return
    except TimeoutError:
        await _close_websocket(websocket, code=1013)


async def _send_simulation_message(
    websocket: WebSocket,
    payload: dict[str, Any],
) -> None:
    await asyncio.wait_for(
        websocket.send_json(payload),
        timeout=SIMULATION_STREAM_SEND_TIMEOUT_SECONDS,
    )


@app.get("/api/simulation/orders")
def simulation_orders() -> dict[str, Any]:
    """讀取本機委託投影，不會呼叫券商或資料來源。"""
    return {"orders": get_simulation_service().orders()}


@app.get("/api/simulation/positions")
def simulation_positions() -> dict[str, Any]:
    """讀取本機已成交持倉投影，不會呼叫券商或資料來源。"""
    return {"positions": get_simulation_service().positions()}


@app.post("/api/simulation/orders", status_code=status.HTTP_201_CREATED)
def submit_simulation_order(
    request: SimulationOrderRequest,
    response: Response,
) -> dict[str, Any]:
    """送出本機紙上模擬委託；絕不呼叫 Shioaji 下單 API。"""
    try:
        order, idempotent = get_local_paper_command_service().submit_order(
            symbol=request.symbol,
            side=request.side,
            lots=request.lots,
            limit_price=request.limit_price,
            idempotency_key=request.idempotency_key,
        )
    except SimulationValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SimulationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"order": order, "idempotent": idempotent}


@app.post("/api/simulation/orders/{order_id}/cancel")
def cancel_simulation_order(
    order_id: str,
    request: SimulationCancelRequest,
    response: Response,
) -> dict[str, Any]:
    """取消仍在等待的本機紙上模擬委託。"""
    try:
        order, idempotent = get_local_paper_command_service().cancel_order(
            order_id,
            request.idempotency_key,
        )
    except SimulationValidationError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SimulationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"order": order, "idempotent": idempotent}


@app.post(
    "/api/simulation/orders/{order_id}/retry",
    status_code=status.HTTP_201_CREATED,
)
def retry_simulation_order(
    order_id: str,
    request: SimulationRetryRequest,
    response: Response,
) -> dict[str, Any]:
    """Retry the unfilled remainder as one bounded successor paper order."""
    try:
        order, idempotent = get_local_paper_command_service().retry_order(
            order_id,
            request.idempotency_key,
            limit_price=request.limit_price,
        )
    except SimulationValidationError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SimulationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"order": order, "idempotent": idempotent}


@app.post("/api/simulation/strategy-intents", status_code=status.HTTP_201_CREATED)
def submit_simulation_strategy_intent(
    request: SimulationStrategyIntentRequest,
    response: Response,
) -> dict[str, Any]:
    """Apply one strategy intent to local paper; never call a broker order API."""
    try:
        intent = StrategyPaperIntent.create(**request.model_dump())
        result = get_strategy_paper_flow_service().submit(intent)
    except SimulationValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SimulationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if result["intent_idempotent"] and result["order_idempotent"]:
        response.status_code = status.HTTP_200_OK
    return result


@app.get("/api/simulation/automated-strategy")
def automated_strategy_status() -> dict[str, Any]:
    """Read the process-local automated paper-strategy state."""
    return get_automated_strategy_controller().status()


@app.post(
    "/api/simulation/automated-strategy/start",
    status_code=status.HTTP_201_CREATED,
)
def start_automated_strategy(
    request: AutomatedStrategyStartRequest,
    response: Response,
) -> dict[str, Any]:
    """Explicitly start one bounded Momentum local-paper session."""
    try:
        config = AutomatedStrategyConfig.create(**request.model_dump())
        result = get_automated_strategy_controller().start(config)
        response.status_code = status.HTTP_201_CREATED
        return result
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AutomatedStrategyStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/simulation/automated-strategy/stop")
def stop_automated_strategy() -> dict[str, Any]:
    """Stop producing new intents; existing local-paper positions are retained."""
    try:
        return get_automated_strategy_controller().stop()
    except AutomatedStrategyStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


# ---------------------------------------------------------------------------
# Historical backtest — data-only, durable, and independent from simulation.
# ---------------------------------------------------------------------------


@app.get("/api/backtests/capabilities")
def backtest_capabilities() -> dict[str, Any]:
    return get_backtest_service().capabilities()


@app.get("/api/strategies")
def strategy_definitions(
    role: str | None = None,
    session_phase: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    try:
        return {
            "strategies": get_backtest_service().strategy_catalog(
                role=role,
                session_phase=session_phase,
                status=status,
            )
        }
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/strategies")
def save_strategy_definition(request: StrategyDefinitionRequest) -> dict[str, Any]:
    try:
        strategy, created = get_backtest_service().save_strategy_definition(request.model_dump())
        return {"strategy": strategy, "created": created}
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/strategies")
def backtest_strategies(side: str | None = None) -> dict[str, Any]:
    try:
        strategies = get_backtest_service().strategies(side)
        return {
            "strategies": strategies,
            "selection": {
                "mode": "SINGLE_OR_MULTI",
                "minimum_per_side": 1,
                "entry_available": sum(item["side"] == "ENTRY" for item in strategies),
                "exit_available": sum(item["side"] == "EXIT" for item in strategies),
                "aggregation_policies": ["ANY", "ALL", "AT_LEAST_N"],
            },
        }
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/datasets")
def backtest_datasets() -> dict[str, Any]:
    try:
        return {"datasets": get_backtest_service().list_datasets()}
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/datasets/incremental-sync")
def backtest_incremental_sync_status() -> dict[str, Any]:
    """Read scheduler/job state without triggering Provider synchronization."""

    try:
        schedule = (
            get_incremental_scheduler().status()
            if backtest_settings.BACKTEST_INCREMENTAL_SYNC_ENABLED
            else {
                "enabled": False,
                "state": "DISABLED",
                "timezone": "Asia/Taipei",
                "close_time": backtest_settings.BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME.strftime("%H:%M"),
                "message": "收盤後自動增量同步已停用",
            }
        )
        return {
            "schedule": schedule,
            "latest_job": get_backtest_service().latest_incremental_job(),
        }
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/datasets/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_backtest_dataset(request: DatasetSyncRequest) -> dict[str, Any]:
    try:
        return get_backtest_service().start_dataset_sync(
            years=request.years,
            symbols=request.symbols,
            symbol_limit=request.symbol_limit,
        )
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/datasets/jobs/{job_id}")
def backtest_dataset_job(job_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().dataset_job(job_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/datasets/jobs/{job_id}/cancel")
def cancel_backtest_dataset_job(job_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().cancel_dataset_job(job_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/runs", status_code=status.HTTP_201_CREATED)
def create_backtest_run(
    request: BacktestRunRequest,
    response: Response,
) -> dict[str, Any]:
    try:
        run, idempotent = get_backtest_service().create_run(**request.model_dump())
    except Exception as error:
        raise _backtest_http_error(error) from error
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"run": run, "idempotent": idempotent}


@app.get("/api/backtests/runs")
def backtest_runs() -> dict[str, Any]:
    try:
        return {"runs": get_backtest_service().list_runs()}
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}")
def backtest_run(run_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().get_run(run_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/runs/{run_id}/cancel")
def cancel_backtest_run(run_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().cancel_run(run_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/runs/{run_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_backtest_run(run_id: str, request: SimulationCancelRequest, response: Response) -> dict[str, Any]:
    try:
        run, idempotent = get_backtest_service().retry_run(
            run_id,
            idempotency_key=request.idempotency_key,
        )
    except Exception as error:
        raise _backtest_http_error(error) from error
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"run": run, "idempotent": idempotent}


@app.post("/api/backtests/runs/{run_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_backtest_run(
    run_id: str,
    request: BacktestCloneRequest,
    response: Response,
) -> dict[str, Any]:
    try:
        run, idempotent = get_backtest_service().clone_run(
            run_id,
            overrides=request.overrides,
            idempotency_key=request.idempotency_key,
            change_note=request.change_note,
        )
    except Exception as error:
        raise _backtest_http_error(error) from error
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"run": run, "idempotent": idempotent}


@app.get("/api/backtests/runs/{run_id}/summary")
def backtest_summary(run_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().summary(run_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/equity")
def backtest_equity(run_id: str) -> dict[str, Any]:
    try:
        return {"daily_equity": get_backtest_service().result(run_id).get("daily_equity", [])}
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/drawdown")
def backtest_drawdown(run_id: str) -> dict[str, Any]:
    try:
        return {"drawdown": get_backtest_service().drawdown(run_id)}
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/breakdowns")
def backtest_breakdowns(run_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().breakdowns(run_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/trades")
def backtest_trades(run_id: str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    try:
        return get_backtest_service().trades(run_id, page=page, page_size=page_size)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/trades/{trade_id}")
def backtest_trade(run_id: str, trade_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().trade(run_id, trade_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/trades/{trade_id}/chart")
def backtest_trade_chart(run_id: str, trade_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().trade_chart(run_id, trade_id)
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/runs/{run_id}/trades.csv")
def export_backtest_trades(run_id: str) -> Response:
    try:
        trades = get_backtest_service().export_trades(run_id)
    except Exception as error:
        raise _backtest_http_error(error) from error
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "trade_id", "symbol", "entry_at", "entry_price", "exit_at", "exit_price",
        "shares", "gross_pnl", "net_pnl", "entry_primary_strategy", "exit_primary_strategy",
    ])
    def primary_strategy_name(trade: dict[str, Any], side: str) -> str:
        decision = trade[f"{side}_decision"]
        primary = decision["primary_strategy_id"]
        for evaluation in decision.get("evaluations", []):
            if evaluation["strategy_id"] == primary:
                return str(evaluation["strategy_name"])
        return str(primary)

    for trade in trades:
        writer.writerow([
            trade["trade_id"],
            trade["symbol"],
            trade["entry"]["filled_at"],
            trade["entry"]["price"],
            trade["exit"]["filled_at"],
            trade["exit"]["price"],
            trade["entry"]["shares"],
            trade["gross_pnl"],
            trade["net_pnl"],
            primary_strategy_name(trade, "entry"),
            primary_strategy_name(trade, "exit"),
        ])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-trades.csv"'},
    )


@app.get("/api/backtests/runs/{run_id}/strategy-attribution")
def backtest_strategy_attribution(run_id: str, side: str | None = None) -> dict[str, Any]:
    try:
        return {"rows": get_backtest_service().strategy_attribution(run_id, side)}
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/comparisons", status_code=status.HTTP_201_CREATED)
def create_backtest_comparison(request: BacktestCompareRequest) -> dict[str, Any]:
    try:
        return get_backtest_service().compare(
            request.baseline_run_id,
            request.challenger_run_id,
        )
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/comparisons/{comparison_id}")
def backtest_comparison(comparison_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().get_comparison(comparison_id)
    except Exception as error:
        raise _backtest_http_error(error) from error
