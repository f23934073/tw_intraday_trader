from __future__ import annotations

from datetime import date, datetime, timedelta
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pytest

from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
)
from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.no_overnight import (
    LocalPaperNoOvernightCommandPort,
    LocalPaperNoOvernightEvidenceReader,
    NoOvernightEnforcementAction,
)
from simulation.settings import LocalPaperSettings
from trading.exposure import ExposureIdentity, HoldingHorizon
from trading.no_overnight import FlatProofMode, NoOvernightState, strict_flat_proof


TAIPEI = ZoneInfo("Asia/Taipei")
AT = datetime(2026, 8, 24, 13, 21, tzinfo=TAIPEI)
ACTIVE_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v1"


def _settings_v2() -> LocalPaperSettings:
    return LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())


class _Clock:
    def __init__(self, value: datetime = AT) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class _StreamingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.handler = None

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self.handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        return None

    def emit(
        self,
        *,
        at: datetime,
        bid: float = 105.5,
        ask: float = 105.5,
        bid_lots: int = 5,
        ask_lots: int = 5,
    ) -> None:
        assert self.handler is not None
        self.handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=at,
                received_at=at,
                bid_price=bid,
                ask_price=ask,
                bid_volume_lots=bid_lots,
                ask_volume_lots=ask_lots,
                suspended=False,
            )
        )


def _wait_until(predicate) -> None:
    deadline = monotonic() + 1.0
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("simulation did not reach expected state")


def _identity(
    exposure_id: str,
    *,
    horizon: HoldingHorizon = HoldingHorizon.INTRADAY,
) -> ExposureIdentity:
    return ExposureIdentity(
        exposure_id=exposure_id,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        owner_origin="STRATEGY_AUTOMATED",
        owner_id="strategy-owner",
        holding_horizon=horizon,
        entry_session_date=AT.date(),
        entry_policy_version="entry-v1",
        entry_policy_digest="e" * 64,
    )


def _exposure(
    exposure_id: str,
    *,
    quantity: int = 1_000,
    horizon: HoldingHorizon = HoldingHorizon.INTRADAY,
) -> dict[str, object]:
    identity = _identity(exposure_id, horizon=horizon)
    return {
        "symbol": "3231",
        "quantity": quantity,
        "bid_price": 105.4,
        "book_received_at": AT.isoformat(),
        "owner_strategy_version": "strategy-v1",
        "exposure_identity": identity.to_payload(),
    }


class _Simulation:
    max_book_age_seconds = 15

    def __init__(self) -> None:
        self.exposure_rows: list[dict[str, object]] = []
        self.order_rows: list[dict[str, object]] = []
        self.context = {
            "instrument_tradable": True,
            "executable_book_ready": True,
            "data_health_state": "HEALTHY",
            "book_age_seconds": 0.0,
            "executable_price": "105.4",
        }

    def exposures(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.exposure_rows]

    def orders(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.order_rows]

    def execution_admission_context(
        self,
        symbol: str,
        side: str,
        *,
        max_book_age_seconds: int,
    ) -> dict[str, object]:
        assert symbol == "3231"
        assert side == "SELL"
        assert max_book_age_seconds == self.max_book_age_seconds
        return dict(self.context)


class _Commands:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []
        self.cancellations: list[tuple[str, str]] = []
        self.retries: list[tuple[str, str, object]] = []
        self.recorded_attempts: set[str] = set()

    def has_recorded_order_attempt(self, idempotency_key: str) -> bool:
        return idempotency_key in self.recorded_attempts

    def submit_no_overnight_exit(self, **payload):
        self.submissions.append(dict(payload))
        self.recorded_attempts.add(str(payload["idempotency_key"]))
        return ({"order_id": "exit-1", "status": "SUBMITTED"}, False)

    def cancel_order(self, order_id: str, idempotency_key: str):
        self.cancellations.append((order_id, idempotency_key))
        return ({"order_id": order_id, "status": "CANCELLED"}, False)

    def retry_order(self, order_id: str, idempotency_key: str, *, limit_price):
        self.retries.append((order_id, idempotency_key, limit_price))
        self.recorded_attempts.add(idempotency_key)
        return ({"order_id": "exit-2", "status": "SUBMITTED"}, False)


def _action(
    kind: str,
    *,
    state: NoOvernightState,
    requested_at: datetime = AT,
) -> NoOvernightEnforcementAction:
    return NoOvernightEnforcementAction(
        kind=kind,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        session_date=AT.date(),
        state=state,
        state_revision=3,
        requested_at=requested_at,
    )


def _port(
    simulation: _Simulation,
    commands: _Commands,
) -> LocalPaperNoOvernightCommandPort:
    return LocalPaperNoOvernightCommandPort(
        commands=commands,
        simulation=simulation,
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
    )


def _exit_order(
    exposure_id: str,
    *,
    status: str,
    attempt: int = 1,
    remaining: int = 1_000,
    updated_at: datetime = AT,
) -> dict[str, object]:
    return {
        "order_id": f"exit-{attempt}",
        "side": "SELL",
        "status": status,
        "attempt": attempt,
        "remaining_quantity": remaining,
        "updated_at": updated_at.isoformat(),
        "target_exposure_id": exposure_id,
        "exposure_identity": _identity(exposure_id).to_payload(),
        "execution_reason_code": "NO_OVERNIGHT_EXIT",
    }


def test_flatten_submits_one_exact_managed_exposure_and_preserves_long() -> None:
    simulation = _Simulation()
    simulation.exposure_rows = [
        _exposure("intraday"),
        _exposure("long", horizon=HoldingHorizon.LONG_TERM),
    ]
    commands = _Commands()
    action = _action(
        "FLATTEN_MANAGED_EXPOSURES",
        state=NoOvernightState.FLATTENING,
    )

    assert _port(simulation, commands).execute(action) is True
    assert len(commands.submissions) == 1
    submission = commands.submissions[0]
    assert submission["symbol"] == "3231"
    assert submission["quantity_shares"] == 1_000
    assert submission["limit_price"] == "105.4"
    assert submission["exposure"].exposure_id == "intraday"
    assert "long" not in str(commands.submissions)
    assert _port(simulation, commands).execute(action) is False
    assert len(commands.submissions) == 1


def test_duplicate_flatten_waits_for_active_exit_and_stale_book_fails_closed() -> None:
    simulation = _Simulation()
    simulation.exposure_rows = [_exposure("intraday")]
    simulation.order_rows = [_exit_order("intraday", status="PARTIALLY_FILLED")]
    commands = _Commands()

    assert (
        _port(simulation, commands).execute(
            _action(
                "FLATTEN_MANAGED_EXPOSURES",
                state=NoOvernightState.FLATTENING,
            )
        )
        is False
    )
    assert commands.submissions == []

    simulation.order_rows = []
    simulation.context["executable_book_ready"] = False
    simulation.context["executable_price"] = None
    assert (
        _port(simulation, commands).execute(
            _action(
                "FLATTEN_MANAGED_EXPOSURES",
                state=NoOvernightState.FLATTENING,
            )
        )
        is False
    )
    assert commands.submissions == []


def test_aggressive_exit_cancels_stale_active_before_any_successor() -> None:
    simulation = _Simulation()
    simulation.exposure_rows = [_exposure("intraday")]
    simulation.order_rows = [
        _exit_order(
            "intraday",
            status="PARTIALLY_FILLED",
            updated_at=AT - timedelta(seconds=10),
        )
    ]
    commands = _Commands()

    assert (
        _port(simulation, commands).execute(
            _action(
                "AGGRESSIVE_EXIT_MANAGED_EXPOSURES",
                state=NoOvernightState.AGGRESSIVE_EXIT,
            )
        )
        is True
    )
    assert len(commands.cancellations) == 1
    assert commands.retries == []
    assert commands.submissions == []


def test_aggressive_successor_requires_terminal_exact_remainder_and_bound() -> None:
    simulation = _Simulation()
    simulation.exposure_rows = [_exposure("intraday")]
    simulation.order_rows = [
        _exit_order("intraday", status="CANCELLED", remaining=1_000)
    ]
    commands = _Commands()
    action = _action(
        "AGGRESSIVE_EXIT_MANAGED_EXPOSURES",
        state=NoOvernightState.AGGRESSIVE_EXIT,
    )

    assert _port(simulation, commands).execute(action) is True
    assert len(commands.retries) == 1
    assert commands.retries[0][0] == "exit-1"
    assert commands.retries[0][2] == "105.4"

    commands.retries.clear()
    simulation.order_rows = [
        _exit_order("intraday", status="CANCELLED", remaining=500)
    ]
    assert _port(simulation, commands).execute(action) is False
    assert commands.retries == []

    simulation.order_rows = [
        _exit_order("intraday", status="CANCELLED", attempt=3)
    ]
    assert _port(simulation, commands).execute(action) is False
    assert commands.retries == []


def test_rejected_or_recovery_required_exit_never_creates_successor() -> None:
    for status in ("REJECTED", "RECOVERY_REQUIRED", "SUBMIT_UNKNOWN"):
        simulation = _Simulation()
        simulation.exposure_rows = [_exposure("intraday")]
        simulation.order_rows = [_exit_order("intraday", status=status)]
        commands = _Commands()

        assert (
            _port(simulation, commands).execute(
                _action(
                    "AGGRESSIVE_EXIT_MANAGED_EXPOSURES",
                    state=NoOvernightState.AGGRESSIVE_EXIT,
                )
            )
            is False
        )
        assert commands.submissions == []
        assert commands.retries == []
        assert commands.cancellations == []


def test_local_paper_flatten_closes_only_intraday_same_symbol_exposure() -> None:
    clock = _Clock()
    provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        provider,
        clock=clock,
        local_paper_settings=_settings_v2(),
    )
    simulation = composition.simulation_service
    simulation.watch_quote(owner_id="flatten-test", symbol="3231")
    provider.emit(at=clock.now())
    _wait_until(
        lambda: simulation.execution_admission_context(
            "3231",
            "BUY",
            max_book_age_seconds=simulation.max_book_age_seconds,
        )["executable_book_ready"]
        is True
    )
    composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="long-entry",
        holding_horizon="LONG_TERM",
    )
    composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="intraday-entry",
        holding_horizon="INTRADAY",
    )
    exposures = simulation.exposures()
    assert len(exposures) == 2
    intraday_id = next(
        str(item["exposure_id"])
        for item in exposures
        if item["holding_horizon"] == "INTRADAY"
    )

    port = LocalPaperNoOvernightCommandPort(
        commands=composition.local_paper_commands,
        simulation=simulation,
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
    )
    assert port.execute(
        _action(
            "FLATTEN_MANAGED_EXPOSURES",
            state=NoOvernightState.FLATTENING,
        )
    )

    remaining = simulation.exposures()
    assert len(remaining) == 1
    assert remaining[0]["holding_horizon"] == "LONG_TERM"
    assert remaining[0]["quantity"] == 1_000
    exit_order = next(item for item in simulation.orders() if item["side"] == "SELL")
    assert exit_order["target_exposure_id"] == intraday_id
    assert exit_order["execution_reason_code"] == "NO_OVERNIGHT_EXIT"
    assert exit_order["status"] == "FILLED"
    evidence = LocalPaperNoOvernightEvidenceReader(
        journal=composition.journal,
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
        simulation=simulation,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    ).read(now=clock.now(), session_date=clock.session_date())
    assert strict_flat_proof(evidence.evidence) is FlatProofMode.FILL_DERIVED_CLOSE

    class _MismatchedOrderProjection:
        def exposures(self):
            return simulation.exposures()

        def orders(self):
            rows = simulation.orders()
            for row in rows:
                if row["side"] == "SELL":
                    row["status"] = "CANCELLED"
            return rows

        def no_overnight_reconciliation_context(self):
            return simulation.no_overnight_reconciliation_context()

    with pytest.raises(ValueError, match="order Journal/simulator state mismatch"):
        LocalPaperNoOvernightEvidenceReader(
            journal=composition.journal,
            local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
            simulation=_MismatchedOrderProjection(),
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        ).read(now=clock.now(), session_date=clock.session_date())

    class _MismatchedAccountingProjection:
        def exposures(self):
            return simulation.exposures()

        def orders(self):
            return simulation.orders()

        def no_overnight_reconciliation_context(self):
            context = simulation.no_overnight_reconciliation_context()
            context["cash"] = "0"
            return context

    with pytest.raises(ValueError, match="accounting Journal/simulator mismatch"):
        LocalPaperNoOvernightEvidenceReader(
            journal=composition.journal,
            local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
            simulation=_MismatchedAccountingProjection(),
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        ).read(now=clock.now(), session_date=clock.session_date())
    composition.close()


def test_local_paper_aggressive_exit_waits_for_cancel_then_retries_once() -> None:
    clock = _Clock()
    provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        provider,
        clock=clock,
        local_paper_settings=_settings_v2(),
    )
    simulation = composition.simulation_service
    simulation.watch_quote(owner_id="aggressive-test", symbol="3231")
    provider.emit(at=clock.now(), bid_lots=0, ask_lots=2)
    _wait_until(
        lambda: simulation.execution_admission_context(
            "3231",
            "BUY",
            max_book_age_seconds=simulation.max_book_age_seconds,
        )["executable_book_ready"]
        is True
    )
    composition.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="aggressive-entry",
        holding_horizon="INTRADAY",
    )
    port = LocalPaperNoOvernightCommandPort(
        commands=composition.local_paper_commands,
        simulation=simulation,
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
    )
    assert port.execute(
        _action(
            "FLATTEN_MANAGED_EXPOSURES",
            state=NoOvernightState.FLATTENING,
        )
    )
    first_exit = next(item for item in simulation.orders() if item["side"] == "SELL")
    assert first_exit["status"] in {"SUBMITTED", "PENDING"}

    clock.value += timedelta(seconds=10)
    assert port.execute(
        _action(
            "AGGRESSIVE_EXIT_MANAGED_EXPOSURES",
            state=NoOvernightState.AGGRESSIVE_EXIT,
            requested_at=clock.now(),
        )
    )
    cancelled = next(
        item for item in simulation.orders() if item["order_id"] == first_exit["order_id"]
    )
    assert cancelled["status"] == "CANCELLED"
    assert len([item for item in simulation.orders() if item["side"] == "SELL"]) == 1

    journal = composition.journal
    composition.close()
    retry_provider = _StreamingProvider()
    composition = RuntimeComposition.create(
        retry_provider,
        clock=clock,
        journal=journal,
        local_paper_settings=_settings_v2(),
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
    )
    simulation = composition.simulation_service
    port = LocalPaperNoOvernightCommandPort(
        commands=composition.local_paper_commands,
        simulation=simulation,
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
    )
    assert next(
        item for item in simulation.orders() if item["order_id"] == first_exit["order_id"]
    )["status"] == "CANCELLED"

    retry_provider.emit(at=clock.now(), bid_lots=1, ask_lots=2)
    _wait_until(
        lambda: simulation.execution_admission_context(
            "3231",
            "SELL",
            max_book_age_seconds=simulation.max_book_age_seconds,
        )["executable_book_ready"]
        is True
    )
    assert port.execute(
        _action(
            "AGGRESSIVE_EXIT_MANAGED_EXPOSURES",
            state=NoOvernightState.AGGRESSIVE_EXIT,
            requested_at=clock.now(),
        )
    )
    exits = sorted(
        (item for item in simulation.orders() if item["side"] == "SELL"),
        key=lambda item: item["attempt"],
    )
    assert [item["attempt"] for item in exits] == [1, 2]
    assert exits[1]["predecessor_order_id"] == exits[0]["order_id"]
    assert exits[1]["status"] == "FILLED"
    assert simulation.exposures() == []
    composition.close()

    final = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
        local_paper_settings=_settings_v2(),
        local_paper_session_id=ACTIVE_LOCAL_PAPER_SESSION_ID,
    )
    final_exits = sorted(
        (item for item in final.simulation_service.orders() if item["side"] == "SELL"),
        key=lambda item: item["attempt"],
    )
    assert [item["status"] for item in final_exits] == ["CANCELLED", "FILLED"]
    assert final_exits[1]["predecessor_order_id"] == final_exits[0]["order_id"]
    assert final.simulation_service.exposures() == []
    final.close()
