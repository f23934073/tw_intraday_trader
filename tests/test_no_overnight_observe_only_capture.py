from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from threading import Event

import pytest

from config import twse_calendar_2026
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.no_overnight import NoOvernightMode
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from runtime.no_overnight import no_overnight_session_id
from runtime.no_overnight_evidence_capture import (
    capture_disabled_baseline,
    capture_observe_only,
)
from simulation.settings import LocalPaperSettings, LocalPaperSettingsState
from trading.journal import JournalCutoffExceededError, JournalRecord, JournalSession
from trading.local_paper import rebuild_local_paper_v2_projection
from trading.no_overnight_evidence import (
    NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA,
    NoOvernightEvidenceStage,
    NoOvernightEvidenceStatus,
    NoOvernightQualificationStatus,
    read_no_overnight_session_report,
)


CAMPAIGN_ID = "no-overnight-observe-only-test-v1"
CODE_IDENTITY = "a" * 40
DISABLED_DATE = date(2026, 8, 27)
OBSERVE_DATE = date(2026, 8, 28)
ACTIVE_SESSION_ID = "local-paper-active-observe-only-test"


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class AtomicCrossCutoffJournal(InMemoryJournalRepository):
    def __init__(self, clock: MutableClock) -> None:
        super().__init__()
        self.clock = clock
        self.cross_cutoff = False
        self.crossed_at = datetime.fromisoformat(
            "2026-08-28T09:00:00+08:00"
        )

    def start_session_and_append_before(self, *args, **kwargs):
        if self.cross_cutoff:
            self.clock.value = self.crossed_at
        return super().start_session_and_append_before(*args, **kwargs)


class AtomicReturnMovesClockJournal(InMemoryJournalRepository):
    def __init__(self, clock: MutableClock) -> None:
        super().__init__()
        self.clock = clock
        self.returned_at: datetime | None = None

    def start_session_and_append_before(self, *args, **kwargs):
        result = super().start_session_and_append_before(*args, **kwargs)
        if self.returned_at is not None:
            self.clock.value = self.returned_at
        return result


class UtcAtomicOpenJournal(InMemoryJournalRepository):
    def start_session_and_append_before(
        self,
        session,
        record,
        *,
        latest_allowed_at,
        authoritative_now=None,
    ):
        del authoritative_now
        return super().start_session_and_append_before(
            session,
            record,
            latest_allowed_at=latest_allowed_at,
            authoritative_now=lambda: record.occurred_at.astimezone(
                timezone.utc
            ),
        )


class SnapshotRaceJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.race_session_id: str | None = None
        self.race_triggered = False

    def records(self, session_id: str, *, after_sequence: int = 0):
        results = super().records(session_id, after_sequence=after_sequence)
        if (
            session_id == self.race_session_id
            and after_sequence == 0
            and not self.race_triggered
        ):
            self.race_triggered = True
            self.append(
                JournalRecord(
                    record_id="snapshot-race-backdated-cancel",
                    session_id=session_id,
                    kind="local_paper_cancel_command.v1",
                    occurred_at=datetime.fromisoformat(
                        "2026-08-27T09:30:00+08:00"
                    ),
                    payload={"unexpected": True},
                )
            )
        return results


class CloseRotationJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.on_observe_close = None

    def append(self, record):
        result = super().append(record)
        if (
            record.kind == "no_overnight_evidence_window_closed.v1"
            and record.session_id == _window_session_id()
            and self.on_observe_close is not None
        ):
            self.on_observe_close()
        return result


class UnsafeMockProviderSubclass(MockProvider):
    pass


def _settings_state(
    *,
    session_id: str = ACTIVE_SESSION_ID,
    revision: int = 7,
) -> LocalPaperSettingsState:
    settings = LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())
    return LocalPaperSettingsState(
        revision=revision,
        active=settings,
        draft=settings,
        active_session_id=session_id,
        active_settings_revision=revision,
        draft_settings_revision=revision,
    )


def _runtime_factory(journal: InMemoryJournalRepository):
    return lambda **values: RuntimeComposition.create(
        **values,
        journal=journal,
        start_simulation_streaming=False,
    )


def _seed_active_session(
    journal: InMemoryJournalRepository,
    state: LocalPaperSettingsState,
) -> None:
    composition = RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        clock=MutableClock(
            datetime.fromisoformat("2026-08-26T15:00:00+08:00")
        ),
        local_paper_settings=state.active,
        local_paper_settings_revision=state.active_settings_revision,
        local_paper_session_id=state.active_session_id,
        start_simulation_streaming=False,
    )
    composition.close()


def _capture_disabled_predecessor(
    root: Path,
    journal: InMemoryJournalRepository,
    state: LocalPaperSettingsState,
) -> object:
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def finish(_seconds: float) -> None:
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    return capture_disabled_baseline(
        campaign_id=CAMPAIGN_ID,
        session_date=DISABLED_DATE,
        code_identity=CODE_IDENTITY,
        artifact_root=root,
        marker_journal_factory=lambda: journal,
        provider=MockProvider(),
        clock=clock,
        runtime_factory=_runtime_factory(journal),
        active_settings_reader=lambda: state,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        wait=finish,
    )


def _campaign(
    tmp_path: Path,
    *,
    journal: InMemoryJournalRepository | None = None,
) -> tuple[Path, InMemoryJournalRepository, LocalPaperSettingsState, object]:
    root = tmp_path / "campaign"
    resolved_journal = journal or InMemoryJournalRepository()
    state = _settings_state()
    _seed_active_session(resolved_journal, state)
    predecessor = _capture_disabled_predecessor(root, resolved_journal, state)
    return root, resolved_journal, state, predecessor


def _observe_clock() -> MutableClock:
    return MutableClock(datetime.fromisoformat("2026-08-28T08:45:00+08:00"))


def _full_session_wait(clock: MutableClock):
    milestones = iter(
        (
            "2026-08-28T09:00:00+08:00",
            "2026-08-28T13:10:00+08:00",
            "2026-08-28T13:15:00+08:00",
            "2026-08-28T13:20:00+08:00",
            "2026-08-28T13:25:00+08:00",
            "2026-08-28T13:28:00+08:00",
            "2026-08-28T13:30:00+08:00",
        )
    )

    def wait(_seconds: float) -> None:
        clock.value = datetime.fromisoformat(next(milestones))

    return wait


def _capture_observe(
    *,
    root: Path,
    journal: InMemoryJournalRepository,
    state: LocalPaperSettingsState,
    clock: MutableClock | None = None,
    provider: MockProvider | None = None,
    active_settings_reader=None,
    runtime_factory=None,
    wait=None,
):
    resolved_clock = clock or _observe_clock()
    return capture_observe_only(
        campaign_id=CAMPAIGN_ID,
        session_date=OBSERVE_DATE,
        code_identity=CODE_IDENTITY,
        artifact_root=root,
        marker_journal_factory=lambda: journal,
        provider=provider or MockProvider(),
        clock=resolved_clock,
        runtime_factory=runtime_factory or _runtime_factory(journal),
        active_settings_reader=(
            active_settings_reader or (lambda: state)
        ),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        wait=wait or _full_session_wait(resolved_clock),
    )


def _window_session_id() -> str:
    return (
        f"no-overnight-evidence-v1:{CAMPAIGN_ID}:"
        f"OBSERVE_ONLY:{OBSERVE_DATE.isoformat()}"
    )


def test_observe_only_capture_uses_hard_mode_and_has_zero_local_paper_side_effects(
    tmp_path,
) -> None:
    root, journal, state, predecessor = _campaign(tmp_path)
    local_session = journal.session(state.active_session_id)
    assert local_session is not None
    before_projection = rebuild_local_paper_v2_projection(
        journal,
        session_id=state.active_session_id,
        starting_cash=state.active.starting_cash_twd,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        settings_digest=state.active.digest,
    )
    observed_modes: list[NoOvernightMode] = []
    observed_command_ports: list[object | None] = []

    def runtime_factory(**values):
        observed_modes.append(values["no_overnight_config"].mode)
        composition = RuntimeComposition.create(
            **values,
            journal=journal,
            start_simulation_streaming=False,
        )
        observed_command_ports.append(
            composition.no_overnight_controller._command_port
        )
        return composition

    report = _capture_observe(
        root=root,
        journal=journal,
        state=state,
        runtime_factory=runtime_factory,
    )

    path = root / "sessions" / "2026-08-28-observe-only.json"
    assert observed_modes == [NoOvernightMode.OBSERVE_ONLY]
    assert observed_command_ports == [None]
    assert report.schema_version == NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA
    assert report.observation.stage is NoOvernightEvidenceStage.OBSERVE_ONLY
    assert report.observation.campaign_id == predecessor.observation.campaign_id
    assert report.observation.code_identity == CODE_IDENTITY
    assert report.observation.local_paper_session_id == state.active_session_id
    assert report.status is NoOvernightEvidenceStatus.COMPLETE
    assert report.qualification is NoOvernightQualificationStatus.QUALIFIED
    assert report.terminal_state == "CONFIRMED_FLAT"
    assert report.result_status == "CURRENT"
    assert report.reconciliation_status == "MATCH"
    assert report.no_overnight_checkpoint_sequence == report.no_overnight_last_sequence
    assert report.local_paper_checkpoint_sequence == report.local_paper_last_sequence
    assert report.metrics.no_overnight_exit_attempt_count == 0
    assert report.metrics.no_overnight_exit_fill_count == 0
    assert report.metrics.synthetic_fill_count == 0
    assert report.metrics.duplicate_exit_side_effect_count == 0
    assert report.metrics.wrong_horizon_liquidation_count == 0
    after_projection = rebuild_local_paper_v2_projection(
        journal,
        session_id=state.active_session_id,
        starting_cash=state.active.starting_cash_twd,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        settings_digest=state.active.digest,
    )
    assert after_projection.cash == before_projection.cash
    assert after_projection.positions == before_projection.positions
    assert (
        after_projection.realized_pnl_by_exposure
        == before_projection.realized_pnl_by_exposure
    )
    assert after_projection.exposure_states == before_projection.exposure_states
    assert read_no_overnight_session_report(path) == report

    transitions = tuple(
        result.record.payload
        for result in journal.records(no_overnight_session_id(OBSERVE_DATE))
        if result.record.kind == "no_overnight_transition.v1"
    )
    would_actions = {
        action
        for transition in transitions
        for action in transition["would_actions"]
    }
    assert "WOULD_CANCEL_ENTRY" in would_actions
    assert "WOULD_EXIT" in would_actions
    assert "WOULD_RECONCILE" in would_actions
    assert not any(
        result.record.kind.startswith("order_")
        or result.record.kind.startswith("local_paper_cancel_")
        or result.record.kind.startswith("local_paper_fill.")
        for result in journal.records(state.active_session_id)
        if result.sequence > predecessor.local_paper_last_sequence
    )


def test_observe_only_normalizes_postgres_utc_open_time(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(
        tmp_path,
        journal=UtcAtomicOpenJournal(),
    )

    report = _capture_observe(root=root, journal=journal, state=state)

    assert report.observation.observed_from.isoformat() == (
        "2026-08-28T08:45:00+08:00"
    )
    opened = next(
        result
        for result in journal.records(_window_session_id())
        if result.record.kind == "no_overnight_evidence_window_opened.v1"
    )
    assert opened.record.occurred_at.isoformat() == (
        "2026-08-28T00:45:00+00:00"
    )


def test_observe_only_requires_one_complete_same_campaign_disabled_predecessor(
    tmp_path,
) -> None:
    root = tmp_path / "campaign"
    journal = InMemoryJournalRepository()
    state = _settings_state()
    _seed_active_session(journal, state)

    with pytest.raises(ValueError, match="DISABLED predecessor"):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.session(_window_session_id()) is None
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()

    predecessor = _capture_disabled_predecessor(root, journal, state)
    incomplete = replace(
        predecessor,
        status=NoOvernightEvidenceStatus.INCOMPLETE,
        reason_codes=("REVIEW_INCOMPLETE",),
    )
    path = root / "sessions" / "2026-08-27-disabled.json"
    path.write_text(
        json.dumps(
            incomplete.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="COMPLETE"):
        _capture_observe(root=root, journal=journal, state=state)


def test_observe_only_rejects_duplicate_disabled_predecessor(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    source = root / "sessions" / "2026-08-27-disabled.json"
    duplicate = root / "sessions" / "2026-08-26-disabled.json"
    duplicate.write_bytes(source.read_bytes())

    with pytest.raises(ValueError, match="exactly one.*DISABLED predecessor"):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.session(_window_session_id()) is None


def test_observe_only_rejects_predecessor_not_bound_to_current_journal(
    tmp_path,
) -> None:
    root, _source_journal, state, _predecessor = _campaign(tmp_path)
    unrelated_journal = InMemoryJournalRepository()
    _seed_active_session(unrelated_journal, state)

    with pytest.raises(ValueError, match="Journal window.*missing"):
        _capture_observe(
            root=root,
            journal=unrelated_journal,
            state=state,
        )

    assert unrelated_journal.session(_window_session_id()) is None


def test_observe_only_rejects_extra_incomplete_disabled_journal_window(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    journal.start_session(
        JournalSession(
            session_id=(
                f"no-overnight-evidence-v1:{CAMPAIGN_ID}:"
                "DISABLED_BASELINE:2026-08-26"
            ),
            started_at=datetime.fromisoformat("2026-08-26T08:45:00+08:00"),
            mode="NO_OVERNIGHT_EVIDENCE_WINDOW",
            metadata={"activation_authority": "NONE_EVIDENCE_ONLY"},
        )
    )

    with pytest.raises(ValueError, match="duplicate, or incomplete"):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.session(_window_session_id()) is None


def test_observe_only_rejects_disabled_policy_identity_drift(tmp_path) -> None:
    root, journal, state, predecessor = _campaign(tmp_path)
    changed = replace(
        predecessor,
        observation=replace(
            predecessor.observation,
            policy_version="forged-disabled-policy",
        ),
    )
    path = root / "sessions" / "2026-08-27-disabled.json"
    path.write_text(
        json.dumps(
            changed.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="policy/window identity"):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.session(_window_session_id()) is None


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("campaign_id", "wrong-campaign", "campaign"),
        ("code_identity", "b" * 40, "code"),
        ("calendar_digest", "b" * 64, "calendar"),
        ("expected_provider_identity", "unsafe.Provider", "provider"),
        ("local_paper_session_id", "wrong-session", "session"),
    ),
)
def test_observe_only_rejects_predecessor_identity_drift(
    tmp_path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    root, journal, state, predecessor = _campaign(tmp_path)
    changed_observation = replace(
        predecessor.observation,
        **{field: replacement},
    )
    changed = replace(
        predecessor,
        observation=changed_observation,
        local_paper_session_id=(
            replacement
            if field == "local_paper_session_id"
            else predecessor.local_paper_session_id
        ),
    )
    path = root / "sessions" / "2026-08-27-disabled.json"
    path.write_text(
        json.dumps(
            changed.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.session(_window_session_id()) is None


def test_observe_only_rejects_old_schema_and_tampered_predecessor(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    path = root / "sessions" / "2026-08-27-disabled.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = "no_overnight_session_evidence_v1"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        _capture_observe(root=root, journal=journal, state=state)
    assert journal.session(_window_session_id()) is None

    raw["schema_version"] = NO_OVERNIGHT_EVIDENCE_REPORT_SCHEMA
    raw["report_digest"] = "f" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        _capture_observe(root=root, journal=journal, state=state)


def test_observe_only_rejects_non_mock_provider_before_open(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)

    with pytest.raises(ValueError, match="exact MockProvider"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            provider=UnsafeMockProviderSubclass(),
        )

    assert journal.session(_window_session_id()) is None


@pytest.mark.parametrize(
    "started_at",
    (
        "2026-08-28T09:00:00+08:00",
        "2026-08-28T09:00:00.000001+08:00",
    ),
)
def test_observe_only_late_start_fails_before_journal_open(
    tmp_path,
    started_at: str,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    clock = MutableClock(datetime.fromisoformat(started_at))

    with pytest.raises(ValueError, match="strictly before open"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
        )

    assert journal.session(_window_session_id()) is None


@pytest.mark.parametrize(
    "crossed_at",
    (
        datetime.fromisoformat("2026-08-28T09:00:00+08:00"),
        datetime.fromisoformat("2026-08-28T09:00:00.000001+08:00"),
    ),
)
def test_observe_only_atomic_cross_cutoff_rolls_back(
    tmp_path,
    crossed_at: datetime,
) -> None:
    clock = _observe_clock()
    journal = AtomicCrossCutoffJournal(clock)
    root, journal, state, _predecessor = _campaign(tmp_path, journal=journal)
    journal.cross_cutoff = True
    journal.crossed_at = crossed_at

    with pytest.raises(JournalCutoffExceededError):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
        )

    assert journal.session(_window_session_id()) is None
    assert journal.records(_window_session_id()) == ()


@pytest.mark.parametrize(
    "returned_at",
    (
        datetime.fromisoformat("2026-08-28T09:00:00.000001+08:00"),
        datetime.fromisoformat("2026-08-28T08:44:59.999999+08:00"),
    ),
)
def test_observe_only_preserves_incomplete_open_after_post_atomic_clock_failure(
    tmp_path,
    returned_at: datetime,
) -> None:
    clock = _observe_clock()
    journal = AtomicReturnMovesClockJournal(clock)
    root, journal, state, _predecessor = _campaign(tmp_path, journal=journal)
    journal.returned_at = returned_at

    with pytest.raises(ValueError):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
        )

    records = journal.records(_window_session_id())
    assert journal.session(_window_session_id()) is not None
    assert len(records) == 1
    assert records[0].record.kind == "no_overnight_evidence_window_opened.v1"
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_clock_regression_during_runtime_composition(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    clock = _observe_clock()

    def regressing_runtime_factory(**values):
        composition = RuntimeComposition.create(
            **values,
            journal=journal,
            start_simulation_streaming=False,
        )
        clock.value = datetime.fromisoformat("2026-08-28T08:44:00+08:00")
        return composition

    with pytest.raises(ValueError, match="runtime composition"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
            runtime_factory=regressing_runtime_factory,
        )

    assert len(journal.records(_window_session_id())) == 1
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_restart_rejects_existing_open_only_marker(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    clock = _observe_clock()

    def fail_runtime(**_values):
        raise RuntimeError("simulated interrupted startup")

    with pytest.raises(RuntimeError, match="interrupted startup"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
            runtime_factory=fail_runtime,
        )
    assert len(journal.records(_window_session_id())) == 1

    clock.value = datetime.fromisoformat("2026-08-28T08:45:00+08:00")
    with pytest.raises(ValueError, match="incomplete.*already exists"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
        )
    assert len(journal.records(_window_session_id())) == 1
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_concurrent_duplicate_capture_leaves_one_durable_open(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    first_clock = _observe_clock()
    first_opened = Event()
    allow_first_runtime = Event()

    def blocking_runtime_factory(**values):
        first_opened.set()
        if not allow_first_runtime.wait(timeout=5):
            raise TimeoutError("duplicate capture did not reach durable open")
        return RuntimeComposition.create(
            **values,
            journal=journal,
            start_simulation_streaming=False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _capture_observe,
            root=root,
            journal=journal,
            state=state,
            clock=first_clock,
            runtime_factory=blocking_runtime_factory,
        )
        assert first_opened.wait(timeout=5)
        with pytest.raises(ValueError, match="incomplete.*already exists"):
            _capture_observe(
                root=root,
                journal=journal,
                state=state,
                clock=_observe_clock(),
            )
        assert len(journal.records(_window_session_id())) == 1
        allow_first_runtime.set()
        report = first.result(timeout=5)

    records = journal.records(_window_session_id())
    assert len(records) == 2
    assert report.status is NoOvernightEvidenceStatus.COMPLETE


def test_observe_only_rejects_existing_report_before_journal_open(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    path = root / "sessions" / "2026-08-28-observe-only.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="report already exists"):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.session(_window_session_id()) is None
    assert path.read_text(encoding="utf-8") == "{}"


def test_observe_only_rejects_active_settings_rotation_and_missing_session(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    rotated = replace(state, active_session_id="rotated-local-paper-session")
    calls = 0

    def active_settings_reader() -> LocalPaperSettingsState:
        nonlocal calls
        calls += 1
        return state if calls < 3 else rotated

    with pytest.raises(ValueError, match="active Local Paper settings changed"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            active_settings_reader=active_settings_reader,
        )
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()

    empty_journal = InMemoryJournalRepository()
    with pytest.raises(ValueError, match="active Local Paper Journal session"):
        _capture_observe(
            root=root,
            journal=empty_journal,
            state=state,
        )
    assert empty_journal.session(state.active_session_id) is None

def test_observe_only_rejects_transient_settings_rotation_during_wait(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    rotated = replace(
        state,
        revision=state.revision + 1,
        active_settings_revision=state.revision + 1,
        draft_settings_revision=state.revision + 1,
    )
    calls = 0

    def active_settings_reader() -> LocalPaperSettingsState:
        nonlocal calls
        calls += 1
        return rotated if calls == 4 else state

    with pytest.raises(ValueError, match="active Local Paper settings changed"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            active_settings_reader=active_settings_reader,
        )

    assert len(journal.records(_window_session_id())) == 1
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_settings_rotation_during_final_controller(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    rotated = replace(
        state,
        revision=state.revision + 1,
        active_settings_revision=state.active_settings_revision + 1,
        draft_settings_revision=state.draft_settings_revision + 1,
    )
    current_state = [state]

    def runtime_factory(**values):
        composition = RuntimeComposition.create(
            **values,
            journal=journal,
            start_simulation_streaming=False,
        )
        run_once = composition.no_overnight_controller.run_once

        def rotate_after_final(now: datetime):
            result = run_once(now)
            if now >= datetime.fromisoformat("2026-08-28T13:30:00+08:00"):
                current_state[0] = rotated
            return result

        composition.no_overnight_controller.run_once = rotate_after_final
        return composition

    with pytest.raises(ValueError, match="active Local Paper settings changed"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            runtime_factory=runtime_factory,
            active_settings_reader=lambda: current_state[0],
        )

    assert len(journal.records(_window_session_id())) == 1
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_settings_rotation_during_close_append(
    tmp_path,
) -> None:
    journal = CloseRotationJournal()
    root, journal, state, _predecessor = _campaign(tmp_path, journal=journal)
    rotated = replace(
        state,
        revision=state.revision + 1,
        active_settings_revision=state.active_settings_revision + 1,
        draft_settings_revision=state.draft_settings_revision + 1,
    )
    current_state = [state]
    journal.on_observe_close = lambda: current_state.__setitem__(0, rotated)

    with pytest.raises(ValueError, match="active Local Paper settings changed"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            active_settings_reader=lambda: current_state[0],
        )

    assert len(journal.records(_window_session_id())) == 2
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_active_settings_metadata_mismatch(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    mismatched_state = replace(
        state,
        revision=state.revision + 1,
        active_settings_revision=state.revision + 1,
        draft_settings_revision=state.revision + 1,
    )

    with pytest.raises(ValueError, match="session/settings identity mismatch"):
        _capture_observe(
            root=root,
            journal=journal,
            state=mismatched_state,
        )

    assert journal.session(_window_session_id()) is None


def test_observe_only_rejects_symlink_and_root_replacement(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    linked = tmp_path / "linked-campaign"
    linked.symlink_to(root, target_is_directory=True)

    with pytest.raises(ValueError, match="unsafe"):
        _capture_observe(root=linked, journal=journal, state=state)
    assert journal.session(_window_session_id()) is None

    displaced = tmp_path / "displaced-campaign"
    clock = _observe_clock()

    def replace_root(_seconds: float) -> None:
        root.rename(displaced)
        root.mkdir()
        (root / "sessions").mkdir()
        clock.value = datetime.fromisoformat("2026-08-28T13:30:00+08:00")

    with pytest.raises(ValueError, match="changed during capture"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
            wait=replace_root,
        )
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()
    assert not (
        displaced / "sessions" / "2026-08-28-observe-only.json"
    ).exists()


def test_observe_only_rejects_non_v4_fill_provenance(tmp_path) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    clock = _observe_clock()
    appended = False

    def append_legacy_fill(_seconds: float) -> None:
        nonlocal appended
        if not appended:
            appended = True
            journal.append(
                JournalRecord(
                    record_id="legacy-fill-provenance-test",
                    session_id=state.active_session_id,
                    kind="local_paper_fill.v3",
                    occurred_at=datetime.fromisoformat(
                        "2026-08-28T09:30:00+08:00"
                    ),
                    payload={"legacy": True},
                )
            )
        clock.value = datetime.fromisoformat("2026-08-28T13:30:00+08:00")

    with pytest.raises(ValueError, match="local_paper_fill.v4 provenance"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
            wait=append_legacy_fill,
        )
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_any_order_side_effect_and_preserves_open(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    clock = _observe_clock()

    def append_order(_seconds: float) -> None:
        journal.append(
            JournalRecord(
                record_id="unexpected-observe-cancel",
                session_id=state.active_session_id,
                kind="local_paper_cancel_command.v1",
                occurred_at=datetime.fromisoformat(
                    "2026-08-28T09:30:00+08:00"
                ),
                payload={"unexpected": True},
            )
        )
        clock.value = datetime.fromisoformat("2026-08-28T13:30:00+08:00")

    with pytest.raises(ValueError, match="order/cancel/fill side effects"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
            wait=append_order,
        )

    assert len(journal.records(_window_session_id())) == 1
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_backdated_side_effect_by_durable_sequence(
    tmp_path,
) -> None:
    root, journal, state, _predecessor = _campaign(tmp_path)
    clock = _observe_clock()

    def append_backdated_cancel(_seconds: float) -> None:
        journal.append(
            JournalRecord(
                record_id="unexpected-backdated-observe-cancel",
                session_id=state.active_session_id,
                kind="local_paper_cancel_command.v1",
                occurred_at=datetime.fromisoformat(
                    "2026-08-27T09:30:00+08:00"
                ),
                payload={"unexpected": True},
            )
        )
        clock.value = datetime.fromisoformat("2026-08-28T13:30:00+08:00")

    with pytest.raises(ValueError, match="order/cancel/fill side effects"):
        _capture_observe(
            root=root,
            journal=journal,
            state=state,
            clock=clock,
            wait=append_backdated_cancel,
        )

    assert len(journal.records(_window_session_id())) == 1
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()


def test_observe_only_rejects_side_effect_racing_baseline_snapshot(
    tmp_path,
) -> None:
    journal = SnapshotRaceJournal()
    root, journal, state, _predecessor = _campaign(tmp_path, journal=journal)
    journal.race_session_id = state.active_session_id

    with pytest.raises(ValueError, match="order/cancel/fill side effects"):
        _capture_observe(root=root, journal=journal, state=state)

    assert journal.race_triggered is True
    assert journal.session(_window_session_id()) is None
    assert not (root / "sessions" / "2026-08-28-observe-only.json").exists()
