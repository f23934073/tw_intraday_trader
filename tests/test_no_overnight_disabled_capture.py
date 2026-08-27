from __future__ import annotations

from datetime import date, datetime, timezone
import os

import pytest

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from runtime.no_overnight_evidence_capture import capture_disabled_baseline
from scripts import capture_no_overnight_disabled_baseline as capture_script
from trading.no_overnight_evidence import (
    NoOvernightEvidenceStatus,
    NoOvernightQualificationStatus,
    read_no_overnight_session_report,
)
from trading.journal import (
    JournalCutoffExceededError,
    JournalSession,
)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class ClosingMockProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class StartSessionCrossesOpenJournal(InMemoryJournalRepository):
    def __init__(self, clock: MutableClock) -> None:
        super().__init__()
        self.clock = clock
        self.append_called = False

    def start_session(self, session: JournalSession) -> None:
        self.clock.value = datetime.fromisoformat(
            "2026-08-27T09:00:00.000001+08:00"
        )
        super().start_session(session)

    def append(self, record):
        self.append_called = True
        return super().append(record)


class AtomicReturnMovesClockJournal(InMemoryJournalRepository):
    def __init__(self, clock: MutableClock, returned_at: datetime) -> None:
        super().__init__()
        self.clock = clock
        self.returned_at = returned_at

    def start_session_and_append_before(self, *args, **kwargs):
        result = super().start_session_and_append_before(*args, **kwargs)
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


def test_capture_disabled_baseline_uses_real_append_order(tmp_path) -> None:
    journal = InMemoryJournalRepository()
    provider = MockProvider()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def wait_until_close(_seconds: float) -> None:
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    report = capture_disabled_baseline(
        campaign_id="no-overnight-campaign-2026-08-operational-v1",
        session_date=date(2026, 8, 27),
        code_identity="a" * 40,
        artifact_root=tmp_path,
        marker_journal_factory=lambda: journal,
        provider=provider,
        clock=clock,
        runtime_factory=lambda **values: RuntimeComposition.create(
            **values,
            journal=journal,
        ),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        wait=wait_until_close,
    )

    path = tmp_path / "sessions" / "2026-08-27-disabled.json"
    assert report.status is NoOvernightEvidenceStatus.COMPLETE
    assert report.qualification is NoOvernightQualificationStatus.NOT_APPLICABLE
    assert report.reason_codes == ()
    assert read_no_overnight_session_report(path) == report
    records = journal.records(
        "no-overnight-evidence-v1:"
        "no-overnight-campaign-2026-08-operational-v1:"
        "DISABLED_BASELINE:2026-08-27"
    )
    open_sequence = next(
        item.sequence
        for item in records
        if item.record.kind == "no_overnight_evidence_window_opened.v1"
    )
    close_sequence = next(
        item.sequence
        for item in records
        if item.record.kind == "no_overnight_evidence_window_closed.v1"
    )
    assert open_sequence < close_sequence
    assert journal.sessions(session_id_prefix="no-overnight-v1-") == ()


def test_capture_disabled_baseline_normalizes_postgres_utc_open_time(
    tmp_path,
) -> None:
    journal = UtcAtomicOpenJournal()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def wait_until_close(_seconds: float) -> None:
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    report = capture_disabled_baseline(
        campaign_id="postgres-utc-open-time",
        session_date=date(2026, 8, 27),
        code_identity="a" * 40,
        artifact_root=tmp_path,
        marker_journal_factory=lambda: journal,
        provider=MockProvider(),
        clock=clock,
        runtime_factory=lambda **values: RuntimeComposition.create(
            **values,
            journal=journal,
        ),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        wait=wait_until_close,
    )

    assert report.observation.observed_from.isoformat() == (
        "2026-08-27T08:45:00+08:00"
    )
    opened = next(
        item
        for item in journal.records(
            "no-overnight-evidence-v1:postgres-utc-open-time:"
            "DISABLED_BASELINE:2026-08-27"
        )
        if item.record.kind == "no_overnight_evidence_window_opened.v1"
    )
    assert opened.record.occurred_at.isoformat() == (
        "2026-08-27T00:45:00+00:00"
    )


@pytest.mark.parametrize(
    "started_at, session_date",
    (
        ("2026-08-27T09:00:00.000001+08:00", date(2026, 8, 27)),
        ("2026-08-29T08:45:00+08:00", date(2026, 8, 29)),
    ),
)
def test_capture_disabled_baseline_rejects_invalid_start(
    tmp_path,
    started_at: str,
    session_date: date,
) -> None:
    journal = InMemoryJournalRepository()
    provider = ClosingMockProvider()
    runtime_called = False
    journal_created = False

    def marker_journal_factory():
        nonlocal journal_created
        journal_created = True
        return journal

    def runtime_factory(**_values):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not start")

    with pytest.raises(ValueError):
        capture_disabled_baseline(
            campaign_id="no-overnight-campaign-2026-08-operational-v1",
            session_date=session_date,
            code_identity="a" * 40,
            artifact_root=tmp_path,
            marker_journal_factory=marker_journal_factory,
            provider=provider,
            clock=MutableClock(datetime.fromisoformat(started_at)),
            runtime_factory=runtime_factory,
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        )

    assert runtime_called is False
    assert journal_created is False
    assert provider.closed is True
    assert journal.sessions(session_id_prefix="no-overnight-evidence-v1:") == ()
    assert not (tmp_path / "sessions").exists()


def test_capture_disabled_baseline_rejects_symlinked_artifact_root(tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(target, target_is_directory=True)
    journal = InMemoryJournalRepository()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def wait_until_close(_seconds: float) -> None:
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    with pytest.raises(ValueError, match="unsafe"):
        capture_disabled_baseline(
            campaign_id="no-overnight-campaign-2026-08-operational-v1",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=linked_root,
            marker_journal_factory=lambda: journal,
            provider=MockProvider(),
            clock=clock,
            runtime_factory=lambda **values: RuntimeComposition.create(
                **values,
                journal=journal,
            ),
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            wait=wait_until_close,
        )

    assert not (target / "sessions").exists()


def test_capture_disabled_baseline_seals_safety_finding_before_failure(
    tmp_path,
) -> None:
    journal = InMemoryJournalRepository()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def wait_until_close(_seconds: float) -> None:
        journal.start_session(
            JournalSession(
                session_id="no-overnight-v1-2026-08-27",
                started_at=datetime.fromisoformat("2026-08-27T09:01:00+08:00"),
                mode="NO_OVERNIGHT_DISABLED_SHOULD_NOT_EXIST",
                metadata={"unexpected_controller_session": True},
            )
        )
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    with pytest.raises(RuntimeError, match="non-qualifying"):
        capture_disabled_baseline(
            campaign_id="no-overnight-campaign-2026-08-operational-v1",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=tmp_path,
            marker_journal_factory=lambda: journal,
            provider=MockProvider(),
            clock=clock,
            runtime_factory=lambda **values: RuntimeComposition.create(
                **values,
                journal=journal,
            ),
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            wait=wait_until_close,
        )

    report = read_no_overnight_session_report(
        tmp_path / "sessions" / "2026-08-27-disabled.json"
    )
    assert "DISABLED_CONTROLLER_SESSION_PRESENT" in report.reason_codes


def test_capture_disabled_baseline_rejects_sessions_directory_replacement(
    tmp_path,
) -> None:
    journal = InMemoryJournalRepository()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def replace_sessions_directory(_seconds: float) -> None:
        (tmp_path / "sessions").rename(tmp_path / "original-sessions")
        (tmp_path / "sessions").mkdir()
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    with pytest.raises(ValueError, match="changed during capture"):
        capture_disabled_baseline(
            campaign_id="no-overnight-campaign-2026-08-operational-v1",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=tmp_path,
            marker_journal_factory=lambda: journal,
            provider=MockProvider(),
            clock=clock,
            runtime_factory=lambda **values: RuntimeComposition.create(
                **values,
                journal=journal,
            ),
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            wait=replace_sessions_directory,
        )

    assert not tuple((tmp_path / "sessions").iterdir())
    assert not tuple((tmp_path / "original-sessions").iterdir())


def test_capture_disabled_baseline_rechecks_time_after_journal_factory(
    tmp_path,
) -> None:
    journal = InMemoryJournalRepository()
    clock = MutableClock(
        datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    )
    runtime_called = False

    def delayed_journal_factory():
        clock.value = datetime.fromisoformat("2026-08-27T09:00:00.000001+08:00")
        return journal

    def runtime_factory(**_values):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not start")

    with pytest.raises(ValueError, match="no later than open"):
        capture_disabled_baseline(
            campaign_id="review-time-boundary",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=tmp_path,
            marker_journal_factory=delayed_journal_factory,
            provider=MockProvider(),
            clock=clock,
            runtime_factory=runtime_factory,
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        )

    session_id = (
        "no-overnight-evidence-v1:review-time-boundary:"
        "DISABLED_BASELINE:2026-08-27"
    )
    assert journal.session(session_id) is None
    assert journal.records(session_id) == ()
    assert runtime_called is False
    assert not (tmp_path / "sessions" / "2026-08-27-disabled.json").exists()


def test_capture_disabled_baseline_rolls_back_if_session_start_crosses_open(
    tmp_path,
) -> None:
    clock = MutableClock(
        datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    )
    journal = StartSessionCrossesOpenJournal(clock)
    runtime_called = False

    def runtime_factory(**_values):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not start")

    with pytest.raises(JournalCutoffExceededError):
        capture_disabled_baseline(
            campaign_id="review-start-session-time-boundary",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=tmp_path,
            marker_journal_factory=lambda: journal,
            provider=MockProvider(),
            clock=clock,
            runtime_factory=runtime_factory,
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        )

    session_id = (
        "no-overnight-evidence-v1:review-start-session-time-boundary:"
        "DISABLED_BASELINE:2026-08-27"
    )
    assert journal.session(session_id) is None
    assert journal.records(session_id) == ()
    assert journal.append_called is False
    assert runtime_called is False
    assert not (tmp_path / "sessions" / "2026-08-27-disabled.json").exists()


@pytest.mark.parametrize(
    "returned_at, message",
    (
        (
            datetime.fromisoformat("2026-08-27T09:00:00.000001+08:00"),
            "no later than open",
        ),
        (
            datetime.fromisoformat("2026-08-27T08:59:59.800000+08:00"),
            "moved backwards after atomic open",
        ),
    ),
)
def test_capture_disabled_baseline_keeps_incomplete_open_after_late_return(
    tmp_path,
    returned_at: datetime,
    message: str,
) -> None:
    opened_at = datetime.fromisoformat("2026-08-27T08:59:59.900000+08:00")
    clock = MutableClock(opened_at)
    journal = AtomicReturnMovesClockJournal(clock, returned_at)
    provider = ClosingMockProvider()
    runtime_called = False

    def runtime_factory(**_values):
        nonlocal runtime_called
        runtime_called = True
        raise AssertionError("runtime must not start")

    with pytest.raises(ValueError, match=message):
        capture_disabled_baseline(
            campaign_id="review-post-atomic-boundary",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=tmp_path,
            marker_journal_factory=lambda: journal,
            provider=provider,
            clock=clock,
            runtime_factory=runtime_factory,
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        )

    session_id = (
        "no-overnight-evidence-v1:review-post-atomic-boundary:"
        "DISABLED_BASELINE:2026-08-27"
    )
    records = journal.records(session_id)
    assert journal.session(session_id) is not None
    assert len(records) == 1
    assert records[0].record.kind == "no_overnight_evidence_window_opened.v1"
    assert runtime_called is False
    assert provider.closed is True
    assert not (tmp_path / "sessions" / "2026-08-27-disabled.json").exists()


def test_capture_disabled_baseline_persists_fresh_post_factory_time(tmp_path) -> None:
    journal = InMemoryJournalRepository()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))

    def delayed_journal_factory():
        clock.value = datetime.fromisoformat("2026-08-27T08:46:00+08:00")
        return journal

    def finish_wait(_seconds: float) -> None:
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    report = capture_disabled_baseline(
        campaign_id="review-fresh-time-boundary",
        session_date=date(2026, 8, 27),
        code_identity="a" * 40,
        artifact_root=tmp_path,
        marker_journal_factory=delayed_journal_factory,
        provider=MockProvider(),
        clock=clock,
        runtime_factory=lambda **values: RuntimeComposition.create(
            **values,
            journal=journal,
        ),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        wait=finish_wait,
    )

    assert report.observation.observed_from == datetime.fromisoformat(
        "2026-08-27T08:46:00+08:00"
    )


def test_capture_disabled_baseline_rejects_moved_sessions_under_new_root(
    tmp_path,
) -> None:
    journal = InMemoryJournalRepository()
    clock = MutableClock(datetime.fromisoformat("2026-08-27T08:45:00+08:00"))
    root = tmp_path / "campaign"
    displaced = tmp_path / "displaced-campaign"

    def replace_root_but_keep_sessions(_seconds: float) -> None:
        root.rename(displaced)
        root.mkdir()
        (displaced / "sessions").rename(root / "sessions")
        clock.value = datetime.fromisoformat("2026-08-27T13:30:00+08:00")

    with pytest.raises(ValueError, match="changed during capture"):
        capture_disabled_baseline(
            campaign_id="review-root-lineage",
            session_date=date(2026, 8, 27),
            code_identity="a" * 40,
            artifact_root=root,
            marker_journal_factory=lambda: journal,
            provider=MockProvider(),
            clock=clock,
            runtime_factory=lambda **values: RuntimeComposition.create(
                **values,
                journal=journal,
            ),
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            wait=replace_root_but_keep_sessions,
        )

    filename = "2026-08-27-disabled.json"
    assert not (root / "sessions" / filename).exists()
    assert not (displaced / "sessions" / filename).exists()


def test_env_file_is_no_follow_and_does_not_inherit_process_values(
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / "capture.env"
    env_file.write_text(
        "TRADING_JOURNAL_BACKEND=postgresql\n"
        "PostgreSQL_DSN=postgresql://reviewed.example/reviewed\n"
    )
    monkeypatch.setenv("PostgreSQL_DSN", "postgresql://ambient.example/wrong")

    values = capture_script._environment_from_file(env_file)

    assert values["PostgreSQL_DSN"] == "postgresql://reviewed.example/reviewed"
    assert os.environ["PostgreSQL_DSN"] == "postgresql://ambient.example/wrong"
    linked_env = tmp_path / "linked.env"
    linked_env.symlink_to(env_file)
    with pytest.raises(ValueError, match="unsafe"):
        capture_script._environment_from_file(linked_env)
    parent_target = tmp_path / "parent-target"
    parent_target.mkdir()
    nested_env = parent_target / "nested.env"
    nested_env.write_text(env_file.read_text())
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(parent_target, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        capture_script._environment_from_file(linked_parent / "nested.env")


def test_cli_checks_code_identity_before_constructing_postgres(
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / "capture.env"
    env_file.write_text(
        "TRADING_JOURNAL_BACKEND=postgresql\n"
        "PostgreSQL_DSN=postgresql://reviewed.example/reviewed\n"
    )
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}")
    journal_created = False

    def fail_code_identity() -> str:
        raise ValueError("dirty worktree")

    def build_journal(_persistence):
        nonlocal journal_created
        journal_created = True
        raise AssertionError("PostgreSQL must not be initialized")

    monkeypatch.setattr(capture_script, "_code_identity", fail_code_identity)
    monkeypatch.setattr(capture_script, "build_journal_repository", build_journal)

    with pytest.raises(ValueError, match="dirty worktree"):
        capture_script.main(
            (
                "--campaign-id",
                "no-overnight-campaign-2026-08-operational-v1",
                "--session-date",
                "2026-08-27",
                "--artifact-root",
                str(tmp_path / "campaign"),
                "--env-file",
                str(env_file),
                "--settings-file",
                str(settings_file),
            )
        )

    assert journal_created is False
