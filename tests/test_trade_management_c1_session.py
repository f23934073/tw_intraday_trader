from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from threading import Thread
from time import sleep
from zoneinfo import ZoneInfo

import pytest

from market_data.events import InstrumentReference
from market_data.momentum_stream import (
    QualificationBootstrapEvidence,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from market_data.qualification_capture import (
    HistoricalQualificationCapture,
    QualificationCaptureConfig,
)
from runtime.trade_management_c1_session import (
    C1SessionStatus,
    TradeManagementC1SessionCoordinator,
)
from runtime.trade_management_live_capture import (
    LiveShadowCaptureConfig,
    LiveShadowProviderIdentity,
)
from tests.test_live_entry_thesis_draft import decision, policy
from tests.test_qualification_capture import _book_envelope
from tests.test_trade_management_operational_composition import (
    existing_fill_journal,
    shadow_policy,
)
from tests.test_trade_management_replay import SNAPSHOT
from tests.test_trade_management_shadow_operation import live_events
from trading.journal import InMemoryJournalRepository, JournalSession
from trading.live_entry_thesis_draft import LiveTradeThesisDraftBuilder
from trading.shadow_evidence_journal import ShadowEvidenceJournalKind
from scripts import run_trade_management_shadow_c1 as c1_cli


TAIPEI = ZoneInfo("Asia/Taipei")
MARKET_DATE = date(2026, 8, 20)
PROVIDER = LiveShadowProviderIdentity(
    provider="test-provider",
    sdk_version="1",
    simulation=True,
    connection_session_id="c1-test-connection",
)


class SessionClock:
    def __init__(self) -> None:
        self.value = datetime.combine(MARKET_DATE, time(9), tzinfo=TAIPEI)

    def now(self):
        return self.value

    def session_date(self):
        return self.value.date()


class FullSessionStream:
    environment_identity = PROVIDER.environment_identity
    callback_errors = ()

    def __init__(self, clock: SessionClock) -> None:
        self.clock = clock
        self.market_handler = None
        self.lifecycle_handler = None
        self.thread: Thread | None = None

    def qualification_bootstrap_evidence(
        self,
        symbol: str,
        session_date: date,
        prior_session_date: date,
    ) -> QualificationBootstrapEvidence:
        reference = InstrumentReference(
            symbol=symbol,
            exchange="TWSE",
            session_date=session_date,
            reference_price=Decimal("590"),
            limit_up_price=Decimal("649"),
            limit_down_price=Decimal("531"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=session_date,
        )
        return QualificationBootstrapEvidence(
            reference=reference,
            instrument_name="台積電",
            security_type="STOCK",
            instrument_source_identity="TSE:2330",
            captured_at=self.clock.now(),
            received_at=self.clock.now(),
            prior_session_date=prior_session_date,
            previous_close=Decimal("590"),
            previous_session_volume_lots=10000,
            snapshot_source_identity="test-snapshot:TSE:2330",
        )

    def start(self, event_handler, lifecycle_handler) -> None:
        self.market_handler = event_handler
        self.lifecycle_handler = lifecycle_handler

    def request_subscribe(self, symbol: str) -> None:
        self.lifecycle_handler(
            StreamLifecycleEvent(
                event_type=StreamLifecycleEventType.SUBSCRIBE_ACKED,
                occurred_at=self.clock.now(),
                reason="paired_tick_bidask_ack",
                symbol=symbol,
            )
        )
        self.thread = Thread(target=self._emit, daemon=True)
        self.thread.start()

    def _emit(self) -> None:
        sleep(0.05)
        book = _book_envelope()
        self.market_handler(
            replace(
                book,
                session_id=decision().session_id,
                payload=replace(
                    book.payload,
                    bid_prices=(Decimal("599"),),
                    ask_prices=(Decimal("600"),),
                ),
            )
        )
        for event in live_events():
            self.market_handler(event)
        self.clock.value = datetime.combine(
            MARKET_DATE,
            time(13, 30),
            tzinfo=TAIPEI,
        )

    def close(self) -> None:
        if self.thread is not None:
            self.thread.join(timeout=2)


def capture_config() -> LiveShadowCaptureConfig:
    return LiveShadowCaptureConfig(
        session_id=decision().session_id,
        symbol=decision().symbol,
        provider=PROVIDER,
        scheduled_open=datetime.combine(MARKET_DATE, time(9), tzinfo=TAIPEI),
        scheduled_close=datetime.combine(
            MARKET_DATE,
            time(13, 30),
            tzinfo=TAIPEI,
        ),
    )


def empty_fill_journal() -> InMemoryJournalRepository:
    draft = LiveTradeThesisDraftBuilder().build(decision(), policy())
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=draft.session_id,
            started_at=draft.signal_at.value,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    return journal


def run_session(
    tmp_path: Path,
    *,
    fill_journal: InMemoryJournalRepository,
    evidence_journal: InMemoryJournalRepository | None = None,
):
    clock = SessionClock()
    evidence_journal = evidence_journal or InMemoryJournalRepository()
    coordinator = TradeManagementC1SessionCoordinator(
        decision=decision(),
        draft_policy=policy(),
        fill_journal=fill_journal,
        evidence_journal=evidence_journal,
        shadow_policy=shadow_policy(),
        risk_snapshot_provider=lambda _event, _result: SNAPSHOT,
        capture_config=capture_config(),
        clock=clock,
        journal_recovery_timeout_seconds=0.05,
        journal_recovery_retry_seconds=0.005,
    )
    capture = HistoricalQualificationCapture(
        FullSessionStream(clock),
        QualificationCaptureConfig(
            symbol=decision().symbol,
            session_id=decision().session_id,
            records_root=tmp_path / "records",
            duration_seconds=1,
        ),
        prior_session_date=date(2026, 8, 19),
        calendar_version="reviewed-calendar-v1",
        clock=clock,
        process_observer=coordinator,
    )
    return coordinator.run(capture), evidence_journal


class FailDecisionJournal(InMemoryJournalRepository):
    def append(self, record):
        if record.kind == ShadowEvidenceJournalKind.DECISION_RECORDED.value:
            raise OSError("shadow postgres unavailable")
        return super().append(record)


class FailOnceDecisionJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def append(self, record):
        if (
            record.kind == ShadowEvidenceJournalKind.DECISION_RECORDED.value
            and not self.failed
        ):
            self.failed = True
            raise OSError("shadow postgres temporarily unavailable")
        return super().append(record)


class FailOnceFinalizationJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def append(self, record):
        if (
            record.kind == ShadowEvidenceJournalKind.SESSION_FINALIZED.value
            and not self.failed
        ):
            self.failed = True
            raise OSError("shadow finalization temporarily unavailable")
        return super().append(record)


def test_full_session_without_existing_fill_is_insufficient_not_blocked(tmp_path) -> None:
    evidence, journal = run_session(
        tmp_path,
        fill_journal=empty_fill_journal(),
    )

    assert evidence.status is C1SessionStatus.INSUFFICIENT_EVIDENCE
    assert evidence.full_market_session_covered
    assert evidence.market_exact_replay_passed
    assert evidence.market_journal_sha256 is not None
    assert evidence.activation_id is None
    assert evidence.decision_count == 0
    assert journal.records(decision().session_id) == ()
    assert evidence.production_shadow_gate == "NOT_PASSED"


def test_c1_readiness_digest_is_path_independent_and_deterministic(tmp_path) -> None:
    first, _ = run_session(
        tmp_path / "first",
        fill_journal=empty_fill_journal(),
    )
    second, _ = run_session(
        tmp_path / "second",
        fill_journal=empty_fill_journal(),
    )

    assert first.market_session_dir != second.market_session_dir
    assert first.digest == second.digest


def test_existing_fill_activates_post_fill_shadow_and_recovers_exactly(tmp_path) -> None:
    _, _, fill_journal = existing_fill_journal()

    evidence, journal = run_session(tmp_path, fill_journal=fill_journal)

    assert evidence.status is C1SessionStatus.FINALIZED
    assert evidence.activation_id is not None
    assert evidence.decision_count == len(live_events())
    assert evidence.journal_record_count == len(live_events()) + 1
    assert evidence.parity_status.value == "MATCHED"
    assert evidence.recovery_verified
    assert evidence.recovery_digest is not None
    assert len(journal.records(decision().session_id)) == len(live_events()) + 1
    assert not evidence.execution_authority
    assert not evidence.execution_enabled


def test_journal_failure_stops_capture_before_later_shadow_event(tmp_path) -> None:
    _, _, fill_journal = existing_fill_journal()
    evidence_journal = FailDecisionJournal()

    evidence, _ = run_session(
        tmp_path,
        fill_journal=fill_journal,
        evidence_journal=evidence_journal,
    )

    assert evidence.status is C1SessionStatus.BLOCKED
    assert evidence.decision_count == 1
    assert evidence.pending_evidence_count == 1
    assert evidence.writer_failure_count > 0
    assert evidence.writer_recovery_count == 0
    assert evidence_journal.records(decision().session_id) == ()
    assert any("PROCESS_OBSERVER_FAILED" in reason for reason in evidence.reasons)


def test_transient_journal_failure_recovers_before_next_shadow_event(tmp_path) -> None:
    _, _, fill_journal = existing_fill_journal()

    evidence, _ = run_session(
        tmp_path,
        fill_journal=fill_journal,
        evidence_journal=FailOnceDecisionJournal(),
    )

    assert evidence.status is C1SessionStatus.FINALIZED
    assert evidence.pending_evidence_count == 0
    assert evidence.writer_failure_count == 1
    assert evidence.writer_recovery_count == 1
    assert evidence.writer_recovery_seconds is not None


def test_transient_finalization_failure_retries_same_evidence(tmp_path) -> None:
    _, _, fill_journal = existing_fill_journal()

    evidence, _ = run_session(
        tmp_path,
        fill_journal=fill_journal,
        evidence_journal=FailOnceFinalizationJournal(),
    )

    assert evidence.status is C1SessionStatus.FINALIZED
    assert evidence.writer_failure_count == 1
    assert evidence.writer_recovery_count == 1
    assert evidence.recovery_verified


def test_cli_fails_before_provider_when_sealed_inputs_are_missing(
    monkeypatch,
    tmp_path,
) -> None:
    connected = False

    def forbidden_connect(**_kwargs):
        nonlocal connected
        connected = True
        raise AssertionError("provider must not be reached")

    monkeypatch.setattr(
        c1_cli.ShioajiMomentumStream,
        "connect_from_env",
        forbidden_connect,
    )

    result = c1_cli.main(
        [
            "--preflight-artifact",
            str(tmp_path / "missing-c0.json"),
            "--entry-decision",
            str(tmp_path / "missing-decision.json"),
            "--thesis-draft",
            str(tmp_path / "missing-draft.json"),
            "--shadow-policy",
            str(tmp_path / "missing-policy.json"),
            "--risk-snapshot",
            str(tmp_path / "missing-risk.json"),
            "--connection-session-id",
            "c1-test",
            "--output",
            str(tmp_path / "out.json"),
        ]
    )

    assert result == 2
    assert connected is False


def test_c1_requires_explicit_separate_local_paper_and_shadow_dsns(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LOCAL_PAPER_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://shared")
    monkeypatch.setenv(
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL",
        "postgresql://shadow",
    )
    with pytest.raises(RuntimeError, match="LOCAL_PAPER_AND_SHADOW_DSNS_ARE_REQUIRED"):
        c1_cli._journal_dsns()

    monkeypatch.setenv("LOCAL_PAPER_DATABASE_URL", "postgresql://same")
    monkeypatch.setenv("TRADE_MANAGEMENT_SHADOW_DATABASE_URL", "postgresql://same")
    with pytest.raises(RuntimeError, match="SHADOW_DSN_MUST_BE_DEDICATED"):
        c1_cli._journal_dsns()

    monkeypatch.setenv("LOCAL_PAPER_DATABASE_URL", "postgresql://paper")
    monkeypatch.setenv(
        "TRADE_MANAGEMENT_SHADOW_DATABASE_URL",
        "postgresql://shadow",
    )
    assert c1_cli._journal_dsns() == (
        "postgresql://paper",
        "postgresql://shadow",
    )


def test_c1_runtime_and_cli_have_no_execution_capability() -> None:
    root = Path(__file__).parents[1]
    imported: set[str] = set()
    referenced: set[str] = set()
    for relative in (
        "runtime/trade_management_c1_session.py",
        "scripts/run_trade_management_shadow_c1.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        )
        referenced.update(
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        )

    assert imported.isdisjoint(
        {
            "OrderCommand",
            "OrderApplicationService",
            "LocalPaperCommandService",
            "SimulationService",
        }
    )
    assert referenced.isdisjoint(
        {"Broker", "Position", "SELL", "place_order", "activate_ca"}
    )
