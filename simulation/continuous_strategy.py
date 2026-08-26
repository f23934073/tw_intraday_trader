"""Explicitly started continuous strategy control for local-paper simulation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from threading import Event, RLock, Thread, current_thread
from typing import Any, Protocol
from uuid import uuid4

from features.specifications import FeatureRequestSpec
from market_data.equity_calendar import ReviewedEquityCalendar
from runtime.clock import TAIPEI, Clock
from simulation.execution_policy import EXECUTABLE_BOOK_MAX_AGE_SECONDS
from simulation.kill_switch import DurableLocalPaperKillSwitch
from simulation.atomic_runtime import (
    AtomicPaperRuntimeResolution,
    PaperSetStatus,
)
from simulation.strategy_flow import StrategyPaperFlowService, StrategyPaperIntent


CONTINUOUS_STRATEGY_VERSION = "continuous_momentum_local_paper_v1"
CONTINUOUS_STRATEGY_ID = "momentum_acceleration_local_paper"
_ENABLED_SIGNAL_FAMILIES = frozenset(
    {"OPENING_MOMENTUM", "LIMIT_UP_MOMENTUM"}
)
_ENABLED_STAGES = frozenset(
    {"ACCELERATING", "NEAR_LIMIT_UP", "LIMIT_TOUCHED"}
)


class _StrategyFlow(Protocol):
    def submit(self, intent: StrategyPaperIntent) -> dict[str, Any]: ...

    def cancel(self, order_id: str, idempotency_key: str) -> dict[str, Any]: ...

    def retry(
        self,
        order_id: str,
        idempotency_key: str,
        *,
        limit_price: Decimal | float | int | str | None = None,
    ) -> dict[str, Any]: ...

    def activate_run(
        self,
        *,
        owner_strategy_id: str,
        operator_max_daily_loss: Decimal,
        activation_config: Mapping[str, Any],
        actor_id: str,
        idempotency_key: str,
        occurred_at: datetime,
        expected_policy_digest: str | None = None,
    ) -> Mapping[str, Any]: ...

    def preview_run_activation(
        self,
        *,
        owner_strategy_id: str,
        operator_max_daily_loss: Decimal,
    ) -> Mapping[str, Any]: ...

    def prepare_entry_quote(
        self,
        *,
        owner_strategy_id: str,
        symbol: str,
    ) -> Mapping[str, Any]: ...

    def clear_entry_quote_watch(self, *, owner_strategy_id: str) -> None: ...


class AutomatedStrategyStateError(RuntimeError):
    """The requested controller lifecycle transition is not allowed."""


@dataclass(frozen=True)
class AutomatedStrategyConfig:
    """Operator-supplied risk limits for one bounded process-local session."""

    stop_loss_pct: Decimal
    take_profit_pct: Decimal
    max_daily_loss: Decimal
    entry_strategy_set_version_id: str | None = None
    actor_id: str = "local-operator"
    activation_idempotency_key: str = "direct-controller-start"
    poll_seconds: float = 1.0
    max_signal_age_seconds: float = 5.0
    max_quote_age_seconds: float = EXECUTABLE_BOOK_MAX_AGE_SECONDS
    entry_open: time = time(9, 0)
    entry_cutoff: time = time(13, 20)
    flatten_at: time = time(13, 25)
    session_close: time = time(13, 30)
    max_exit_attempts: int = 3

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.stop_loss_pct, "stop_loss_pct"),
            (self.take_profit_pct, "take_profit_pct"),
            (self.max_daily_loss, "max_daily_loss"),
        ):
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{field_name} 必須是大於 0 的有限數字")
        if self.stop_loss_pct >= 100:
            raise ValueError("stop_loss_pct 必須小於 100")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds 必須大於 0")
        if self.max_signal_age_seconds <= 0 or self.max_quote_age_seconds <= 0:
            raise ValueError("行情新鮮度秒數必須大於 0")
        if self.max_exit_attempts <= 0:
            raise ValueError("max_exit_attempts 必須大於 0")
        if self.entry_strategy_set_version_id is not None:
            normalized_set_id = self.entry_strategy_set_version_id.strip()
            if not normalized_set_id:
                raise ValueError("entry_strategy_set_version_id 不可為空")
            object.__setattr__(
                self, "entry_strategy_set_version_id", normalized_set_id
            )
        for value, field_name in (
            (self.actor_id, "actor_id"),
            (self.activation_idempotency_key, "activation_idempotency_key"),
        ):
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} 不可為空")
            object.__setattr__(self, field_name, normalized)
        if not (
            self.entry_open
            < self.entry_cutoff
            < self.flatten_at
            < self.session_close
        ):
            raise ValueError("自動策略交易時段設定無效")

    @classmethod
    def create(
        cls,
        *,
        stop_loss_pct: Decimal | float | int | str,
        take_profit_pct: Decimal | float | int | str,
        max_daily_loss: Decimal | float | int | str,
        entry_strategy_set_version_id: str | None = None,
        actor_id: str = "local-operator",
        activation_idempotency_key: str = "direct-controller-start",
        poll_seconds: float = 1.0,
    ) -> "AutomatedStrategyConfig":
        return cls(
            stop_loss_pct=_decimal(stop_loss_pct, "stop_loss_pct"),
            take_profit_pct=_decimal(take_profit_pct, "take_profit_pct"),
            max_daily_loss=_decimal(max_daily_loss, "max_daily_loss"),
            entry_strategy_set_version_id=entry_strategy_set_version_id,
            actor_id=actor_id,
            activation_idempotency_key=activation_idempotency_key,
            poll_seconds=poll_seconds,
        )

    def payload(self) -> dict[str, object]:
        return {
            "strategy_id": CONTINUOUS_STRATEGY_ID,
            "strategy_version": CONTINUOUS_STRATEGY_VERSION,
            "entry_strategy_set_version_id": self.entry_strategy_set_version_id,
            "actor_id": self.actor_id,
            "activation_idempotency_key": self.activation_idempotency_key,
            "lots": 1,
            "max_entries_per_session": 1,
            "stop_loss_pct": str(self.stop_loss_pct),
            "take_profit_pct": str(self.take_profit_pct),
            "max_daily_loss": str(self.max_daily_loss),
            "poll_seconds": self.poll_seconds,
            "max_signal_age_seconds": self.max_signal_age_seconds,
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "entry_open": self.entry_open.strftime("%H:%M"),
            "entry_cutoff": self.entry_cutoff.strftime("%H:%M"),
            "flatten_at": self.flatten_at.strftime("%H:%M"),
            "session_close": self.session_close.strftime("%H:%M"),
            "max_exit_attempts": self.max_exit_attempts,
        }


class ContinuousPaperStrategyController:
    """Poll one live Momentum projection and emit bounded local-paper intents."""

    def __init__(
        self,
        *,
        flow: StrategyPaperFlowService | _StrategyFlow,
        projection_reader: Callable[[], Mapping[str, Any]],
        signal_reader: Callable[[], Mapping[str, Any]],
        calendar: ReviewedEquityCalendar,
        clock: Clock,
        atomic_resolver: Callable[[str], AtomicPaperRuntimeResolution] | None = None,
        atomic_signal_reader: Callable[
            [tuple[FeatureRequestSpec, ...]], Mapping[str, Any]
        ]
        | None = None,
        kill_switch: DurableLocalPaperKillSwitch,
    ) -> None:
        self._flow = flow
        self._projection_reader = projection_reader
        self._signal_reader = signal_reader
        self._calendar = calendar
        self._clock = clock
        self._atomic_resolver = atomic_resolver
        self._atomic_signal_reader = atomic_signal_reader
        self._kill_switch = kill_switch
        self._lock = RLock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._config: AutomatedStrategyConfig | None = None
        self._run_id: str | None = None
        self._state = "STOPPED"
        self._decision = "STOPPED"
        self._message = "自動模擬策略尚未啟動"
        self._started_at: datetime | None = None
        self._last_checked_at: datetime | None = None
        self._last_action_at: datetime | None = None
        self._last_error: str | None = None
        self._last_intent: dict[str, object] | None = None
        self._last_exit_reason: str | None = None
        self._entries_submitted = 0
        self._consumed_signal_digests: set[str] = set()
        self._atomic_resolution: AtomicPaperRuntimeResolution | None = None
        self._effective_risk_evidence: Mapping[str, Any] | None = None
        kill_switch_state = str(self._kill_switch.status()["control_state"])
        if kill_switch_state != "DISENGAGED":
            self._state = "KILLED"
            self._decision = (
                "KILL_SWITCH_RECOVERY_REQUIRED"
                if kill_switch_state == "RECOVERY_REQUIRED"
                else "KILL_SWITCH_ENGAGED"
            )
            self._message = (
                "Kill Switch Journal 需要復原；禁止產生新意圖"
                if kill_switch_state == "RECOVERY_REQUIRED"
                else "全域 Local Paper kill switch 已啟用；禁止產生新意圖"
            )

    def start(
        self,
        config: AutomatedStrategyConfig,
        *,
        background: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            self._kill_switch.assert_start_allowed()
            if self._state == "RUNNING":
                raise AutomatedStrategyStateError("自動模擬策略已在執行")
            atomic_resolution = None
            effective_risk_evidence = None
            activation_config = None
            activator = None
            started_at = self._clock.now()
            if config.entry_strategy_set_version_id is not None:
                if self._atomic_resolver is None:
                    raise AutomatedStrategyStateError(
                        "尚未設定 exact Strategy Set Local Paper resolver"
                    )
                atomic_resolution = self._atomic_resolver(
                    config.entry_strategy_set_version_id
                )
                activator = getattr(self._flow, "activate_run", None)
                previewer = getattr(self._flow, "preview_run_activation", None)
                if not callable(activator) or not callable(previewer):
                    raise AutomatedStrategyStateError(
                        "exact Strategy Set flow 缺少 preview/commit activation boundary"
                    )
                activation_config = {
                    "config": config.payload(),
                    "pipeline": {
                        **atomic_resolution.pipeline.to_dict(),
                        "snapshot_digest": (
                            atomic_resolution.pipeline.snapshot_digest
                        ),
                    },
                }
                effective_risk_evidence = previewer(
                    owner_strategy_id=atomic_resolution.pipeline.owner_strategy_id,
                    operator_max_daily_loss=config.max_daily_loss,
                )
            previous_runtime = (
                self._config,
                self._atomic_resolution,
                self._effective_risk_evidence,
                self._entries_submitted,
                set(self._consumed_signal_digests),
            )
            self._config = config
            self._atomic_resolution = atomic_resolution
            self._effective_risk_evidence = effective_risk_evidence
            self._entries_submitted = 0
            self._consumed_signal_digests.clear()
            try:
                self._restore_session_ownership_locked()
                self._restore_runtime_checkpoint_locked()
                if atomic_resolution is not None:
                    assert callable(activator)
                    assert activation_config is not None
                    preview_digest = str(
                        (effective_risk_evidence or {}).get(
                            "effective_policy_digest", ""
                        )
                    )
                    committed_evidence = activator(
                        owner_strategy_id=(
                            atomic_resolution.pipeline.owner_strategy_id
                        ),
                        operator_max_daily_loss=config.max_daily_loss,
                        activation_config=activation_config,
                        actor_id=config.actor_id,
                        idempotency_key=config.activation_idempotency_key,
                        occurred_at=started_at,
                        expected_policy_digest=preview_digest,
                    )
                    if str(
                        committed_evidence.get("effective_policy_digest", "")
                    ) != preview_digest:
                        raise AutomatedStrategyStateError(
                            "Effective Hard Risk preview 與 activation commit 不一致"
                        )
                    self._effective_risk_evidence = committed_evidence
            except Exception:
                (
                    self._config,
                    self._atomic_resolution,
                    self._effective_risk_evidence,
                    self._entries_submitted,
                    previous_digests,
                ) = previous_runtime
                self._consumed_signal_digests = previous_digests
                raise
            self._run_id = uuid4().hex
            self._state = "RUNNING"
            self._decision = "STARTED"
            self._message = "自動模擬策略已啟動，等待有效盤中訊號"
            self._started_at = started_at
            self._last_checked_at = None
            self._last_action_at = None
            self._last_error = None
            self._last_intent = None
            self._last_exit_reason = None
            self._stop.clear()
            self._write_runtime_checkpoint_locked()
            if background:
                self._thread = Thread(
                    target=self._run_loop,
                    name="continuous-local-paper-strategy",
                    daemon=True,
                )
                self._thread.start()
            else:
                self._thread = None
            return self._status_locked()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=10)
            if thread.is_alive():
                raise AutomatedStrategyStateError("自動模擬策略 worker 無法停止")
        with self._lock:
            self._thread = None
            if not self._synchronize_kill_switch_locked():
                self._state = "STOPPED"
                self._decision = "STOPPED"
                self._message = "自動模擬策略已停止；既有本機持倉不會自動清除"
            self._write_runtime_checkpoint_locked()
            status = self._status_locked()
            owner = self._atomic_owner_strategy_id_locked()
        self._clear_entry_quote_watch(owner)
        return status

    def close(self) -> None:
        self.stop()

    def engage_kill_switch(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        reason: str,
    ) -> dict[str, Any]:
        transition = self._kill_switch.engage(
            actor_id=actor_id,
            operation_id=idempotency_key,
            reason=reason,
        )
        with self._lock:
            blocking = self._synchronize_kill_switch_locked()
            self._write_control_checkpoint_best_effort_locked()
            status = self._status_locked()
            owner = self._atomic_owner_strategy_id_locked()
        if blocking:
            self._clear_entry_quote_watch(owner)
        return {**status, "operation": transition["operation"]}

    def reset_kill_switch(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, Any]:
        transition = self._kill_switch.reset(
            actor_id=actor_id,
            operation_id=idempotency_key,
            reason=reason,
            expected_revision=expected_revision,
        )
        with self._lock:
            blocking = self._synchronize_kill_switch_locked()
            if not blocking and self._state == "KILLED":
                self._state = "STOPPED"
                self._decision = "STOPPED"
                self._message = "kill switch 已解除；必須重新手動啟動策略"
            self._write_control_checkpoint_best_effort_locked()
            status = self._status_locked()
            owner = self._atomic_owner_strategy_id_locked()
        if blocking:
            self._clear_entry_quote_watch(owner)
        return {**status, "operation": transition["operation"]}

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._synchronize_kill_switch_locked()
            return self._status_locked()

    def run_once(self) -> dict[str, Any]:
        with self._lock:
            if self._state != "RUNNING":
                return self._status_locked()
            try:
                self._evaluate_locked(self._clock.now())
                self._write_runtime_checkpoint_locked()
            except Exception as error:
                self._state = "ERROR"
                self._decision = "ERROR"
                self._message = "自動模擬策略發生未處理錯誤並已停止"
                self._last_error = str(error)
                self._stop.set()
            return self._status_locked()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            with self._lock:
                config = self._config
                state = self._state
            if config is None or state != "RUNNING":
                return
            self._stop.wait(config.poll_seconds)

    def _evaluate_locked(self, now: datetime) -> None:
        config = self._require_config()
        self._last_checked_at = now
        if self._kill_switch.engaged:
            self._state = "KILLED"
            recovery_required = (
                self._kill_switch.control_state.value == "RECOVERY_REQUIRED"
            )
            self._decision = (
                "KILL_SWITCH_RECOVERY_REQUIRED"
                if recovery_required
                else "KILL_SWITCH_ENGAGED"
            )
            self._message = (
                "Kill Switch Journal 需要復原；禁止產生新意圖"
                if recovery_required
                else "全域 Local Paper kill switch 已啟用；禁止產生新意圖"
            )
            self._stop.set()
            return
        local = now.astimezone(TAIPEI)
        try:
            trading_day = self._calendar.is_trading_day(local.date())
        except ValueError as error:
            self._set_decision("BLOCKED_CALENDAR", str(error))
            return
        if not trading_day:
            self._set_decision("WAITING_MARKET", "今天不是 TWSE 交易日")
            return

        local_time = local.time().replace(tzinfo=None)
        projection = self._projection_reader()
        session = _mapping(projection.get("session"), "simulation.session")
        positions = _mapping_list(projection.get("positions"), "positions")
        orders = _mapping_list(projection.get("orders"), "orders")

        if local_time >= config.session_close:
            self._reconcile_after_close(positions, orders)
            return
        if local_time < config.entry_open:
            self._set_decision("WAITING_MARKET", "目前不在 09:00-13:30 交易時段")
            return

        if str(session.get("stream_health", "")) != "HEALTHY":
            self._set_decision("BLOCKED_DATA", "本機模擬行情 stream 不健康")
            return
        if not (
            session.get("quote_mode") == "SHIOAJI_TICK_BIDASK"
            and session.get("streaming") is True
        ):
            self._set_decision(
                "BLOCKED_DATA",
                "自動策略只允許 Shioaji Tick／BidAsk 驅動的本機模擬",
            )
            return
        if len(positions) > 1:
            self._set_decision(
                "BLOCKED_INVARIANT",
                "自動策略只允許最多一個本機持倉",
            )
            return
        if any(
            str(order.get("status"))
            in {"SUBMITTED", "PENDING", "PARTIALLY_FILLED"}
            for order in orders
        ):
            self._set_decision("WAITING_ORDER", "等待既有本機委託進入終態")
            return
        if positions:
            self._evaluate_position(positions[0], orders, local, config)
            return
        if self._daily_loss(session) >= config.max_daily_loss:
            self._set_decision(
                "BLOCKED_DAILY_LOSS",
                "本機模擬權益已達交易日開盤權益的每日最大虧損",
            )
            return
        if self._entries_submitted >= 1:
            self._set_decision("SESSION_COMPLETE", "本次自動策略 session 已完成一筆進場")
            return
        if local_time >= config.entry_cutoff:
            self._set_decision("WAITING_MARKET", "已超過 13:20 自動進場截止時間")
            return

        self._evaluate_entry(local, config)

    def _reconcile_after_close(
        self,
        positions: list[Mapping[str, Any]],
        orders: list[Mapping[str, Any]],
    ) -> None:
        active = [
            order
            for order in orders
            if str(order.get("status"))
            in {"SUBMITTED", "PENDING", "PARTIALLY_FILLED"}
            and str(order.get("origin")) == "STRATEGY_AUTOMATED"
            and str(order.get("strategy_id")) == self._owner_strategy_id()
        ]
        for order in active:
            order_id = str(order.get("order_id") or "").strip()
            if not order_id:
                continue
            self._flow.cancel(
                order_id,
                f"auto:{self._run_id}:cancel:{order_id}:after-close",
            )
        owned_positions = [
            position
            for position in positions
            if str(position.get("owner_origin")) == "STRATEGY_AUTOMATED"
            and str(position.get("owner_strategy_id")) == self._owner_strategy_id()
        ]
        if owned_positions or any(str(order.get("side")) == "SELL" for order in active):
            self._set_decision(
                "ALERT_EXIT_UNRESOLVED",
                "13:30 後仍有自動策略持倉或未完成出場；已取消未完成委託並要求人工處理",
            )
            return
        if active:
            self._set_decision(
                "ALERT_ENTRY_CANCELLED_AFTER_CLOSE",
                "13:30 後仍有未完成進場；已取消並停止本交易日策略",
            )
            return
        self._set_decision("WAITING_MARKET", "目前不在 09:00-13:30 交易時段")

    def _evaluate_entry(
        self,
        now: datetime,
        config: AutomatedStrategyConfig,
    ) -> None:
        if self._atomic_resolution is not None:
            self._evaluate_atomic_entry(now, config)
            return
        snapshot = self._signal_reader()
        source = _mapping(snapshot.get("source"), "momentum.source")
        if not (
            snapshot.get("status") == "live"
            and source.get("is_live") is True
            and source.get("connection_state") == "RUNNING"
            and source.get("data_health") == "HEALTHY"
        ):
            self._set_decision("BLOCKED_SIGNAL", "Momentum 即時來源尚未 ready")
            return

        candidates: list[tuple[int, str, Mapping[str, Any], datetime, Decimal]] = []
        blocked_reason: str | None = None
        for item in _mapping_list(snapshot.get("items"), "momentum.items"):
            signal = _optional_mapping(item.get("signal"))
            intraday = _optional_mapping(item.get("intraday"))
            price = _optional_mapping(intraday.get("price")) if intraday else None
            if not signal or not price:
                continue
            if not (
                item.get("availability") == "EVALUATED"
                and item.get("current_stage") in _ENABLED_STAGES
                and signal.get("family") in _ENABLED_SIGNAL_FAMILIES
                and signal.get("evaluation_status") == "TRIGGERED"
                and signal.get("momentum_acceleration_confirmed") is True
                and signal.get("data_health") == "HEALTHY"
                and price.get("status") == "VALID"
            ):
                continue
            source_at = _aware_datetime(price.get("source_as_of"), "price.source_as_of")
            age_seconds = (now - source_at).total_seconds()
            if age_seconds < 0 or age_seconds > config.max_signal_age_seconds:
                blocked_reason = "Momentum 訊號價格已過期"
                continue
            digest = str(signal.get("digest") or "").strip()
            symbol = str(item.get("symbol") or "").strip().upper()
            config_version = str(signal.get("config_version") or "").strip()
            if not digest or not symbol or not config_version:
                blocked_reason = "Momentum 訊號缺少可稽核識別"
                continue
            if digest in self._consumed_signal_digests:
                continue
            limit_price = _positive_decimal(price.get("value"), "price.value")
            score = int(signal.get("evidence_score") or 0)
            candidates.append((score, symbol, item, source_at, limit_price))

        if not candidates:
            self._set_decision(
                "BLOCKED_SIGNAL" if blocked_reason else "WAITING_SIGNAL",
                blocked_reason or "等待新鮮且已確認加速的 Momentum 訊號",
            )
            return

        _, symbol, item, signaled_at, limit_price = sorted(
            candidates,
            key=lambda value: (-value[0], value[1]),
        )[0]
        signal = _mapping(item["signal"], "momentum.signal")
        digest = str(signal["digest"])
        short_digest = digest if len(digest) <= 32 else digest[:32]
        intent = StrategyPaperIntent.create(
            intent_id=f"auto:{self._run_id}:entry:{short_digest}",
            strategy_id=CONTINUOUS_STRATEGY_ID,
            strategy_version=(
                f"{CONTINUOUS_STRATEGY_VERSION}:{signal['config_version']}"
            ),
            symbol=symbol,
            side="BUY",
            lots=1,
            limit_price=limit_price,
            signaled_at=signaled_at,
        )
        result = self._flow.submit(intent)
        self._consumed_signal_digests.add(digest)
        self._entries_submitted += 1
        self._last_action_at = now
        self._last_intent = intent.journal_payload()
        order_status = str(_mapping(result.get("order"), "flow.order").get("status"))
        decision = "ENTRY_REJECTED" if order_status == "REJECTED" else "ENTRY_SUBMITTED"
        self._set_decision(decision, f"已送出 {symbol} 一張本機模擬進場意圖")

    def _evaluate_atomic_entry(
        self,
        now: datetime,
        config: AutomatedStrategyConfig,
    ) -> None:
        resolution = self._atomic_resolution
        if resolution is None:
            raise AutomatedStrategyStateError("atomic Local Paper runtime 尚未解析")
        snapshot = (
            self._atomic_signal_reader(resolution.projection_requests)
            if self._atomic_signal_reader is not None
            else self._signal_reader()
        )
        result = resolution.evaluate_projection(
            snapshot,
            evaluated_at=now,
            max_age_seconds=config.max_signal_age_seconds,
        )
        triggered = [
            item
            for item in result.triggered
            if item.decision_digest not in self._consumed_signal_digests
        ]
        if not triggered:
            if result.blocked_reasons:
                self._set_decision(
                    "BLOCKED_SIGNAL",
                    "；".join(result.blocked_reasons[:3]),
                )
                return
            unavailable = [
                item
                for item in result.candidates
                if item.status
                in {PaperSetStatus.BLOCKED, PaperSetStatus.INSUFFICIENT_DATA}
            ]
            if unavailable:
                self._set_decision(
                    "BLOCKED_SIGNAL",
                    "exact Strategy Set 尚缺必要 Feature evidence",
                )
            else:
                self._set_decision(
                    "WAITING_SIGNAL",
                    "等待 exact Strategy Set 產生新觸發",
                )
            return

        decision = sorted(triggered, key=lambda item: item.symbol)[0]
        quote_preparer = getattr(self._flow, "prepare_entry_quote", None)
        if not callable(quote_preparer):
            raise AutomatedStrategyStateError(
                "exact Strategy Set flow 缺少 pre-order quote watch boundary"
            )
        quote_evidence = quote_preparer(
            owner_strategy_id=resolution.pipeline.owner_strategy_id,
            symbol=decision.symbol,
        )
        if quote_evidence.get("ready") is not True:
            self._set_decision(
                "WAITING_BOOK",
                f"等待 {decision.symbol} fresh BidAsk 暖機後再進入 Hard Risk",
            )
            return
        short_digest = decision.decision_digest[:32]
        intent = StrategyPaperIntent.create(
            intent_id=f"auto:{self._run_id}:entry:{short_digest}",
            strategy_id=resolution.pipeline.owner_strategy_id,
            strategy_version=(
                f"local-paper-pipeline:{resolution.pipeline.snapshot_digest}"
            ),
            symbol=decision.symbol,
            side="BUY",
            lots=1,
            limit_price=decision.entry_limit_price,
            signaled_at=decision.event_at,
            decision_evidence={
                "pipeline": resolution.pipeline.to_dict(),
                "pipeline_digest": resolution.pipeline.snapshot_digest,
                "strategy_set_decision": decision.evidence(),
                "pre_order_quote_watch": dict(quote_evidence),
            },
        )
        try:
            flow_result = self._flow.submit(intent)
        finally:
            self._clear_entry_quote_watch(
                resolution.pipeline.owner_strategy_id
            )
        self._consumed_signal_digests.add(decision.decision_digest)
        self._entries_submitted += 1
        self._last_action_at = now
        self._last_intent = intent.journal_payload()
        order_status = str(
            _mapping(flow_result.get("order"), "flow.order").get("status")
        )
        outcome = "ENTRY_REJECTED" if order_status == "REJECTED" else "ENTRY_SUBMITTED"
        self._set_decision(
            outcome,
            f"已依 exact Strategy Set 送出 {decision.symbol} 一張本機模擬進場意圖",
        )

    def _atomic_owner_strategy_id_locked(self) -> str | None:
        if self._atomic_resolution is None:
            return None
        return self._atomic_resolution.pipeline.owner_strategy_id

    def _clear_entry_quote_watch(self, owner_strategy_id: str | None) -> None:
        if owner_strategy_id is None:
            return
        clearer = getattr(self._flow, "clear_entry_quote_watch", None)
        if callable(clearer):
            clearer(owner_strategy_id=owner_strategy_id)

    def _evaluate_position(
        self,
        position: Mapping[str, Any],
        orders: list[Mapping[str, Any]],
        now: datetime,
        config: AutomatedStrategyConfig,
    ) -> None:
        symbol = str(position.get("symbol") or "").strip().upper()
        quantity = int(position.get("quantity") or 0)
        if not symbol or quantity != 1_000:
            self._set_decision(
                "BLOCKED_INVARIANT",
                "自動策略只管理一張整股本機持倉",
            )
            return
        if not (
            position.get("owner_origin") == "STRATEGY_AUTOMATED"
            and position.get("owner_strategy_id") == self._owner_strategy_id()
        ):
            self._set_decision(
                "BLOCKED_OWNERSHIP",
                f"{symbol} 持倉不屬於目前自動策略，禁止自動賣出",
            )
            return
        quote_at = _aware_datetime(
            position.get("book_received_at"),
            "position.book_received_at",
        )
        quote_age = (now - quote_at).total_seconds()
        if quote_age < 0 or quote_age > config.max_quote_age_seconds:
            self._set_decision("BLOCKED_DATA", "持倉 BidAsk 已過期，禁止自動出場")
            return

        bid_price = _positive_decimal(position.get("bid_price"), "position.bid_price")
        retry_candidates = [
            order
            for order in orders
            if str(order.get("symbol")) == symbol
            and str(order.get("side")) == "SELL"
            and str(order.get("origin")) == "STRATEGY_AUTOMATED"
            and str(order.get("strategy_id")) == self._owner_strategy_id()
            and str(order.get("status")) in {"CANCELLED", "EXPIRED"}
            and int(order.get("remaining_quantity") or 0) > 0
        ]
        if retry_candidates:
            previous = max(
                retry_candidates,
                key=lambda item: (int(item.get("attempt") or 1), str(item.get("updated_at") or "")),
            )
            previous_attempt = int(previous.get("attempt") or 1)
            if previous_attempt >= config.max_exit_attempts:
                self._set_decision(
                    "ALERT_EXIT_RETRY_EXHAUSTED",
                    f"{symbol} 出場已達 {config.max_exit_attempts} 次嘗試，要求人工處理",
                )
                return
            previous_order_id = str(previous["order_id"])
            next_attempt = previous_attempt + 1
            result = self._flow.retry(
                previous_order_id,
                f"auto:{self._run_id}:retry:{previous_order_id}:{next_attempt}",
                limit_price=bid_price,
            )
            self._last_action_at = now
            self._last_intent = {
                "kind": "EXIT_RETRY",
                "predecessor_order_id": previous_order_id,
                "attempt": next_attempt,
                "symbol": symbol,
                "limit_price": str(bid_price),
            }
            self._last_exit_reason = str(previous.get("reason") or "EXIT_RETRY")
            self._record_exit_result(
                result,
                symbol=symbol,
                reason="EXIT_RETRY",
            )
            return

        pnl_pct = _decimal(position.get("unrealized_pnl_pct"), "unrealized_pnl_pct")
        local_time = now.time().replace(tzinfo=None)
        reason = None
        if pnl_pct <= -config.stop_loss_pct:
            reason = "STOP_LOSS"
        elif pnl_pct >= config.take_profit_pct:
            reason = "TAKE_PROFIT"
        elif local_time >= config.flatten_at:
            reason = "END_OF_SESSION"
        if reason is None:
            self._set_decision("POSITION_OPEN", f"持續監控 {symbol} 本機模擬持倉")
            return

        intent = StrategyPaperIntent.create(
            intent_id=f"auto:{self._run_id}:{symbol}:exit:{reason.lower()}",
            strategy_id=self._owner_strategy_id(),
            strategy_version=f"{self._owner_strategy_version()}:exit:{reason.lower()}",
            symbol=symbol,
            side="SELL",
            lots=1,
            limit_price=bid_price,
            signaled_at=now,
        )
        result = self._flow.submit(intent)
        self._last_action_at = now
        self._last_intent = intent.journal_payload()
        self._last_exit_reason = reason
        self._record_exit_result(result, symbol=symbol, reason=reason)

    def _record_exit_result(
        self,
        result: Mapping[str, Any],
        *,
        symbol: str,
        reason: str,
    ) -> None:
        order = _mapping(result.get("order"), "flow.order")
        order_status = str(order.get("status"))
        if order_status == "REJECTED":
            self._set_decision(
                "EXIT_REJECTED",
                f"{symbol} {reason} 本機模擬出場遭拒絕：{order.get('reason') or '未提供原因'}",
            )
        elif order_status == "FILLED":
            remaining = _mapping_list(
                self._projection_reader().get("positions"),
                "positions",
            )
            if any(str(item.get("symbol")) == symbol for item in remaining):
                self._set_decision(
                    "ALERT_EXIT_FILL_UNCONFIRMED",
                    f"{symbol} 出場委託已成交但持倉投影尚未關閉",
                )
            else:
                self._set_decision(
                    "EXIT_FILLED",
                    f"{symbol} {reason} 本機模擬出場已成交且持倉已關閉",
                )
        elif order_status == "PARTIALLY_FILLED":
            self._set_decision(
                "EXIT_PARTIALLY_FILLED",
                f"{symbol} {reason} 本機模擬出場部分成交，持續追蹤",
            )
        elif order_status in {"CANCELLED", "EXPIRED", "RECOVERY_REQUIRED"}:
            self._set_decision(
                "ALERT_EXIT_UNRESOLVED",
                f"{symbol} {reason} 本機模擬出場未完成：{order_status}",
            )
        else:
            self._set_decision(
                "EXIT_SUBMITTED",
                f"已送出 {symbol} {reason} 本機模擬出場意圖",
            )

    def _daily_loss(self, session: Mapping[str, Any]) -> Decimal:
        opening_equity = _positive_decimal(
            session.get("opening_equity"),
            "session.opening_equity",
        )
        equity = _decimal(session.get("equity"), "session.equity")
        return max(Decimal("0"), opening_equity - equity)

    def _set_decision(self, decision: str, message: str) -> None:
        self._decision = decision
        self._message = message

    def _require_config(self) -> AutomatedStrategyConfig:
        if self._config is None:
            raise AutomatedStrategyStateError("自動模擬策略尚未設定")
        return self._config

    def _owner_strategy_id(self) -> str:
        if self._atomic_resolution is not None:
            return self._atomic_resolution.pipeline.owner_strategy_id
        return CONTINUOUS_STRATEGY_ID

    def _owner_strategy_version(self) -> str:
        if self._atomic_resolution is not None:
            return f"local-paper-pipeline:{self._atomic_resolution.pipeline.snapshot_digest}"
        return CONTINUOUS_STRATEGY_VERSION

    def _restore_session_ownership_locked(self) -> None:
        """Fail closed on another automated owner and recover one-entry state."""

        projection = self._projection_reader()
        positions = _mapping_list(projection.get("positions"), "positions")
        orders = _mapping_list(projection.get("orders"), "orders")
        expected_owner = self._owner_strategy_id()
        automated_owners = {
            str(item.get("owner_strategy_id") or "").strip()
            for item in positions
            if item.get("owner_origin") == "STRATEGY_AUTOMATED"
        } | {
            str(item.get("strategy_id") or "").strip()
            for item in orders
            if item.get("origin") == "STRATEGY_AUTOMATED"
        }
        automated_owners.discard("")
        foreign = sorted(automated_owners - {expected_owner})
        if foreign:
            raise AutomatedStrategyStateError(
                "偵測到其他自動策略 owner，必須先人工完成 recovery："
                + ", ".join(foreign)
            )
        if expected_owner in automated_owners:
            self._entries_submitted = 1

    def _restore_runtime_checkpoint_locked(self) -> None:
        reader = getattr(self._flow, "latest_checkpoint", None)
        if not callable(reader):
            return
        checkpoint = reader(
            owner_strategy_id=self._owner_strategy_id(),
            pipeline_digest=(
                self._atomic_resolution.pipeline.snapshot_digest
                if self._atomic_resolution is not None
                else None
            ),
        )
        if checkpoint is None:
            return
        try:
            entries = int(checkpoint.get("entries_submitted", 0))
            consumed = checkpoint.get("consumed_decision_digests", ())
        except (TypeError, ValueError) as error:
            raise AutomatedStrategyStateError(
                "策略 runtime checkpoint 無法重建"
            ) from error
        if entries < 0 or not isinstance(consumed, (list, tuple)):
            raise AutomatedStrategyStateError("策略 runtime checkpoint 格式無效")
        checkpoint_risk = checkpoint.get("effective_risk")
        if self._atomic_resolution is not None:
            if not isinstance(checkpoint_risk, Mapping):
                raise AutomatedStrategyStateError(
                    "策略 runtime checkpoint 缺少 Effective Hard Risk evidence"
                )
            current_digest = str(
                (self._effective_risk_evidence or {}).get(
                    "effective_policy_digest", ""
                )
            )
            if str(checkpoint_risk.get("effective_policy_digest", "")) != current_digest:
                raise AutomatedStrategyStateError(
                    "策略 runtime checkpoint 的 Effective Hard Risk 已漂移"
                )
        self._entries_submitted = max(self._entries_submitted, entries)
        self._consumed_signal_digests.update(str(item) for item in consumed)

    def _write_runtime_checkpoint_locked(self) -> None:
        writer = getattr(self._flow, "checkpoint", None)
        if not callable(writer) or self._run_id is None:
            return
        occurred_at = self._clock.now()
        writer(
            {
                "contract_version": "strategy-runtime-checkpoint-v1",
                "run_id": self._run_id,
                "owner_strategy_id": self._owner_strategy_id(),
                "pipeline_digest": (
                    self._atomic_resolution.pipeline.snapshot_digest
                    if self._atomic_resolution is not None
                    else None
                ),
                "effective_risk": (
                    dict(self._effective_risk_evidence)
                    if self._effective_risk_evidence is not None
                    else None
                ),
                "state": self._state,
                "decision": self._decision,
                "entries_submitted": self._entries_submitted,
                "consumed_decision_digests": sorted(
                    self._consumed_signal_digests
                ),
                "last_checked_at": _iso(self._last_checked_at),
                "last_action_at": _iso(self._last_action_at),
                "checkpointed_at": occurred_at.isoformat(),
            },
            occurred_at=occurred_at,
        )

    def _write_control_checkpoint_best_effort_locked(self) -> None:
        """Keep durable control authoritative if a run checkpoint cannot append."""

        try:
            self._write_runtime_checkpoint_locked()
        except Exception as error:
            self._last_error = (
                "Kill Switch 已生效，但 strategy runtime checkpoint 寫入失敗："
                f"{type(error).__name__}"
            )

    def _synchronize_kill_switch_locked(self) -> bool:
        """Reflect authoritative control state without manufacturing a transition."""

        control_state = str(self._kill_switch.status()["control_state"])
        if control_state == "DISENGAGED":
            return False
        self._stop.set()
        self._state = "KILLED"
        if control_state == "RECOVERY_REQUIRED":
            self._decision = "KILL_SWITCH_RECOVERY_REQUIRED"
            self._message = "Kill Switch Journal 需要復原；禁止產生新意圖"
        else:
            self._decision = "KILL_SWITCH_ENGAGED"
            self._message = "全域 Local Paper kill switch 已啟用；禁止產生新意圖"
        return True

    def _status_locked(self) -> dict[str, Any]:
        return {
            "mode": "LOCAL_PAPER_SIMULATION",
            "execution_authority": False,
            "state": self._state,
            "decision": self._decision,
            "message": self._message,
            "run_id": self._run_id,
            "started_at": _iso(self._started_at),
            "last_checked_at": _iso(self._last_checked_at),
            "last_action_at": _iso(self._last_action_at),
            "last_error": self._last_error,
            "last_intent": self._last_intent,
            "last_exit_reason": self._last_exit_reason,
            "entries_submitted": self._entries_submitted,
            "config": self._config.payload() if self._config else None,
            "pipeline": (
                {
                    **self._atomic_resolution.pipeline.to_dict(),
                    "snapshot_digest": self._atomic_resolution.pipeline.snapshot_digest,
                }
                if self._atomic_resolution is not None
                else None
            ),
            "effective_risk": (
                dict(self._effective_risk_evidence)
                if self._effective_risk_evidence is not None
                else None
            ),
            "restart_behavior": "MANUAL_START_REQUIRED",
            "kill_switch": self._kill_switch.status(),
            "notice": (
                "只會產生本機紙上模擬意圖；不具 Shioaji 或券商下單權限。"
            ),
        }


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 必須是數字") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} 必須是有限數字")
    return parsed


def _positive_decimal(value: object, field_name: str) -> Decimal:
    parsed = _decimal(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} 必須大於 0")
    return parsed


def _aware_datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field_name} 必須是 ISO datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} 必須包含 timezone")
    return parsed.astimezone(TAIPEI)


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} 必須是 object")
    return value


def _optional_mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _mapping_list(value: object, field_name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{field_name} 必須是 object list")
    return list(value)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
