"""Operational capture seam for DISABLED and OBSERVE_ONLY evidence sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import os
from pathlib import Path
import re
import stat
from time import sleep
from zoneinfo import ZoneInfo

from config import twse_calendar_2026
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MarketDataProvider, MockProvider
from runtime.clock import Clock
from runtime.composition import RuntimeComposition
from runtime.ports import JournalRepository
from simulation.settings import (
    SETTINGS_SCHEMA_V2,
    LocalPaperSettings,
    LocalPaperSettingsState,
)
from trading.local_paper import (
    LOCAL_PAPER_FILL_KIND,
    LOCAL_PAPER_FILL_V2_KIND,
    LOCAL_PAPER_FILL_V3_KIND,
)
from trading.no_overnight_evidence import (
    NO_OVERNIGHT_EVIDENCE_WINDOW_CLOSE_KIND,
    NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND,
    NoOvernightEvidenceStage,
    NoOvernightEvidenceStatus,
    NoOvernightEvidenceWindowSpec,
    NoOvernightQualificationStatus,
    NoOvernightSessionReport,
    build_no_overnight_session_report,
    close_no_overnight_evidence_window,
    open_no_overnight_evidence_window,
    read_no_overnight_session_report,
    write_no_overnight_session_report,
)


RuntimeFactory = Callable[..., RuntimeComposition]
JournalFactory = Callable[[], JournalRepository]
ActiveSettingsReader = Callable[[], LocalPaperSettingsState]
_DirectoryFence = tuple[int, int, int, int, int, int, int]
_DISABLED_REPORT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-disabled\.json$")


def _open_directory(path: Path, label: str, *, create: bool) -> int:
    try:
        absolute_path = Path(os.path.abspath(os.fspath(path)))
    except TypeError as error:
        raise ValueError(f"{label} path is invalid") from error
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(os.sep, flags)
    try:
        for component in absolute_path.parts[1:]:
            try:
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise ValueError(f"{label} must be a directory")
        return directory_fd
    except (OSError, ValueError) as error:
        os.close(directory_fd)
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"{label} path is unsafe or unavailable") from error


def _directory_fence(directory_fd: int) -> _DirectoryFence:
    item = os.fstat(directory_fd)
    return (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _existing_directory_fence(path: Path, label: str) -> _DirectoryFence:
    directory_fd = _open_directory(path, label, create=False)
    try:
        return _directory_fence(directory_fd)
    finally:
        os.close(directory_fd)


@dataclass
class _CampaignArtifactDirectories:
    root_path: Path
    sessions_path: Path
    root_fd: int
    sessions_fd: int
    initial_root_fence: _DirectoryFence
    initial_sessions_fence: _DirectoryFence

    def verify_before_write(self) -> None:
        if (
            _directory_fence(self.root_fd) != self.initial_root_fence
            or _existing_directory_fence(
                self.root_path,
                "campaign artifact root",
            )
            != self.initial_root_fence
            or _directory_fence(self.sessions_fd) != self.initial_sessions_fence
            or _existing_directory_fence(
                self.sessions_path,
                "campaign sessions directory",
            )
            != self.initial_sessions_fence
        ):
            raise ValueError("campaign artifact directories changed during capture")

    def verify_after_write(self) -> None:
        current_sessions_fence = _directory_fence(self.sessions_fd)
        if (
            _directory_fence(self.root_fd) != self.initial_root_fence
            or _existing_directory_fence(
                self.root_path,
                "campaign artifact root",
            )
            != self.initial_root_fence
            or _existing_directory_fence(
                self.sessions_path,
                "campaign sessions directory",
            )
            != current_sessions_fence
        ):
            raise ValueError("campaign artifact directories changed during capture")

    def close(self) -> None:
        os.close(self.sessions_fd)
        os.close(self.root_fd)


def _prepare_sessions_directory(
    artifact_root: Path,
) -> _CampaignArtifactDirectories:
    absolute_root = Path(os.path.abspath(os.fspath(artifact_root)))
    root_fd = _open_directory(
        absolute_root,
        "campaign artifact root",
        create=True,
    )
    sessions_fd: int | None = None
    try:
        try:
            sessions_fd = os.open(
                "sessions",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
        except FileNotFoundError:
            try:
                os.mkdir("sessions", 0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            except FileExistsError:
                pass
            sessions_fd = os.open(
                "sessions",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
        if not stat.S_ISDIR(os.fstat(sessions_fd).st_mode):
            raise ValueError("campaign sessions path must be a directory")
        return _CampaignArtifactDirectories(
            root_path=absolute_root,
            sessions_path=absolute_root / "sessions",
            root_fd=root_fd,
            sessions_fd=sessions_fd,
            initial_root_fence=_directory_fence(root_fd),
            initial_sessions_fence=_directory_fence(sessions_fd),
        )
    except OSError as error:
        if sessions_fd is not None:
            os.close(sessions_fd)
        os.close(root_fd)
        raise ValueError(
            "campaign sessions path is unsafe or unavailable"
        ) from error
    except Exception:
        if sessions_fd is not None:
            os.close(sessions_fd)
        os.close(root_fd)
        raise


def _validate_open_time(
    value: datetime,
    *,
    session_date: date,
    reviewed_open: datetime,
    zone: ZoneInfo,
    label: str = "DISABLED baseline",
    strict_before_open: bool = False,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} clock must be timezone-aware")
    if value.astimezone(zone).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError(f"{label} clock timezone differs from calendar")
    late = value >= reviewed_open if strict_before_open else value > reviewed_open
    if value.date() != session_date or late:
        boundary = (
            "strictly before open"
            if strict_before_open
            else "no later than open"
        )
        raise ValueError(
            f"{label} must start on the session date {boundary}"
        )


def _default_evidence_settings_state() -> LocalPaperSettingsState:
    settings = LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())
    return LocalPaperSettingsState(
        revision=0,
        active=settings,
        draft=settings,
        active_session_id=LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID,
        active_settings_revision=0,
        draft_settings_revision=0,
    )


def _active_settings_state(
    reader: ActiveSettingsReader | None,
    *,
    required: bool,
) -> LocalPaperSettingsState:
    if reader is None:
        if required:
            raise ValueError("active Local Paper settings reader is required")
        state = _default_evidence_settings_state()
    else:
        state = reader()
    if not isinstance(state, LocalPaperSettingsState):
        raise ValueError("active Local Paper settings state is invalid")
    if state.active.schema_version != SETTINGS_SCHEMA_V2:
        raise ValueError("active Local Paper settings must use v2")
    return state


def _require_active_settings_unchanged(
    reader: ActiveSettingsReader | None,
    expected: LocalPaperSettingsState,
    *,
    required: bool,
) -> None:
    if _active_settings_state(reader, required=required) != expected:
        raise ValueError("active Local Paper settings changed during capture")


def _require_active_local_paper_session(
    journal: JournalRepository,
    state: LocalPaperSettingsState,
    *,
    required: bool,
) -> None:
    session = journal.session(state.active_session_id)
    if session is None:
        if required:
            raise ValueError("active Local Paper Journal session is missing")
        return
    expected_metadata = {
        "settings_schema": state.active.schema_version,
        "settings_revision": state.active_settings_revision,
        "settings_digest": state.active.digest,
        "account_scope_id": LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        "policy_family_id": LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    }
    if session.mode != "LOCAL_PAPER_SIMULATION" or any(
        session.metadata.get(field_name) != expected
        for field_name, expected in expected_metadata.items()
    ):
        raise ValueError("active Local Paper session/settings identity mismatch")


def _observe_only_config() -> NoOvernightPolicyConfig:
    return NoOvernightPolicyConfig(
        mode=NoOvernightMode.OBSERVE_ONLY,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        policy_version="observe-only-v1",
        timezone="Asia/Taipei",
        market_open=time(9, 0),
        no_new_entry_at=time(13, 10),
        cancel_entry_at=time(13, 15),
        flatten_at=time(13, 20),
        aggressive_exit_at=time(13, 25),
        final_reconciliation_at=time(13, 28),
        reviewed_session_close=time(13, 30),
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
        executable_book_policy_id="local-paper-book-v1",
    )


def _read_disabled_predecessor(
    directories: _CampaignArtifactDirectories,
    *,
    campaign_id: str,
    session_date: date,
    code_identity: str,
    calendar: ReviewedEquityCalendar,
    provider_identity: str,
    local_paper_session_id: str,
) -> NoOvernightSessionReport:
    names = tuple(
        sorted(
            name
            for name in os.listdir(directories.sessions_fd)
            if _DISABLED_REPORT_NAME.fullmatch(name)
        )
    )
    if len(names) != 1:
        raise ValueError("exactly one COMPLETE DISABLED predecessor is required")
    path = directories.sessions_path / names[0]
    report = read_no_overnight_session_report(path)
    observation = report.observation
    expected_name = f"{observation.session_date.isoformat()}-disabled.json"
    if path.name != expected_name:
        raise ValueError("DISABLED predecessor filename conflicts with its identity")
    if observation.stage is not NoOvernightEvidenceStage.DISABLED_BASELINE:
        raise ValueError("DISABLED predecessor stage is invalid")
    disabled_config = NoOvernightPolicyConfig.disabled(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )
    expected_open = datetime.combine(
        observation.session_date,
        time(9, 0),
        tzinfo=ZoneInfo(calendar.timezone),
    )
    expected_close = datetime.combine(
        observation.session_date,
        time(13, 30),
        tzinfo=ZoneInfo(calendar.timezone),
    )
    if (
        observation.policy_version != disabled_config.policy_version
        or observation.policy_digest != disabled_config.policy_digest
        or observation.reviewed_open != expected_open
        or observation.reviewed_close != expected_close
    ):
        raise ValueError("DISABLED predecessor policy/window identity mismatch")
    if report.status is not NoOvernightEvidenceStatus.COMPLETE:
        raise ValueError("DISABLED predecessor must be COMPLETE")
    if (
        report.qualification is not NoOvernightQualificationStatus.NOT_APPLICABLE
        or report.reason_codes
    ):
        raise ValueError("DISABLED predecessor safety qualification is invalid")
    if observation.session_date >= session_date:
        raise ValueError("DISABLED predecessor must be from an earlier session")
    if observation.campaign_id != campaign_id:
        raise ValueError("DISABLED predecessor campaign identity mismatch")
    if observation.code_identity != code_identity:
        raise ValueError("DISABLED predecessor code identity mismatch")
    if (
        observation.calendar_schema_version != calendar.schema_version
        or observation.calendar_digest != calendar.source_digest
        or observation.timezone != calendar.timezone
    ):
        raise ValueError("DISABLED predecessor calendar identity mismatch")
    if observation.expected_provider_identity != provider_identity:
        raise ValueError("DISABLED predecessor provider identity mismatch")
    if (
        observation.local_paper_session_id != local_paper_session_id
        or report.local_paper_session_id != local_paper_session_id
    ):
        raise ValueError("DISABLED predecessor Local Paper session mismatch")
    if (
        observation.account_scope_id
        != LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id
        or observation.policy_family_id
        != LOCAL_PAPER_POLICY_FAMILY.policy_family_id
    ):
        raise ValueError("DISABLED predecessor scope identity mismatch")
    if (
        report.metrics.no_overnight_exit_attempt_count
        or report.metrics.no_overnight_exit_fill_count
        or report.metrics.synthetic_fill_count
        or report.metrics.duplicate_exit_side_effect_count
        or report.metrics.wrong_horizon_liquidation_count
    ):
        raise ValueError("DISABLED predecessor contains handler/order/fill side effects")
    return report


def _require_observe_output_absent(
    directories: _CampaignArtifactDirectories,
    *,
    session_date: date,
) -> None:
    name = f"{session_date.isoformat()}-observe-only.json"
    try:
        os.stat(name, dir_fd=directories.sessions_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise ValueError("OBSERVE_ONLY report path is unsafe or unavailable") from error
    raise ValueError("OBSERVE_ONLY report already exists")


def _require_disabled_predecessor_journal(
    journal: JournalRepository,
    report: NoOvernightSessionReport,
) -> None:
    observation = report.observation
    prefix = (
        f"no-overnight-evidence-v1:{observation.campaign_id}:"
        f"{NoOvernightEvidenceStage.DISABLED_BASELINE.value}:"
    )
    expected_session_id = f"{prefix}{observation.session_date.isoformat()}"
    sessions = journal.sessions(session_id_prefix=prefix)
    if len(sessions) != 1 or sessions[0].session_id != expected_session_id:
        raise ValueError(
            "DISABLED predecessor Journal window is missing, duplicate, or incomplete"
        )
    session = sessions[0]
    if (
        session.mode != "NO_OVERNIGHT_EVIDENCE_WINDOW"
        or dict(session.metadata)
        != {
            "window_spec": observation.window_spec.payload(),
            "activation_authority": "NONE_EVIDENCE_ONLY",
        }
        or session.started_at != observation.observed_from
    ):
        raise ValueError("DISABLED predecessor Journal identity mismatch")
    records = journal.records(expected_session_id)
    if len(records) != 2:
        raise ValueError(
            "DISABLED predecessor Journal window is missing, duplicate, or incomplete"
        )
    opened = next(
        (
            result
            for result in records
            if result.sequence == observation.window_open_journal_sequence
        ),
        None,
    )
    closed = next(
        (
            result
            for result in records
            if result.sequence == observation.window_close_journal_sequence
        ),
        None,
    )
    if (
        opened is None
        or closed is None
        or opened.record.kind != NO_OVERNIGHT_EVIDENCE_WINDOW_OPEN_KIND
        or dict(opened.record.payload) != observation.window_spec.payload()
        or opened.record.occurred_at != observation.observed_from
        or opened.record.fingerprint
        != observation.window_open_record_fingerprint
        or closed.record.kind != NO_OVERNIGHT_EVIDENCE_WINDOW_CLOSE_KIND
        or closed.record.occurred_at != observation.observed_through
        or closed.record.fingerprint
        != observation.window_close_record_fingerprint
        or dict(closed.record.payload)
        != {
            **observation.window_spec.payload(),
            "open_record_id": opened.record.record_id,
            "open_journal_sequence": opened.sequence,
            "open_record_fingerprint": opened.record.fingerprint,
        }
    ):
        raise ValueError("DISABLED predecessor Journal markers do not replay")


def _is_local_paper_side_effect_kind(kind: str) -> bool:
    return (
        kind in {"order_command.v1", "order_command.v2"}
        or kind.startswith("local_paper_order_state.")
        or kind.startswith("local_paper_cancel_")
        or kind.startswith("local_paper_cancellation.")
        or kind.startswith("local_paper_fill.")
    )


def _require_no_local_paper_side_effects(
    journal: JournalRepository,
    *,
    session_id: str,
    session_date: date,
    zone: ZoneInfo,
    after_sequence: int | None = None,
) -> None:
    records = journal.records(
        session_id,
        after_sequence=after_sequence or 0,
    )
    if any(
        _is_local_paper_side_effect_kind(result.record.kind)
        and (
            after_sequence is not None
            or result.record.occurred_at.astimezone(zone).date() == session_date
        )
        for result in records
    ):
        raise ValueError(
            "OBSERVE_ONLY session contains order/cancel/fill side effects"
        )


def _require_v4_fill_provenance(
    journal: JournalRepository,
    *,
    session_id: str,
    session_date: date,
    zone: ZoneInfo,
    after_sequence: int | None = None,
) -> None:
    legacy_kinds = {
        LOCAL_PAPER_FILL_KIND,
        LOCAL_PAPER_FILL_V2_KIND,
        LOCAL_PAPER_FILL_V3_KIND,
    }
    records = journal.records(
        session_id,
        after_sequence=after_sequence or 0,
    )
    if any(
        result.record.kind in legacy_kinds
        and (
            after_sequence is not None
            or result.record.occurred_at.astimezone(zone).date() == session_date
        )
        for result in records
    ):
        raise ValueError(
            "OBSERVE_ONLY requires complete local_paper_fill.v4 provenance"
        )


def _wait_observe_only_until_close(
    composition: RuntimeComposition,
    target: datetime,
    *,
    clock: Clock,
    initial_at: datetime,
    wait: Callable[[float], None],
    state: LocalPaperSettingsState,
    active_settings_reader: ActiveSettingsReader,
    local_paper_baseline_sequence: int,
) -> datetime:
    previous = clock.now()
    if previous < initial_at:
        raise ValueError(
            "OBSERVE_ONLY clock moved backwards before session wait"
        )
    zone = ZoneInfo(composition.no_overnight_controller.config.timezone)
    while previous < target:
        wait(min(30.0, max(0.001, (target - previous).total_seconds())))
        current = clock.now()
        if current < previous:
            raise ValueError("OBSERVE_ONLY clock moved backwards during capture")
        _require_active_settings_unchanged(
            active_settings_reader,
            state,
            required=True,
        )
        _require_v4_fill_provenance(
            composition.journal,
            session_id=state.active_session_id,
            session_date=target.date(),
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        _require_no_local_paper_side_effects(
            composition.journal,
            session_id=state.active_session_id,
            session_date=target.date(),
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        if current >= target:
            return current
        composition.no_overnight_controller.run_once(current)
        _require_no_local_paper_side_effects(
            composition.journal,
            session_id=state.active_session_id,
            session_date=target.date(),
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        previous = current
    return previous


def _close_if_supported(value: object) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


def _provider_identity(provider: MarketDataProvider) -> str:
    identity = getattr(provider, "environment_identity", None)
    if isinstance(identity, str) and identity.strip():
        return identity.strip()
    return f"{type(provider).__module__}.{type(provider).__qualname__}"


def _wait_until(
    target: datetime,
    *,
    clock: Clock,
    wait: Callable[[float], None],
) -> datetime:
    while (current := clock.now()) < target:
        wait(min(30.0, max(0.001, (target - current).total_seconds())))
    return current


def capture_disabled_baseline(
    *,
    campaign_id: str,
    session_date: date,
    code_identity: str,
    artifact_root: Path,
    marker_journal_factory: JournalFactory,
    provider: MarketDataProvider,
    clock: Clock,
    runtime_factory: RuntimeFactory,
    active_settings_reader: ActiveSettingsReader | None = None,
    calendar: ReviewedEquityCalendar | None = None,
    wait: Callable[[float], None] = sleep,
) -> NoOvernightSessionReport:
    """Capture one real-time baseline without no-overnight execution authority."""

    composition: RuntimeComposition | None = None
    marker_journal: JournalRepository | None = None
    artifact_directories: _CampaignArtifactDirectories | None = None
    try:
        reviewed_calendar = calendar or ReviewedEquityCalendar.from_path(
            twse_calendar_2026.PATH
        )
        if not reviewed_calendar.is_trading_day(session_date):
            raise ValueError("DISABLED baseline requires a reviewed trading day")

        zone = ZoneInfo(reviewed_calendar.timezone)
        reviewed_open = datetime.combine(session_date, time(9, 0), tzinfo=zone)
        reviewed_close = datetime.combine(session_date, time(13, 30), tzinfo=zone)
        preflight_at = clock.now()
        _validate_open_time(
            preflight_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
        )
        active_settings = _active_settings_state(
            active_settings_reader,
            required=False,
        )

        config = NoOvernightPolicyConfig.disabled(
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        )
        spec = NoOvernightEvidenceWindowSpec(
            campaign_id=campaign_id,
            stage=NoOvernightEvidenceStage.DISABLED_BASELINE,
            session_date=session_date,
            account_scope_id=config.account_scope_id,
            policy_family_id=config.policy_family_id,
            policy_version=config.policy_version,
            policy_digest=config.policy_digest,
            calendar_schema_version=reviewed_calendar.schema_version,
            calendar_digest=reviewed_calendar.source_digest,
            timezone=config.timezone,
            reviewed_open=reviewed_open,
            reviewed_close=reviewed_close,
            code_identity=code_identity,
            expected_provider_identity=_provider_identity(provider),
            local_paper_session_id=active_settings.active_session_id,
        )
        artifact_directories = _prepare_sessions_directory(artifact_root)
        marker_journal = marker_journal_factory()
        _require_active_local_paper_session(
            marker_journal,
            active_settings,
            required=active_settings_reader is not None,
        )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=False,
        )
        opened_at = clock.now()
        _validate_open_time(
            opened_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
        )
        if opened_at < preflight_at:
            raise ValueError("DISABLED baseline clock moved backwards before append")
        opened = open_no_overnight_evidence_window(
            journal=marker_journal,
            spec=spec,
            opened_at=opened_at,
            latest_allowed_at=spec.reviewed_open,
            authoritative_now=clock.now,
        )
        _close_if_supported(marker_journal)
        marker_journal = None
        runtime_start_at = clock.now()
        _validate_open_time(
            runtime_start_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
        )
        if runtime_start_at < opened.record.occurred_at:
            raise ValueError(
                "DISABLED baseline clock moved backwards after atomic open"
            )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=False,
        )
        composition = runtime_factory(
            provider=provider,
            clock=clock,
            local_paper_settings=active_settings.active,
            local_paper_settings_revision=(
                active_settings.active_settings_revision
            ),
            local_paper_session_id=active_settings.active_session_id,
            no_overnight_config=config,
            equity_calendar=reviewed_calendar,
        )
        closed_at = _wait_until(reviewed_close, clock=clock, wait=wait)
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=False,
        )
        observation = close_no_overnight_evidence_window(
            journal=composition.journal,
            spec=spec,
            opened=opened,
            closed_at=closed_at,
        )
        report = build_no_overnight_session_report(
            journal=composition.journal,
            observation=observation,
        )
        artifact_directories.verify_before_write()
        report_path = (
            artifact_directories.sessions_path
            / f"{session_date.isoformat()}-disabled.json"
        )
        write_no_overnight_session_report(report_path, report)
        if read_no_overnight_session_report(report_path) != report:
            raise ValueError("persisted DISABLED baseline does not replay exactly")
        artifact_directories.verify_after_write()
        if (
            report.status is not NoOvernightEvidenceStatus.COMPLETE
            or report.qualification
            is not NoOvernightQualificationStatus.NOT_APPLICABLE
            or report.reason_codes
        ):
            raise RuntimeError("DISABLED baseline sealed non-qualifying evidence")
        return report
    finally:
        try:
            if composition is not None:
                composition.close()
            else:
                try:
                    if marker_journal is not None:
                        _close_if_supported(marker_journal)
                finally:
                    provider.close()
        finally:
            if artifact_directories is not None:
                artifact_directories.close()


def capture_observe_only(
    *,
    campaign_id: str,
    session_date: date,
    code_identity: str,
    artifact_root: Path,
    marker_journal_factory: JournalFactory,
    provider: MarketDataProvider,
    clock: Clock,
    runtime_factory: RuntimeFactory,
    active_settings_reader: ActiveSettingsReader,
    calendar: ReviewedEquityCalendar | None = None,
    wait: Callable[[float], None] = sleep,
) -> NoOvernightSessionReport:
    """Capture one full OBSERVE_ONLY session without Local Paper command authority."""

    composition: RuntimeComposition | None = None
    marker_journal: JournalRepository | None = None
    artifact_directories: _CampaignArtifactDirectories | None = None
    try:
        if type(provider) is not MockProvider:
            raise ValueError("OBSERVE_ONLY requires the exact MockProvider")
        reviewed_calendar = calendar or ReviewedEquityCalendar.from_path(
            twse_calendar_2026.PATH
        )
        if not reviewed_calendar.is_trading_day(session_date):
            raise ValueError("OBSERVE_ONLY requires a reviewed trading day")
        zone = ZoneInfo(reviewed_calendar.timezone)
        reviewed_open = datetime.combine(session_date, time(9, 0), tzinfo=zone)
        reviewed_close = datetime.combine(session_date, time(13, 30), tzinfo=zone)
        preflight_at = clock.now()
        _validate_open_time(
            preflight_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
            label="OBSERVE_ONLY",
            strict_before_open=True,
        )
        active_settings = _active_settings_state(
            active_settings_reader,
            required=True,
        )
        config = _observe_only_config()
        if config.timezone != reviewed_calendar.timezone:
            raise ValueError("OBSERVE_ONLY policy timezone conflicts with calendar")
        provider_identity = _provider_identity(provider)
        artifact_directories = _prepare_sessions_directory(artifact_root)
        artifact_directories.verify_before_write()
        _require_observe_output_absent(
            artifact_directories,
            session_date=session_date,
        )
        predecessor = _read_disabled_predecessor(
            artifact_directories,
            campaign_id=campaign_id,
            session_date=session_date,
            code_identity=code_identity,
            calendar=reviewed_calendar,
            provider_identity=provider_identity,
            local_paper_session_id=active_settings.active_session_id,
        )
        artifact_directories.verify_before_write()
        spec = NoOvernightEvidenceWindowSpec(
            campaign_id=campaign_id,
            stage=NoOvernightEvidenceStage.OBSERVE_ONLY,
            session_date=session_date,
            account_scope_id=config.account_scope_id,
            policy_family_id=config.policy_family_id,
            policy_version=config.policy_version,
            policy_digest=config.policy_digest,
            calendar_schema_version=reviewed_calendar.schema_version,
            calendar_digest=reviewed_calendar.source_digest,
            timezone=config.timezone,
            reviewed_open=reviewed_open,
            reviewed_close=reviewed_close,
            code_identity=code_identity,
            expected_provider_identity=provider_identity,
            local_paper_session_id=active_settings.active_session_id,
        )
        marker_journal = marker_journal_factory()
        _require_active_local_paper_session(
            marker_journal,
            active_settings,
            required=True,
        )
        _require_disabled_predecessor_journal(marker_journal, predecessor)
        local_paper_records = marker_journal.records(
            active_settings.active_session_id
        )
        local_paper_baseline_sequence = (
            local_paper_records[-1].sequence if local_paper_records else 0
        )
        _require_v4_fill_provenance(
            marker_journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
        )
        _require_no_local_paper_side_effects(
            marker_journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
        )
        _require_v4_fill_provenance(
            marker_journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        _require_no_local_paper_side_effects(
            marker_journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        opened_at = clock.now()
        _validate_open_time(
            opened_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
            label="OBSERVE_ONLY",
            strict_before_open=True,
        )
        if opened_at < preflight_at:
            raise ValueError("OBSERVE_ONLY clock moved backwards before append")
        opened = open_no_overnight_evidence_window(
            journal=marker_journal,
            spec=spec,
            opened_at=opened_at,
            latest_allowed_at=spec.reviewed_open - timedelta(microseconds=1),
            authoritative_now=clock.now,
        )
        if opened.idempotent:
            raise ValueError(
                "OBSERVE_ONLY incomplete evidence window already exists"
            )
        _close_if_supported(marker_journal)
        marker_journal = None
        runtime_start_at = clock.now()
        _validate_open_time(
            runtime_start_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
            label="OBSERVE_ONLY",
            strict_before_open=True,
        )
        if runtime_start_at < opened.record.occurred_at:
            raise ValueError(
                "OBSERVE_ONLY clock moved backwards after atomic open"
            )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        composition = runtime_factory(
            provider=provider,
            clock=clock,
            local_paper_settings=active_settings.active,
            local_paper_settings_revision=(
                active_settings.active_settings_revision
            ),
            local_paper_session_id=active_settings.active_session_id,
            no_overnight_config=config,
            equity_calendar=reviewed_calendar,
        )
        if (
            composition.no_overnight_controller.config.mode
            is not NoOvernightMode.OBSERVE_ONLY
            or composition.no_overnight_worker is not None
            or composition.no_overnight_controller._command_port is not None
        ):
            raise ValueError("runtime composition violated hard OBSERVE_ONLY mode")
        runtime_ready_at = clock.now()
        _validate_open_time(
            runtime_ready_at,
            session_date=session_date,
            reviewed_open=reviewed_open,
            zone=zone,
            label="OBSERVE_ONLY",
            strict_before_open=True,
        )
        if runtime_ready_at < runtime_start_at:
            raise ValueError(
                "OBSERVE_ONLY clock moved backwards during runtime composition"
            )
        _require_v4_fill_provenance(
            composition.journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        _require_no_local_paper_side_effects(
            composition.journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        closed_at = _wait_observe_only_until_close(
            composition,
            reviewed_close,
            clock=clock,
            initial_at=runtime_ready_at,
            wait=wait,
            state=active_settings,
            active_settings_reader=active_settings_reader,
            local_paper_baseline_sequence=local_paper_baseline_sequence,
        )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        _require_active_local_paper_session(
            composition.journal,
            active_settings,
            required=True,
        )
        _require_v4_fill_provenance(
            composition.journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        composition.no_overnight_controller.run_once(closed_at)
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        _require_active_local_paper_session(
            composition.journal,
            active_settings,
            required=True,
        )
        _require_no_local_paper_side_effects(
            composition.journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        artifact_directories.verify_before_write()
        if (
            _read_disabled_predecessor(
                artifact_directories,
                campaign_id=campaign_id,
                session_date=session_date,
                code_identity=code_identity,
                calendar=reviewed_calendar,
                provider_identity=provider_identity,
                local_paper_session_id=active_settings.active_session_id,
            )
            != predecessor
        ):
            raise ValueError("DISABLED predecessor changed during capture")
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        _require_active_local_paper_session(
            composition.journal,
            active_settings,
            required=True,
        )
        observation = close_no_overnight_evidence_window(
            journal=composition.journal,
            spec=spec,
            opened=opened,
            closed_at=closed_at,
        )
        _require_v4_fill_provenance(
            composition.journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        _require_no_local_paper_side_effects(
            composition.journal,
            session_id=active_settings.active_session_id,
            session_date=session_date,
            zone=zone,
            after_sequence=local_paper_baseline_sequence,
        )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        _require_active_local_paper_session(
            composition.journal,
            active_settings,
            required=True,
        )
        report = build_no_overnight_session_report(
            journal=composition.journal,
            observation=observation,
        )
        _require_active_settings_unchanged(
            active_settings_reader,
            active_settings,
            required=True,
        )
        _require_active_local_paper_session(
            composition.journal,
            active_settings,
            required=True,
        )
        artifact_directories.verify_before_write()
        report_path = (
            artifact_directories.sessions_path
            / f"{session_date.isoformat()}-observe-only.json"
        )
        write_no_overnight_session_report(report_path, report)
        if read_no_overnight_session_report(report_path) != report:
            raise ValueError("persisted OBSERVE_ONLY report does not replay exactly")
        artifact_directories.verify_after_write()
        if (
            report.status is not NoOvernightEvidenceStatus.COMPLETE
            or report.qualification
            is not NoOvernightQualificationStatus.QUALIFIED
            or report.reason_codes
            or report.terminal_state != "CONFIRMED_FLAT"
            or report.result_status != "CURRENT"
            or report.reconciliation_status != "MATCH"
            or report.no_overnight_checkpoint_sequence
            != report.no_overnight_last_sequence
            or report.local_paper_checkpoint_sequence
            != report.local_paper_last_sequence
            or report.metrics.no_overnight_exit_attempt_count
            or report.metrics.no_overnight_exit_fill_count
            or report.metrics.local_paper_fill_count
            or report.metrics.cancel_intent_count
            or report.metrics.cancel_result_count
            or report.metrics.synthetic_fill_count
            or report.metrics.duplicate_exit_side_effect_count
            or report.metrics.wrong_horizon_liquidation_count
        ):
            raise RuntimeError(
                "OBSERVE_ONLY sealed non-qualifying or side-effect evidence"
            )
        return report
    finally:
        try:
            if composition is not None:
                composition.close()
            else:
                try:
                    if marker_journal is not None:
                        _close_if_supported(marker_journal)
                finally:
                    provider.close()
        finally:
            if artifact_directories is not None:
                artifact_directories.close()
