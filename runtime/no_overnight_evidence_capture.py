"""Operational capture seam for a real DISABLED evidence baseline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
import os
from pathlib import Path
import stat
from time import sleep
from zoneinfo import ZoneInfo

from config import twse_calendar_2026
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.no_overnight import NoOvernightPolicyConfig
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MarketDataProvider
from runtime.clock import Clock
from runtime.composition import RuntimeComposition
from runtime.ports import JournalRepository
from simulation.settings import LocalPaperSettings
from trading.no_overnight_evidence import (
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
_DirectoryFence = tuple[int, int, int, int, int, int, int]


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
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("DISABLED baseline clock must be timezone-aware")
    if value.astimezone(zone).replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("DISABLED baseline clock timezone differs from calendar")
    if value.date() != session_date or value > reviewed_open:
        raise ValueError(
            "DISABLED baseline must start on the session date no later than open"
        )


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
            local_paper_session_id=(
                LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID
            ),
        )
        artifact_directories = _prepare_sessions_directory(artifact_root)
        marker_journal = marker_journal_factory()
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
        if runtime_start_at < opened_at:
            raise ValueError(
                "DISABLED baseline clock moved backwards after atomic open"
            )
        composition = runtime_factory(
            provider=provider,
            clock=clock,
            local_paper_settings=LocalPaperSettings.v2_from_v1(
                LocalPaperSettings.defaults()
            ),
            local_paper_session_id=(
                LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID
            ),
            no_overnight_config=config,
            equity_calendar=reviewed_calendar,
        )
        closed_at = _wait_until(reviewed_close, clock=clock, wait=wait)
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
