"""FastAPI 入口：提供儀表板與本機紙上模擬 API。"""

from __future__ import annotations

import asyncio
import csv
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from ipaddress import ip_address
from io import StringIO
from pathlib import Path
from threading import RLock
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import build_provider
from backtest.application import BacktestApplicationService
from backtest.migrations import apply_migrations
from backtest.repository import BacktestIdempotencyConflict
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
from simulation.atomic_runtime import resolve_atomic_paper_entry_set
from simulation.continuous_strategy import (
    AutomatedStrategyConfig,
    AutomatedStrategyStateError,
    ContinuousPaperStrategyController,
    LocalPaperKillSwitch,
)
from simulation.service import (
    SimulationService,
    SimulationStateError,
    SimulationValidationError,
)
from simulation.strategy_flow import StrategyPaperFlowService
from atomic_strategies.registry import AtomicStrategyRegistry
from strategy_catalog.application import AtomicStrategyCatalogService, build_atomic_strategy_service
from strategy_catalog.drafts import PublishStrategyRequest
from strategy_catalog.domain import StrategyRole
from strategy_catalog.repository import StrategyCatalogConflict
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)
from strategy_catalog.web_projection import (
    draft_projection,
    template_projection,
    version_projection,
)

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
_atomic_strategy_service: AtomicStrategyCatalogService | None = None
_incremental_scheduler: AfterCloseIncrementalScheduler | None = None
_automated_strategy_controller: ContinuousPaperStrategyController | None = None
_local_paper_kill_switch = LocalPaperKillSwitch()
_runtime_composition_lock = RLock()
_atomic_strategy_csrf_token = secrets.token_urlsafe(32)
_HTTP_DEFAULT_PORTS = {"http": 80, "https": 443}
_UNTRUSTED_PROXY_HEADERS = frozenset(
    {
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-port",
        "x-forwarded-proto",
    }
)


def _is_loopback_address(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"localhost", "testclient"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _parse_http_authority(value: str) -> tuple[str, int | None]:
    raw = value.strip()
    if not raw or any(character.isspace() for character in raw) or "," in raw:
        raise HTTPException(status_code=403, detail="HTTP Host 不允許")
    parsed = urlsplit(f"//{raw}")
    if (
        not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(status_code=403, detail="HTTP Host 不允許")
    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise HTTPException(status_code=403, detail="HTTP Host 不允許") from error
    if not host or port == 0:
        raise HTTPException(status_code=403, detail="HTTP Host 不允許")
    return host, port


def _validated_loopback_http_origin(request: Request) -> tuple[str, str, int]:
    if any(header in request.headers for header in _UNTRUSTED_PROXY_HEADERS):
        raise HTTPException(status_code=403, detail="本機服務不接受 proxy forwarding headers")

    client_host = request.client.host if request.client is not None else ""
    if not _is_loopback_address(client_host):
        raise HTTPException(status_code=403, detail="本機服務只允許 loopback client")

    host, explicit_port = _parse_http_authority(request.headers.get("host", ""))
    if host == "testserver":
        if client_host.lower() != "testclient":
            raise HTTPException(status_code=403, detail="HTTP Host 不允許")
    elif host != "localhost" and not _is_loopback_address(host):
        raise HTTPException(status_code=403, detail="HTTP Host 必須是 loopback")

    scheme = str(request.scope.get("scheme", "")).lower()
    if scheme not in _HTTP_DEFAULT_PORTS:
        raise HTTPException(status_code=403, detail="HTTP scheme 不允許")
    return scheme, host, explicit_port or _HTTP_DEFAULT_PORTS[scheme]


def _parse_http_origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() not in _HTTP_DEFAULT_PORTS
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(status_code=403, detail="策略 mutation origin 不允許")
    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise HTTPException(
            status_code=403,
            detail="策略 mutation origin 不允許",
        ) from error
    if not host or port == 0:
        raise HTTPException(status_code=403, detail="策略 mutation origin 不允許")
    scheme = parsed.scheme.lower()
    return scheme, host, port or _HTTP_DEFAULT_PORTS[scheme]


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
        if _atomic_strategy_service is not None:
            _atomic_strategy_service.close()
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


@app.middleware("http")
async def enforce_loopback_http_boundary(request: Request, call_next):
    """Reject network/proxy exposure before any local-only response is produced."""
    try:
        _validated_loopback_http_origin(request)
    except HTTPException as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail},
        )
    return await call_next(request)


StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]


class SimulationOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity_shares: StrictPositiveInt | None = None
    lots: StrictPositiveInt | None = None
    limit_price: float
    idempotency_key: str


class SimulationCancelRequest(BaseModel):
    idempotency_key: str


class SimulationRetryRequest(BaseModel):
    idempotency_key: str
    limit_price: float | None = None


class AutomatedStrategyStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_strategy_set_version_id: str = Field(min_length=1, pattern=r".*\S.*")
    stop_loss_pct: str
    take_profit_pct: str
    max_daily_loss: str
    actor_id: str = Field(min_length=1, pattern=r".*\S.*")
    activation_idempotency_key: str = Field(min_length=1, pattern=r".*\S.*")


class AutomatedStrategyKillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, pattern=r".*\S.*")


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


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BacktestRetryRequest(StrictRequest):
    idempotency_key: str = Field(min_length=1)
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")


class BacktestCancelRequest(StrictRequest):
    idempotency_key: str = Field(min_length=1)
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")


class BacktestCloneRequest(StrictRequest):
    idempotency_key: str = Field(min_length=1)
    change_note: str = Field(min_length=1, pattern=r".*\S.*")
    overrides: dict[str, Any] = Field(default_factory=dict)
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")


class BacktestCompareRequest(BaseModel):
    baseline_run_id: str
    challenger_run_id: str


class BacktestQualificationWindowRequest(StrictRequest):
    label: str = Field(min_length=1, pattern=r".*\S.*")
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    oos_start: date
    oos_end: date


class BacktestQualificationProtocolRequest(StrictRequest):
    contract_version: Literal["backtest-qualification-request-v2"] = (
        "backtest-qualification-request-v2"
    )
    primary_window: BacktestQualificationWindowRequest
    walk_forward_windows: list[BacktestQualificationWindowRequest] = Field(
        default_factory=list,
        max_length=50,
    )


class BacktestQualificationCreateRequest(StrictRequest):
    baseline_run_id: str = Field(min_length=1)
    challenger_run_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1, max_length=120, pattern=r".*\S.*")
    protocol: BacktestQualificationProtocolRequest
    actor_id: str = Field(
        default="local-researcher",
        min_length=1,
        pattern=r".*\S.*",
    )
    change_note: str = Field(min_length=1, pattern=r".*\S.*")


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


class AtomicDraftCreateRequest(StrictRequest):
    strategy_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")
    change_note: str = ""


class AtomicDraftUpdateRequest(StrictRequest):
    expected_revision: int = Field(ge=1)
    parameters: dict[str, Any]
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")
    change_note: str = ""


class AtomicDraftPublishRequest(StrictRequest):
    expected_draft_revision: int = Field(ge=1)
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")
    actor_session_id: str = Field(default="local-dashboard", min_length=1, pattern=r".*\S.*")
    change_note: str = ""


class AtomicVersionCloneRequest(StrictRequest):
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")
    change_note: str = Field(min_length=1, pattern=r".*\S.*")


class AtomicStrategySetMemberRequest(StrictRequest):
    strategy_version_id: str
    strategy_id: str
    configuration_digest: str
    implementation_digest: str
    member_order: int = Field(ge=0)
    attribution_priority: int = Field(ge=0)


class AtomicStrategySetCreateRequest(StrictRequest):
    display_name_zh_tw: str
    stage: str = "ENTRY"
    policy: str = "ANY"
    minimum_trigger_count: int = Field(default=1, ge=1)
    members: list[AtomicStrategySetMemberRequest]
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")
    change_note: str = Field(min_length=1, pattern=r".*\S.*")


class AtomicBacktestRunRequest(StrictRequest):
    dataset_id: str
    strategy_set_version_id: str
    starting_cash: str = "10000000"
    position_fraction: str = "0.10"
    commission_rate: str = "0.001425"
    sell_tax_rate: str = "0.003"
    slippage_bps: str = "5"
    target_win_rate: str = "0.50"
    minimum_oos_trades: int = Field(default=30, ge=1)
    max_drawdown_guardrail: str = "0.20"
    change_note: str = ""
    baseline_run_id: str | None = None
    actor_id: str = Field(default="local-researcher", min_length=1, pattern=r".*\S.*")


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
                atomic_resolver=lambda strategy_set_version_id: (
                    resolve_atomic_paper_entry_set(
                        get_atomic_strategy_service(),
                        AtomicStrategyRegistry(),
                        strategy_set_version_id,
                    )
                ),
                kill_switch=_local_paper_kill_switch,
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


def get_atomic_strategy_service() -> AtomicStrategyCatalogService:
    """Build the PostgreSQL-only atomic catalog without simulation capabilities."""

    global _atomic_strategy_service
    with _runtime_composition_lock:
        if _atomic_strategy_service is not None:
            return _atomic_strategy_service
        if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
            raise RuntimeError("原子策略管理只支援 PostgreSQL；禁止 SQLite fallback")
        try:
            from psycopg_pool import ConnectionPool  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "使用原子策略管理前，請安裝 tw-intraday-trader[postgres]"
            ) from error
        pool = ConnectionPool(
            backtest_settings.BACKTEST_DATABASE_URL,
            min_size=1,
            max_size=max(4, backtest_settings.BACKTEST_WORKERS + 2),
            timeout=5,
            open=True,
        )
        try:
            with pool.connection() as connection:
                apply_migrations(connection)
            _atomic_strategy_service = build_atomic_strategy_service(
                database_backend="postgresql",
                pool=pool,
                owns_pool=True,
                templates=AtomicStrategyRegistry().templates(),
            )
        except Exception:
            pool.close()
            raise
        return _atomic_strategy_service


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
    if isinstance(error, BacktestIdempotencyConflict):
        return HTTPException(
            status_code=409,
            detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(error)},
        )
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, RuntimeError):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


def _atomic_http_error(error: Exception) -> HTTPException:
    if isinstance(error, StrategyCatalogConflict):
        missing = {
            "DRAFT_NOT_FOUND",
            "STRATEGY_VERSION_NOT_FOUND",
            "STRATEGY_SET_VERSION_NOT_FOUND",
        }
        return HTTPException(
            status_code=404 if error.code in missing else 409,
            detail={"code": error.code, "message": str(error), "details": error.details},
        )
    if isinstance(error, RuntimeError):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=422, detail=str(error))


def _require_atomic_mutation(
    request: Request,
    x_strategy_csrf: str | None,
) -> None:
    expected_origin = _validated_loopback_http_origin(request)
    origin = request.headers.get("origin")
    if origin and _parse_http_origin(origin) != expected_origin:
        raise HTTPException(status_code=403, detail="策略 mutation origin 不允許")
    if not x_strategy_csrf or not secrets.compare_digest(
        x_strategy_csrf,
        _atomic_strategy_csrf_token,
    ):
        raise HTTPException(status_code=403, detail="策略 mutation CSRF token 無效")


def _atomic_idempotency_key(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not 8 <= len(normalized) <= 200:
        raise HTTPException(status_code=422, detail="Idempotency-Key 長度必須介於 8 與 200")
    return normalized


def _record_atomic_audit(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    actor_id: str,
    operation_scope: str,
    idempotency_key: str,
    outcome: str,
    request_document: dict[str, Any],
    change_note: str = "",
    after_digest: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_atomic_strategy_service().record_audit_event(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        operation_scope=operation_scope,
        idempotency_key=idempotency_key,
        outcome=outcome,
        request_digest=canonical_digest(request_document),
        after_digest=after_digest,
        change_note=change_note,
        details=details or {},
    )


def _record_catalog_mutation_failure(
    error: Exception,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    actor_id: str,
    operation_scope: str,
    idempotency_key: str,
    request_document: dict[str, Any],
    change_note: str = "",
) -> None:
    _record_atomic_audit(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        operation_scope=operation_scope,
        idempotency_key=idempotency_key,
        outcome="CONFLICT" if isinstance(error, StrategyCatalogConflict) else "FAILED",
        request_document=request_document,
        change_note=change_note,
        details={"error_type": type(error).__name__, "message": str(error)},
    )


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
            quantity_shares=request.quantity_shares,
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
    http_request: Request,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    """Explicitly start one exact-version atomic Local Paper session."""
    _require_atomic_mutation(http_request, x_strategy_csrf)
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
def stop_automated_strategy(
    request: Request,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    """Stop producing new intents; existing local-paper positions are retained."""
    _require_atomic_mutation(request, x_strategy_csrf)
    try:
        return get_automated_strategy_controller().stop()
    except AutomatedStrategyStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/simulation/automated-strategy/kill-switch")
def engage_automated_strategy_kill_switch(
    payload: AutomatedStrategyKillRequest,
    request: Request,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    """Emergency-stop every process-local automated Local Paper intent."""

    _require_atomic_mutation(request, x_strategy_csrf)
    return get_automated_strategy_controller().engage_kill_switch(payload.reason)


@app.post("/api/simulation/automated-strategy/kill-switch/reset")
def reset_automated_strategy_kill_switch(
    request: Request,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    """Explicitly clear the kill switch without restarting a strategy."""

    _require_atomic_mutation(request, x_strategy_csrf)
    return get_automated_strategy_controller().reset_kill_switch()


# ---------------------------------------------------------------------------
# Atomic strategy Web management — PostgreSQL-only and historical-data-only.
# ---------------------------------------------------------------------------


@app.get("/api/atomic-strategies/capabilities")
def atomic_strategy_capabilities() -> dict[str, Any]:
    available = True
    message = "PostgreSQL 原子策略管理可用"
    try:
        get_atomic_strategy_service()
    except Exception as error:
        available = False
        message = str(error)
    return {
        "available": available,
        "database": "PostgreSQL only",
        "mutation_mode": "LOOPBACK_SINGLE_USER",
        "csrf_token": _atomic_strategy_csrf_token,
        "message": message,
        "safety": "只管理歷史回測設定；不會啟動模擬交易或券商委託。",
    }


@app.get("/api/strategy-templates")
def atomic_strategy_templates() -> dict[str, Any]:
    try:
        return {
            "templates": [
                template_projection(item)
                for item in get_atomic_strategy_service().templates()
            ]
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-templates/{strategy_id}")
def atomic_strategy_template(strategy_id: str) -> dict[str, Any]:
    try:
        return {"template": template_projection(get_atomic_strategy_service().template(strategy_id))}
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-templates/{strategy_id}/parameter-schema")
def atomic_strategy_parameter_schema(strategy_id: str) -> dict[str, Any]:
    try:
        template = get_atomic_strategy_service().template(strategy_id)
        return {
            "strategy_id": template.strategy_id,
            "parameter_schema": template.parameter_schema.schema_document,
            "parameter_schema_digest": template.parameter_schema.schema_digest,
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-versions/drafts")
def atomic_strategy_drafts(strategy_id: str | None = None) -> dict[str, Any]:
    try:
        return {
            "drafts": [
                draft_projection(item)
                for item in get_atomic_strategy_service().list_drafts(strategy_id)
            ]
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.post("/api/strategy-versions/drafts", status_code=status.HTTP_201_CREATED)
def create_atomic_strategy_draft(
    payload: AtomicDraftCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    try:
        draft = get_atomic_strategy_service().create_draft(
            payload.strategy_id,
            payload.parameters,
            actor_id=payload.actor_id,
            change_note=payload.change_note,
            idempotency_key=key,
        )
        return {"draft": draft_projection(draft)}
    except Exception as error:
        _record_catalog_mutation_failure(
            error,
            action="STRATEGY_DRAFT_CREATE",
            resource_type="STRATEGY_TEMPLATE",
            resource_id=payload.strategy_id,
            actor_id=payload.actor_id,
            operation_scope=f"strategy-draft:create:{payload.strategy_id}",
            idempotency_key=key,
            request_document=payload.model_dump(),
            change_note=payload.change_note,
        )
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-versions/drafts/{draft_id}")
def atomic_strategy_draft(draft_id: str) -> dict[str, Any]:
    try:
        return {"draft": draft_projection(get_atomic_strategy_service().get_draft(draft_id))}
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.put("/api/strategy-versions/drafts/{draft_id}")
def update_atomic_strategy_draft(
    draft_id: str,
    payload: AtomicDraftUpdateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    try:
        draft = get_atomic_strategy_service().update_draft(
            draft_id,
            payload.parameters,
            expected_revision=payload.expected_revision,
            actor_id=payload.actor_id,
            change_note=payload.change_note,
            idempotency_key=key,
        )
        return {"draft": draft_projection(draft)}
    except Exception as error:
        _record_catalog_mutation_failure(
            error,
            action="STRATEGY_DRAFT_UPDATE",
            resource_type="STRATEGY_DRAFT",
            resource_id=draft_id,
            actor_id=payload.actor_id,
            operation_scope=f"strategy-draft:update:{draft_id}",
            idempotency_key=key,
            request_document=payload.model_dump(),
            change_note=payload.change_note,
        )
        raise _atomic_http_error(error) from error


@app.post("/api/strategy-versions/drafts/{draft_id}/validate")
def validate_atomic_strategy_draft(
    draft_id: str,
    request: Request,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    try:
        return get_atomic_strategy_service().validate_draft(draft_id)
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.post("/api/strategy-versions/drafts/{draft_id}/publish")
def publish_atomic_strategy_draft(
    draft_id: str,
    payload: AtomicDraftPublishRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    try:
        result = get_atomic_strategy_service().publish(
            PublishStrategyRequest(
                draft_id=draft_id,
                idempotency_key=key,
                expected_draft_revision=payload.expected_draft_revision,
                actor_id=payload.actor_id,
                actor_session_id=payload.actor_session_id,
                change_note=payload.change_note,
            )
        )
        return {
            "publish": {
                "publish_operation_id": result.publish_operation_id,
                "draft_id": result.draft_id,
                "strategy_version_id": result.strategy_version_id,
                "published_event_id": result.published_event_id,
                "version_number": result.version_number,
                "configuration_digest": result.configuration_digest,
                "result_digest": result.result_digest,
                "replayed": result.replayed,
            }
        }
    except Exception as error:
        _record_catalog_mutation_failure(
            error,
            action="STRATEGY_VERSION_PUBLISH",
            resource_type="STRATEGY_DRAFT",
            resource_id=draft_id,
            actor_id=payload.actor_id,
            operation_scope=f"strategy-draft:publish:{draft_id}",
            idempotency_key=key,
            request_document=payload.model_dump(),
            change_note=payload.change_note,
        )
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-versions")
def atomic_strategy_versions(strategy_id: str | None = None) -> dict[str, Any]:
    try:
        return {
            "versions": [
                version_projection(item)
                for item in get_atomic_strategy_service().list_versions(strategy_id)
            ]
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-versions/{left_id}/diff/{right_id}")
def diff_atomic_strategy_versions(left_id: str, right_id: str) -> dict[str, Any]:
    try:
        return {"diff": get_atomic_strategy_service().diff_versions(left_id, right_id)}
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.post("/api/strategy-versions/{strategy_version_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_atomic_strategy_version(
    strategy_version_id: str,
    payload: AtomicVersionCloneRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    try:
        draft = get_atomic_strategy_service().clone_version(
            strategy_version_id,
            actor_id=payload.actor_id,
            change_note=payload.change_note,
            idempotency_key=key,
        )
        return {"draft": draft_projection(draft)}
    except Exception as error:
        _record_catalog_mutation_failure(
            error,
            action="STRATEGY_VERSION_CLONE",
            resource_type="STRATEGY_VERSION",
            resource_id=strategy_version_id,
            actor_id=payload.actor_id,
            operation_scope=f"strategy-version:clone:{strategy_version_id}",
            idempotency_key=key,
            request_document=payload.model_dump(),
            change_note=payload.change_note,
        )
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-versions/{strategy_version_id}")
def atomic_strategy_version(strategy_version_id: str) -> dict[str, Any]:
    try:
        return {
            "version": version_projection(
                get_atomic_strategy_service().get_version(strategy_version_id)
            )
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-sets")
def atomic_strategy_sets() -> dict[str, Any]:
    try:
        return {
            "strategy_sets": [
                item.to_dict() | {"snapshot_digest": item.snapshot_digest}
                for item in get_atomic_strategy_service().list_strategy_sets()
            ]
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.post("/api/strategy-sets", status_code=status.HTTP_201_CREATED)
def create_atomic_strategy_set(
    payload: AtomicStrategySetCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    try:
        stable_id = uuid5(NAMESPACE_URL, f"tw-intraday-trader:strategy-set:{key}").hex
        snapshot = ExactStrategySetSnapshot(
            strategy_set_version_id=f"strategy-set-version-{stable_id}",
            strategy_set_id=f"strategy-set-{stable_id}",
            version_number=1,
            display_name_zh_tw=payload.display_name_zh_tw,
            stage=StrategyRole(payload.stage.strip().upper()),
            policy=CompositionPolicy(payload.policy.strip().upper()),
            members=tuple(
                StrategySetMemberSnapshot(
                    strategy_version_id=item.strategy_version_id,
                    strategy_id=item.strategy_id,
                    role=StrategyRole(payload.stage.strip().upper()),
                    configuration_digest=item.configuration_digest,
                    implementation_digest=item.implementation_digest,
                    member_order=item.member_order,
                    attribution_priority=item.attribution_priority,
                )
                for item in payload.members
            ),
            minimum_trigger_count=payload.minimum_trigger_count,
        )
        created = get_atomic_strategy_service().save_strategy_set(
            snapshot,
            actor_id=payload.actor_id,
            idempotency_key=key,
            change_note=payload.change_note,
        )
        return {
            "strategy_set": snapshot.to_dict() | {"snapshot_digest": snapshot.snapshot_digest},
            "created": created,
        }
    except Exception as error:
        stable_id = uuid5(NAMESPACE_URL, f"tw-intraday-trader:strategy-set:{key}").hex
        _record_catalog_mutation_failure(
            error,
            action="STRATEGY_SET_CREATE",
            resource_type="STRATEGY_SET_VERSION",
            resource_id=f"strategy-set-version-{stable_id}",
            actor_id=payload.actor_id,
            operation_scope=f"strategy-set:create:strategy-set-{stable_id}",
            idempotency_key=key,
            request_document=payload.model_dump(),
            change_note=payload.change_note,
        )
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-sets/{strategy_set_version_id}")
def atomic_strategy_set(strategy_set_version_id: str) -> dict[str, Any]:
    try:
        snapshot = get_atomic_strategy_service().get_strategy_set(strategy_set_version_id)
        return {
            "strategy_set": snapshot.to_dict() | {"snapshot_digest": snapshot.snapshot_digest}
        }
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.get("/api/strategy-audit-events")
def atomic_strategy_audit_events(limit: int = 100) -> dict[str, Any]:
    try:
        return {"audit_events": list(get_atomic_strategy_service().list_audit_events(limit=limit))}
    except Exception as error:
        raise _atomic_http_error(error) from error


@app.post("/api/backtests/runs/atomic", status_code=status.HTTP_201_CREATED)
def create_atomic_backtest_run(
    payload: AtomicBacktestRunRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    request_document = payload.model_dump()
    try:
        values = dict(request_document)
        values.pop("actor_id")
        run, idempotent = get_backtest_service().create_atomic_run(
            **values,
            idempotency_key=key,
        )
    except Exception as error:
        _record_atomic_audit(
            action="ATOMIC_BACKTEST_RUN_CREATE",
            resource_type="BACKTEST_RUN",
            resource_id=payload.strategy_set_version_id,
            actor_id=payload.actor_id,
            operation_scope="backtest-run:create:atomic",
            idempotency_key=key,
            outcome="CONFLICT" if isinstance(error, (BacktestIdempotencyConflict, StrategyCatalogConflict)) else "FAILED",
            request_document=request_document,
            change_note=payload.change_note,
            details={"error_type": type(error).__name__, "message": str(error)},
        )
        if isinstance(error, StrategyCatalogConflict):
            raise _atomic_http_error(error) from error
        raise _backtest_http_error(error) from error
    _record_atomic_audit(
        action="ATOMIC_BACKTEST_RUN_CREATE",
        resource_type="BACKTEST_RUN",
        resource_id=run["run_id"],
        actor_id=payload.actor_id,
        operation_scope="backtest-run:create:atomic",
        idempotency_key=key,
        outcome="REPLAYED" if idempotent else "SUCCESS",
        request_document=request_document,
        change_note=payload.change_note,
        after_digest=run["config_digest"],
    )
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"run": run, "idempotent": idempotent}


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
def cancel_backtest_run(
    run_id: str,
    request: Request,
    payload: BacktestCancelRequest | None = None,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    atomic = False
    try:
        existing = get_backtest_service().get_run(run_id)
        atomic = existing["config"].get("atomic_strategy_run_snapshot") is not None
        if atomic:
            _require_atomic_mutation(request, x_strategy_csrf)
            if payload is None:
                raise HTTPException(status_code=422, detail="atomic run cancel 需要 idempotency_key 與 actor_id")
        if atomic and payload is not None:
            result, replayed = get_backtest_service().cancel_atomic_run(
                run_id,
                idempotency_key=payload.idempotency_key,
                actor_id=payload.actor_id,
                request_digest=canonical_digest(payload.model_dump()),
            )
            if replayed:
                _record_atomic_audit(
                    action="ATOMIC_BACKTEST_RUN_CANCEL",
                    resource_type="BACKTEST_RUN",
                    resource_id=run_id,
                    actor_id=payload.actor_id,
                    operation_scope=f"backtest-run:cancel:{run_id}",
                    idempotency_key=payload.idempotency_key,
                    outcome="REPLAYED",
                    request_document=payload.model_dump(),
                    after_digest=result["config_digest"],
                )
        else:
            result = get_backtest_service().cancel_run(run_id)
        return result
    except HTTPException:
        raise
    except Exception as error:
        if atomic and payload is not None:
            _record_atomic_audit(
                action="ATOMIC_BACKTEST_RUN_CANCEL",
                resource_type="BACKTEST_RUN",
                resource_id=run_id,
                actor_id=payload.actor_id,
                operation_scope=f"backtest-run:cancel:{run_id}",
                idempotency_key=payload.idempotency_key,
                outcome="CONFLICT" if isinstance(error, BacktestIdempotencyConflict) else "FAILED",
                request_document=payload.model_dump(),
                details={"error_type": type(error).__name__, "message": str(error)},
            )
        raise _backtest_http_error(error) from error


@app.post("/api/backtests/runs/{run_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_backtest_run(
    run_id: str,
    payload: BacktestRetryRequest,
    request: Request,
    response: Response,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    atomic = False
    try:
        existing = get_backtest_service().get_run(run_id)
        atomic = existing["config"].get("atomic_strategy_run_snapshot") is not None
        if atomic:
            _require_atomic_mutation(request, x_strategy_csrf)
        run, idempotent = get_backtest_service().retry_run(
            run_id,
            idempotency_key=payload.idempotency_key,
        )
    except HTTPException:
        raise
    except Exception as error:
        if atomic:
            _record_atomic_audit(
                action="ATOMIC_BACKTEST_RUN_RETRY",
                resource_type="BACKTEST_RUN",
                resource_id=run_id,
                actor_id=payload.actor_id,
                operation_scope=f"backtest-run:retry:{run_id}",
                idempotency_key=payload.idempotency_key,
                outcome="CONFLICT" if isinstance(error, BacktestIdempotencyConflict) else "FAILED",
                request_document=payload.model_dump(),
                details={"error_type": type(error).__name__, "message": str(error)},
            )
        raise _backtest_http_error(error) from error
    if atomic:
        _record_atomic_audit(
            action="ATOMIC_BACKTEST_RUN_RETRY",
            resource_type="BACKTEST_RUN",
            resource_id=run["run_id"],
            actor_id=payload.actor_id,
            operation_scope=f"backtest-run:retry:{run_id}",
            idempotency_key=payload.idempotency_key,
            outcome="REPLAYED" if idempotent else "SUCCESS",
            request_document=payload.model_dump(),
            after_digest=run["config_digest"],
        )
    if idempotent:
        response.status_code = status.HTTP_200_OK
    return {"run": run, "idempotent": idempotent}


@app.post("/api/backtests/runs/{run_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_backtest_run(
    run_id: str,
    payload: BacktestCloneRequest,
    request: Request,
    response: Response,
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    atomic = False
    try:
        existing = get_backtest_service().get_run(run_id)
        atomic = existing["config"].get("atomic_strategy_run_snapshot") is not None
        if atomic:
            _require_atomic_mutation(request, x_strategy_csrf)
        run, idempotent = get_backtest_service().clone_run(
            run_id,
            overrides=payload.overrides,
            idempotency_key=payload.idempotency_key,
            change_note=payload.change_note,
        )
    except HTTPException:
        raise
    except Exception as error:
        if atomic:
            _record_atomic_audit(
                action="ATOMIC_BACKTEST_RUN_CLONE",
                resource_type="BACKTEST_RUN",
                resource_id=run_id,
                actor_id=payload.actor_id,
                operation_scope=f"backtest-run:clone:{run_id}",
                idempotency_key=payload.idempotency_key,
                outcome="CONFLICT" if isinstance(error, BacktestIdempotencyConflict) else "FAILED",
                request_document=payload.model_dump(),
                change_note=payload.change_note,
                details={"error_type": type(error).__name__, "message": str(error)},
            )
        raise _backtest_http_error(error) from error
    if atomic:
        _record_atomic_audit(
            action="ATOMIC_BACKTEST_RUN_CLONE",
            resource_type="BACKTEST_RUN",
            resource_id=run["run_id"],
            actor_id=payload.actor_id,
            operation_scope=f"backtest-run:clone:{run_id}",
            idempotency_key=payload.idempotency_key,
            outcome="REPLAYED" if idempotent else "SUCCESS",
            request_document=payload.model_dump(),
            change_note=payload.change_note,
            after_digest=run["config_digest"],
        )
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


@app.post("/api/backtests/qualifications", status_code=status.HTTP_201_CREATED)
def create_backtest_qualification(
    payload: BacktestQualificationCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_strategy_csrf: str | None = Header(default=None, alias="X-Strategy-CSRF"),
) -> dict[str, Any]:
    _require_atomic_mutation(request, x_strategy_csrf)
    key = _atomic_idempotency_key(idempotency_key)
    request_document = payload.model_dump(mode="json")
    try:
        qualification, replayed = get_backtest_service().qualify_runs(
            baseline_run_id=payload.baseline_run_id,
            challenger_run_id=payload.challenger_run_id,
            protocol=request_document["protocol"],
            hypothesis_id=payload.hypothesis_id,
            idempotency_key=key,
            actor_id=payload.actor_id,
            change_note=payload.change_note,
        )
    except Exception as error:
        _record_atomic_audit(
            action="BACKTEST_QUALIFICATION_CREATE",
            resource_type="BACKTEST_QUALIFICATION",
            resource_id=f"{payload.baseline_run_id}:{payload.challenger_run_id}",
            actor_id=payload.actor_id,
            operation_scope="backtest-qualification:create",
            idempotency_key=key,
            outcome=(
                "CONFLICT"
                if isinstance(error, (BacktestIdempotencyConflict, StrategyCatalogConflict))
                else "FAILED"
            ),
            request_document=request_document,
            change_note=payload.change_note,
            details={"error_type": type(error).__name__, "message": str(error)},
        )
        raise _backtest_http_error(error) from error
    _record_atomic_audit(
        action="BACKTEST_QUALIFICATION_CREATE",
        resource_type="BACKTEST_QUALIFICATION",
        resource_id=qualification["qualification_id"],
        actor_id=payload.actor_id,
        operation_scope="backtest-qualification:create",
        idempotency_key=key,
        outcome="REPLAYED" if replayed else "SUCCESS",
        request_document=request_document,
        change_note=payload.change_note,
        after_digest=qualification["evidence_digest"],
    )
    if replayed:
        response.status_code = status.HTTP_200_OK
    return {"qualification": qualification, "replayed": replayed}


@app.get("/api/backtests/qualifications")
def backtest_qualifications(limit: int = 100) -> dict[str, Any]:
    try:
        return {
            "qualifications": get_backtest_service().list_qualifications(limit=limit)
        }
    except Exception as error:
        raise _backtest_http_error(error) from error


@app.get("/api/backtests/qualifications/{qualification_id}")
def backtest_qualification(qualification_id: str) -> dict[str, Any]:
    try:
        return get_backtest_service().get_qualification(qualification_id)
    except Exception as error:
        raise _backtest_http_error(error) from error
