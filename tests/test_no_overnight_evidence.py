from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from datetime import date, datetime, time

import pytest

from config import twse_calendar_2026
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from config.no_overnight import NoOvernightDeploymentManifest
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
import runtime.composition as composition_module
from trading import no_overnight_evidence as no_overnight_evidence_module
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from runtime.no_overnight_guard import no_overnight_guard_identity
from simulation.settings import LocalPaperSettings
from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from trading.no_overnight_evidence import (
    NoOvernightCampaignReport,
    NoOvernightCampaignStatus,
    NoOvernightDrillEvidence,
    NoOvernightDrillKind,
    NoOvernightDrillStatus,
    NoOvernightEvidenceMetrics,
    NoOvernightEvidenceStage,
    NoOvernightEvidenceStatus,
    NoOvernightEvidenceWindowSpec,
    NoOvernightParameterReviewPhase,
    NoOvernightParameterReviewStatus,
    NoOvernightParameterReview,
    NoOvernightQualificationStatus,
    build_no_overnight_campaign_report,
    build_no_overnight_parameter_review,
    build_no_overnight_session_report,
    close_no_overnight_evidence_window,
    open_no_overnight_evidence_window,
    read_no_overnight_campaign_bundle,
    read_no_overnight_campaign_report,
    read_no_overnight_drill_evidence,
    read_no_overnight_parameter_review,
    read_no_overnight_session_report,
    write_no_overnight_campaign_report,
    write_no_overnight_drill_evidence,
    write_no_overnight_parameter_review,
    write_no_overnight_session_report,
)
from trading.journal import JournalRecord, JournalSession


SESSION_DATE = date(2026, 8, 24)
TAIPEI_OPEN = datetime.fromisoformat("2026-08-24T09:00:00+08:00")
TAIPEI_CLOSE = datetime.fromisoformat("2026-08-24T13:30:00+08:00")


def _write_campaign_bundle(
    root,
    *,
    reports,
    parameter_review,
    drills,
    campaign,
) -> None:
    session_directory = root / "sessions"
    drill_directory = root / "drills"
    session_directory.mkdir(parents=True)
    drill_directory.mkdir()
    suffix_by_stage = {
        NoOvernightEvidenceStage.DISABLED_BASELINE: "disabled",
        NoOvernightEvidenceStage.OBSERVE_ONLY: "observe-only",
        NoOvernightEvidenceStage.SUPERVISED_ENFORCING: (
            "supervised-enforcing"
        ),
    }
    for report in reports:
        filename = (
            f"{report.observation.session_date.isoformat()}-"
            f"{suffix_by_stage[report.observation.stage]}.json"
        )
        write_no_overnight_session_report(
            session_directory / filename,
            report,
        )
    for drill in drills:
        filename = f"{drill.kind.value.lower().replace('_', '-')}.json"
        write_no_overnight_drill_evidence(drill_directory / filename, drill)
    if parameter_review is not None:
        write_no_overnight_parameter_review(
            root / "parameter_review.json",
            parameter_review,
        )
        (root / "review_notes.sha256").write_text(
            f"{parameter_review.review_note_digest}\n"
        )
    write_no_overnight_campaign_report(
        root / "campaign_report.json",
        campaign,
    )


def _session_times(session_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.fromisoformat(f"{session_date.isoformat()}T09:00:00+08:00"),
        datetime.fromisoformat(f"{session_date.isoformat()}T13:30:00+08:00"),
    )


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class HealthyGuard:
    guard_identity = no_overnight_guard_identity(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )

    def __init__(self) -> None:
        self.owned = False
        self.closed = False

    def acquire(self) -> None:
        self.owned = True

    def is_owned_and_healthy(self) -> bool:
        return self.owned and not self.closed

    def execute_if_owned(self, operation):
        if not self.is_owned_and_healthy():
            raise ValueError("guard is not healthy")
        return operation()

    def close(self) -> None:
        self.closed = True
        self.owned = False


def _config(mode: NoOvernightMode) -> NoOvernightPolicyConfig:
    if mode is NoOvernightMode.DISABLED:
        return NoOvernightPolicyConfig.disabled(
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        )
    return NoOvernightPolicyConfig(
        mode=mode,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        policy_version=(
            "observe-only-v1"
            if mode is NoOvernightMode.OBSERVE_ONLY
            else "enforcing-v1"
        ),
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


def _journal_for(
    mode: NoOvernightMode,
    *,
    session_date: date = SESSION_DATE,
    opened_at: datetime | None = None,
):
    journal = InMemoryJournalRepository()
    session_open, session_close = _session_times(session_date)
    clock = MutableClock(session_open)
    provider = MockProvider()
    config = _config(mode)
    provider_identity = f"{type(provider).__module__}.{type(provider).__qualname__}"
    stage = {
        NoOvernightMode.DISABLED: NoOvernightEvidenceStage.DISABLED_BASELINE,
        NoOvernightMode.OBSERVE_ONLY: NoOvernightEvidenceStage.OBSERVE_ONLY,
    }[mode]
    spec, opened = _open_window(
        journal=journal,
        config=config,
        provider_identity=provider_identity,
        stage=stage,
        session_date=session_date,
        opened_at=opened_at,
    )
    composition = RuntimeComposition.create(
        provider,
        journal=journal,
        clock=clock,
        local_paper_settings=LocalPaperSettings.v2_from_v1(
            LocalPaperSettings.defaults()
        ),
        local_paper_session_id=(
            LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID
        ),
        no_overnight_config=config,
    )
    if mode is NoOvernightMode.OBSERVE_ONLY:
        clock.value = session_close
        composition.no_overnight_controller.run_once(clock.value)
    composition.close()
    observation = close_no_overnight_evidence_window(
        journal=journal,
        spec=spec,
        opened=opened,
        closed_at=session_close,
    )
    return journal, config, provider_identity, observation


def _open_window(
    *,
    journal: InMemoryJournalRepository,
    config: NoOvernightPolicyConfig,
    provider_identity: str,
    stage: NoOvernightEvidenceStage,
    deployment_manifest_digest: str | None = None,
    guard_identity: str | None = None,
    session_date: date = SESSION_DATE,
    opened_at: datetime | None = None,
):
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    session_open, session_close = _session_times(session_date)
    spec = NoOvernightEvidenceWindowSpec(
        campaign_id="no-overnight-campaign-2026-08-v1",
        stage=stage,
        session_date=session_date,
        account_scope_id=config.account_scope_id,
        policy_family_id=config.policy_family_id,
        policy_version=config.policy_version,
        policy_digest=config.policy_digest,
        calendar_schema_version=calendar.schema_version,
        calendar_digest=calendar.source_digest,
        timezone=config.timezone,
        reviewed_open=session_open,
        reviewed_close=session_close,
        code_identity="067f0131f1c2ac80e16249a574b3808f6fb4c80a",
        expected_provider_identity=provider_identity,
        local_paper_session_id=(
            LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID
        ),
        expected_deployment_manifest_digest=deployment_manifest_digest,
        expected_guard_identity=guard_identity,
    )
    return (
        spec,
        open_no_overnight_evidence_window(
            journal=journal,
            spec=spec,
            opened_at=opened_at or session_open,
        ),
    )


def _enforcing_journal(monkeypatch, *, session_date: date = SESSION_DATE):
    journal = InMemoryJournalRepository()
    guard = HealthyGuard()
    session_open, session_close = _session_times(session_date)
    clock = MutableClock(session_open)
    provider = MockProvider()
    config = _config(NoOvernightMode.ENFORCING)
    manifest = NoOvernightDeploymentManifest(
        source="pytest-reviewed-single-worker",
        process_count=1,
        workers_per_process=1,
    )
    provider_identity = f"{type(provider).__module__}.{type(provider).__qualname__}"
    spec, opened = _open_window(
        journal=journal,
        config=config,
        provider_identity=provider_identity,
        stage=NoOvernightEvidenceStage.SUPERVISED_ENFORCING,
        deployment_manifest_digest=manifest.digest,
        guard_identity=guard.guard_identity,
        session_date=session_date,
    )
    monkeypatch.setattr(
        composition_module,
        "build_journal_repository",
        lambda _config: journal,
    )
    monkeypatch.setattr(
        composition_module.PostgresNoOvernightControllerGuard,
        "connect",
        lambda **_kwargs: guard,
    )
    composition = RuntimeComposition.create(
        provider,
        clock=clock,
        local_paper_settings=LocalPaperSettings.v2_from_v1(
            LocalPaperSettings.defaults()
        ),
        local_paper_session_id=(
            LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID
        ),
        persistence_config=TradingPersistenceConfig(
            backend=TradingJournalBackend.POSTGRESQL,
            database_url="postgresql://unit-test.invalid/no_overnight_g6",
        ),
        no_overnight_config=config,
        no_overnight_deployment_manifest=manifest,
    )
    assert composition.no_overnight_worker is not None
    composition.no_overnight_worker.stop()
    clock.value = session_close
    composition.no_overnight_controller.run_once(clock.value)
    composition.close()
    observation = close_no_overnight_evidence_window(
        journal=journal,
        spec=spec,
        opened=opened,
        closed_at=session_close,
    )
    return (
        journal,
        config,
        provider_identity,
        manifest,
        guard.guard_identity,
        observation,
    )


def test_disabled_baseline_is_complete_but_never_qualifies_rollout() -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.DISABLED
    )

    report = build_no_overnight_session_report(
        journal=journal,
        observation=observation,
    )

    assert report.status is NoOvernightEvidenceStatus.COMPLETE
    assert report.qualification is NoOvernightQualificationStatus.NOT_APPLICABLE
    assert report.no_overnight_session_id is None
    assert report.metrics.no_overnight_exit_attempt_count == 0
    assert report.metrics.synthetic_fill_count == 0
    assert report.postgres_destructive_uat == "WAIVED_NOT_RUN_NOT_PASSED"


def test_observe_only_full_session_replays_to_zero_side_effect_evidence() -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY
    )

    report = build_no_overnight_session_report(
        journal=journal,
        observation=observation,
    )

    assert report.status is NoOvernightEvidenceStatus.COMPLETE
    assert report.qualification is NoOvernightQualificationStatus.QUALIFIED
    assert report.terminal_state == "CONFIRMED_FLAT"
    assert report.result_status == "CURRENT"
    assert report.flat_proof_mode == "NEVER_EXPOSED"
    assert report.metrics.no_overnight_exit_attempt_count == 0
    assert report.metrics.no_overnight_exit_fill_count == 0
    assert report.metrics.duplicate_exit_side_effect_count == 0
    assert report.metrics.wrong_horizon_liquidation_count == 0
    assert report.no_overnight_checkpoint_sequence == (
        report.no_overnight_last_sequence
    )
    assert report.local_paper_checkpoint_sequence == report.local_paper_last_sequence


def test_incomplete_session_window_cannot_qualify() -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY,
        opened_at=datetime.fromisoformat("2026-08-24T09:00:00.000001+08:00"),
    )

    report = build_no_overnight_session_report(
        journal=journal,
        observation=observation,
    )

    assert report.status is NoOvernightEvidenceStatus.INCOMPLETE
    assert report.qualification is NoOvernightQualificationStatus.NOT_QUALIFIED
    assert "SESSION_OPEN_NOT_COVERED" in report.reason_codes


def test_evidence_window_observation_cannot_be_forged_after_capture() -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY
    )

    with pytest.raises(ValueError, match="session metadata"):
        build_no_overnight_session_report(
            journal=journal,
            observation=replace(
                observation,
                observed_from=observation.observed_from.replace(microsecond=1),
            ),
        )
    with pytest.raises(ValueError, match="close marker"):
        build_no_overnight_session_report(
            journal=journal,
            observation=replace(
                observation,
                window_close_record_fingerprint="f" * 64,
            ),
        )


def test_execution_fact_appended_after_window_close_fails_closed() -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY
    )
    journal.append(
        JournalRecord(
            record_id="reviewer-late-execution-fact",
            session_id=LOCAL_PAPER_NO_OVERNIGHT_EVIDENCE_SESSION_ID,
            kind="reviewer_late_execution_fact.v1",
            occurred_at=observation.observed_through,
            payload={"reason": "append-order-regression"},
        )
    )

    with pytest.raises(ValueError, match="append order"):
        build_no_overnight_session_report(
            journal=journal,
            observation=observation,
        )


def test_stale_no_overnight_checkpoint_fails_closed() -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY
    )
    session_id = f"no-overnight-v1-{SESSION_DATE.isoformat()}"
    checkpoint = journal.latest_checkpoint(session_id, "no_overnight.v1")
    assert checkpoint is not None
    journal._checkpoints[(session_id, "no_overnight.v1")] = replace(
        checkpoint,
        journal_sequence=checkpoint.journal_sequence - 1,
    )

    with pytest.raises(ValueError, match="checkpoint"):
        build_no_overnight_session_report(
            journal=journal,
            observation=observation,
        )


def test_report_artifact_is_canonical_idempotent_and_strict(tmp_path) -> None:
    journal, _config_value, _provider_identity, observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY
    )
    report = build_no_overnight_session_report(
        journal=journal,
        observation=observation,
    )
    path = tmp_path / "no_overnight_session_evidence.json"

    assert write_no_overnight_session_report(path, report) == path
    assert write_no_overnight_session_report(path, report) == path
    assert read_no_overnight_session_report(path) == report
    raw = json.loads(path.read_text())
    raw["unexpected"] = True
    path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="fields"):
        read_no_overnight_session_report(path)


def test_frozen_parameter_review_requires_all_samples_and_stages(tmp_path) -> None:
    zero_metrics = NoOvernightEvidenceMetrics(
        **{
            field_name: 0
            for field_name in NoOvernightEvidenceMetrics.__dataclass_fields__
        }
    )

    with pytest.raises(ValueError, match="all campaign stages"):
        NoOvernightParameterReview(
            campaign_id="forged-review",
            account_scope_id="scope-v1",
            policy_family_id="family-v1",
            frozen_policy_version="policy-v1",
            frozen_policy_digest="a" * 64,
            frozen_deployment_manifest_digest="b" * 64,
            code_identity="code-v1",
            reviewed_at=datetime.fromisoformat("2026-08-26T13:50:00+08:00"),
            reviewed_by="reviewer",
            review_note_digest="c" * 64,
            false_positive_review_complete=True,
            status=NoOvernightParameterReviewStatus.FROZEN,
            reason_codes=(),
            session_report_digests=("d" * 64,),
            metrics=zero_metrics,
        )

    forged_review = NoOvernightParameterReview(
        campaign_id="forged-review",
        account_scope_id="scope-v1",
        policy_family_id="family-v1",
        frozen_policy_version="policy-v1",
        frozen_policy_digest="a" * 64,
        frozen_deployment_manifest_digest="b" * 64,
        code_identity="code-v1",
        reviewed_at=datetime.fromisoformat("2026-08-26T13:50:00+08:00"),
        reviewed_by="reviewer",
        review_note_digest="c" * 64,
        false_positive_review_complete=True,
        status=NoOvernightParameterReviewStatus.FROZEN,
        reason_codes=(),
        session_report_digests=("d" * 64, "e" * 64, "f" * 64),
        metrics=zero_metrics,
    )
    path = tmp_path / "forged_parameter_review.json"
    write_no_overnight_parameter_review(path, forged_review)

    with pytest.raises(ValueError, match="evidence is insufficient"):
        read_no_overnight_parameter_review(path)


def test_strict_campaign_reader_rejects_semantically_impossible_ready(
    tmp_path,
) -> None:
    report = NoOvernightCampaignReport(
        campaign_id="forged-ready",
        account_scope_id="scope-v1",
        policy_family_id="family-v1",
        frozen_policy_version="policy-v1",
        frozen_policy_digest="a" * 64,
        frozen_deployment_manifest_digest="b" * 64,
        code_identity="code-v1",
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
        status=NoOvernightCampaignStatus.READY_FOR_INDEPENDENT_REVIEW,
        reason_codes=(),
        session_report_digests=("c" * 64,),
        drill_evidence_digests=(),
        parameter_review_digest="d" * 64,
    )
    path = tmp_path / "forged_campaign.json"
    write_no_overnight_campaign_report(path, report)

    with pytest.raises(ValueError, match="stage evidence"):
        read_no_overnight_campaign_report(path)


def test_supervised_enforcing_report_requires_postgres_manifest_and_guard(
    monkeypatch,
) -> None:
    journal, _config_value, _provider_identity, _manifest, _guard, observation = (
        _enforcing_journal(monkeypatch)
    )

    report = build_no_overnight_session_report(
        journal=journal,
        observation=observation,
    )

    assert report.status is NoOvernightEvidenceStatus.COMPLETE
    assert report.qualification is NoOvernightQualificationStatus.QUALIFIED
    assert report.terminal_state == "CONFIRMED_FLAT"
    assert report.postgres_destructive_uat == "WAIVED_NOT_RUN_NOT_PASSED"


def test_campaign_requires_all_stages_and_three_passed_drills(
    monkeypatch,
    tmp_path,
) -> None:
    baseline_date = date(2026, 8, 24)
    observe_date = date(2026, 8, 25)
    enforcing_date = date(2026, 8, 26)
    baseline_journal, baseline_config, provider_identity, baseline_observation = _journal_for(
        NoOvernightMode.DISABLED,
        session_date=baseline_date,
    )
    observe_journal, observe_config, _, observe_observation = _journal_for(
        NoOvernightMode.OBSERVE_ONLY,
        session_date=observe_date,
    )
    enforcing_journal, enforcing_config, _, manifest, guard_identity, enforcing_observation = (
        _enforcing_journal(monkeypatch, session_date=enforcing_date)
    )
    reports = (
        build_no_overnight_session_report(
            journal=baseline_journal,
            observation=baseline_observation,
        ),
        build_no_overnight_session_report(
            journal=observe_journal,
            observation=observe_observation,
        ),
        build_no_overnight_session_report(
            journal=enforcing_journal,
            observation=enforcing_observation,
        ),
    )
    missing_drills = build_no_overnight_campaign_report(
        reports=reports,
        drills=(),
        parameter_review=None,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )

    assert missing_drills.status is NoOvernightCampaignStatus.INCOMPLETE
    assert set(missing_drills.reason_codes) == {
        "BREACH_DRILL_MISSING",
        "DUPLICATE_PROCESS_DRILL_MISSING",
        "PARAMETER_REVIEW_MISSING",
        "RESTART_RECOVERY_DRILL_MISSING",
    }
    drills = tuple(
        NoOvernightDrillEvidence(
            campaign_id=reports[0].observation.campaign_id,
            kind=kind,
            status=NoOvernightDrillStatus.PASSED,
            observed_at=datetime.fromisoformat("2026-08-26T13:45:00+08:00"),
            evidence_digest=f"{index:x}" * 64,
            account_scope_id=enforcing_config.account_scope_id,
            policy_family_id=enforcing_config.policy_family_id,
            policy_digest=enforcing_config.policy_digest,
            deployment_manifest_digest=manifest.digest,
        )
        for index, kind in enumerate(NoOvernightDrillKind, start=1)
    )
    insufficient_review = build_no_overnight_parameter_review(
        reports=reports[:2],
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        reviewed_at=datetime.fromisoformat("2026-08-25T13:50:00+08:00"),
        reviewed_by="supervised-g6-operator",
        review_note_digest="a" * 64,
        false_positive_review_complete=True,
    )
    assert (
        insufficient_review.status
        is NoOvernightParameterReviewStatus.INSUFFICIENT_EVIDENCE
    )
    assert "PARTIAL_FILL_SAMPLE_MISSING" in insufficient_review.reason_codes
    forged_review = replace(
        insufficient_review,
        status=NoOvernightParameterReviewStatus.FROZEN,
        reason_codes=(),
    )
    rejected_forgery = build_no_overnight_campaign_report(
        reports=reports,
        drills=drills,
        parameter_review=forged_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )
    assert rejected_forgery.status is NoOvernightCampaignStatus.INCOMPLETE
    assert (
        "PARAMETER_REVIEW_REQUIRED_EVIDENCE_MISSING"
        in rejected_forgery.reason_codes
    )
    sampled_reports = (
        reports[0],
        replace(
            reports[1],
            metrics=NoOvernightEvidenceMetrics(
                local_paper_fill_count=2,
                managed_entry_opportunity_count=1,
                partial_fill_order_count=1,
                cancel_intent_count=1,
                cancel_result_count=1,
                cancel_latency_sample_count=1,
                max_cancel_latency_microseconds=200_000,
                no_overnight_exit_attempt_count=2,
                no_overnight_exit_retry_count=1,
                no_overnight_exit_fill_count=1,
                exit_fill_latency_sample_count=1,
                max_exit_fill_latency_microseconds=500_000,
                exit_retry_latency_sample_count=1,
                max_exit_retry_latency_microseconds=10_000_000,
                executable_book_ready_count=2,
                executable_book_unavailable_count=0,
                synthetic_fill_count=0,
                duplicate_exit_side_effect_count=0,
                wrong_horizon_liquidation_count=0,
            ),
        ),
        reports[2],
    )
    parameter_review = build_no_overnight_parameter_review(
        reports=sampled_reports[:2],
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        reviewed_at=datetime.fromisoformat("2026-08-25T13:50:00+08:00"),
        reviewed_by="supervised-g6-operator",
        review_note_digest="a" * 64,
        false_positive_review_complete=True,
    )
    assert parameter_review.status is NoOvernightParameterReviewStatus.FROZEN
    assert (
        parameter_review.review_phase
        is NoOvernightParameterReviewPhase.PRE_ENFORCEMENT_APPROVAL
    )
    assert parameter_review.metrics.managed_entry_opportunity_count == 1

    baseline_journal.start_session(
        JournalSession(
            session_id="no-overnight-v1-2026-08-24",
            started_at=datetime.fromisoformat("2026-08-24T09:00:00+08:00"),
            mode="NO_OVERNIGHT_DISABLED_SHOULD_NOT_EXIST",
            metadata={"unexpected_controller_session": True},
        )
    )
    unsafe_baseline = build_no_overnight_session_report(
        journal=baseline_journal,
        observation=baseline_observation,
    )
    assert unsafe_baseline.status is NoOvernightEvidenceStatus.COMPLETE
    assert (
        unsafe_baseline.qualification
        is NoOvernightQualificationStatus.NOT_APPLICABLE
    )
    assert (
        "DISABLED_CONTROLLER_SESSION_PRESENT"
        in unsafe_baseline.reason_codes
    )
    disabled_safety_reports = (
        unsafe_baseline,
        sampled_reports[1],
        sampled_reports[2],
    )
    disabled_safety_review = build_no_overnight_parameter_review(
        reports=disabled_safety_reports[:2],
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        reviewed_at=datetime.fromisoformat("2026-08-25T13:50:00+08:00"),
        reviewed_by="supervised-g6-operator",
        review_note_digest="d" * 64,
        false_positive_review_complete=True,
    )
    assert (
        disabled_safety_review.status
        is NoOvernightParameterReviewStatus.INSUFFICIENT_EVIDENCE
    )
    assert (
        "DISABLED_BASELINE_SAFETY_FINDING"
        in disabled_safety_review.reason_codes
    )
    forged_disabled_safety_review = replace(
        disabled_safety_review,
        status=NoOvernightParameterReviewStatus.FROZEN,
        reason_codes=(),
    )
    disabled_safety_campaign = build_no_overnight_campaign_report(
        reports=disabled_safety_reports,
        drills=drills,
        parameter_review=forged_disabled_safety_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )
    assert (
        disabled_safety_campaign.status
        is NoOvernightCampaignStatus.INCOMPLETE
    )
    assert (
        "DISABLED_BASELINE_SAFETY_FINDING"
        in disabled_safety_campaign.reason_codes
    )
    disabled_safety_root = tmp_path / "disabled-safety"
    _write_campaign_bundle(
        disabled_safety_root,
        reports=disabled_safety_reports,
        parameter_review=forged_disabled_safety_review,
        drills=drills,
        campaign=disabled_safety_campaign,
    )
    assert (
        read_no_overnight_campaign_bundle(disabled_safety_root)
        == disabled_safety_campaign
    )

    post_uat_review = build_no_overnight_parameter_review(
        reports=sampled_reports,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        reviewed_at=datetime.fromisoformat("2026-08-26T13:50:00+08:00"),
        reviewed_by="supervised-g6-operator",
        review_note_digest="b" * 64,
        false_positive_review_complete=True,
    )
    assert post_uat_review.status is NoOvernightParameterReviewStatus.FROZEN
    assert (
        post_uat_review.review_phase
        is NoOvernightParameterReviewPhase.POST_UAT_VALIDATION
    )
    post_uat_campaign = build_no_overnight_campaign_report(
        reports=sampled_reports,
        drills=drills,
        parameter_review=post_uat_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )
    assert post_uat_campaign.status is NoOvernightCampaignStatus.INCOMPLETE
    assert "PARAMETER_REVIEW_PHASE_INVALID" in post_uat_campaign.reason_codes

    unsafe_reports = (
        sampled_reports[0],
        replace(
            sampled_reports[1],
            metrics=replace(
                sampled_reports[1].metrics,
                synthetic_fill_count=1,
            ),
        ),
        sampled_reports[2],
    )
    unsafe_review = build_no_overnight_parameter_review(
        reports=unsafe_reports[:2],
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        reviewed_at=datetime.fromisoformat("2026-08-25T13:50:00+08:00"),
        reviewed_by="supervised-g6-operator",
        review_note_digest="b" * 64,
        false_positive_review_complete=True,
    )
    assert (
        unsafe_review.status
        is NoOvernightParameterReviewStatus.INSUFFICIENT_EVIDENCE
    )
    assert "ZERO_SAFETY_METRIC_VIOLATED" in unsafe_review.reason_codes

    early_parameter_review = replace(
        parameter_review,
        reviewed_at=datetime.fromisoformat("2026-08-25T13:30:00+08:00"),
    )
    early_review_campaign = build_no_overnight_campaign_report(
        reports=sampled_reports,
        drills=drills,
        parameter_review=early_parameter_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )
    assert early_review_campaign.status is NoOvernightCampaignStatus.INCOMPLETE
    assert (
        "PARAMETER_REVIEW_CAUSAL_ORDER_INVALID"
        in early_review_campaign.reason_codes
    )

    late_parameter_review = replace(
        parameter_review,
        reviewed_at=datetime.fromisoformat("2026-08-26T09:00:00+08:00"),
    )
    late_review_campaign = build_no_overnight_campaign_report(
        reports=sampled_reports,
        drills=drills,
        parameter_review=late_parameter_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )
    assert late_review_campaign.status is NoOvernightCampaignStatus.INCOMPLETE
    assert (
        "PARAMETER_REVIEW_CAUSAL_ORDER_INVALID"
        in late_review_campaign.reason_codes
    )

    early_drills = tuple(
        replace(
            drill,
            observed_at=datetime.fromisoformat("2026-08-26T13:30:00+08:00"),
        )
        for drill in drills
    )
    early_drill_campaign = build_no_overnight_campaign_report(
        reports=sampled_reports,
        drills=early_drills,
        parameter_review=parameter_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )
    assert early_drill_campaign.status is NoOvernightCampaignStatus.INCOMPLETE
    assert "DRILL_CAUSAL_ORDER_INVALID" in early_drill_campaign.reason_codes

    ready = build_no_overnight_campaign_report(
        reports=sampled_reports,
        drills=drills,
        parameter_review=parameter_review,
        frozen_policy_version=enforcing_config.policy_version,
        frozen_policy_digest=enforcing_config.policy_digest,
        frozen_deployment_manifest_digest=manifest.digest,
        finalized_at=datetime.fromisoformat("2026-08-26T14:00:00+08:00"),
    )

    assert ready.status is NoOvernightCampaignStatus.READY_FOR_INDEPENDENT_REVIEW
    assert ready.reason_codes == ()
    assert ready.independent_review_required is True
    assert ready.unattended_local_paper_allowed is False
    assert ready.broker_live_ready is False
    assert ready.postgres_destructive_uat == "WAIVED_NOT_RUN_NOT_PASSED"

    valid_root = tmp_path / "valid"
    _write_campaign_bundle(
        valid_root,
        reports=sampled_reports,
        parameter_review=parameter_review,
        drills=drills,
        campaign=ready,
    )
    parameter_path = valid_root / "parameter_review.json"
    campaign_path = valid_root / "campaign_report.json"
    drill_path = valid_root / "drills" / "restart-recovery.json"
    assert read_no_overnight_parameter_review(parameter_path) == parameter_review
    assert read_no_overnight_campaign_bundle(valid_root) == ready
    assert read_no_overnight_campaign_report(campaign_path) == ready
    assert read_no_overnight_drill_evidence(drill_path) == drills[0]

    original_inventory = no_overnight_evidence_module._directory_entry_modes
    injected = False

    def inventory_with_concurrent_extra(directory, label):
        nonlocal injected
        entries = original_inventory(directory, label)
        if not injected and directory == valid_root:
            injected = True
            (valid_root / "unexpected-after-inventory.json").write_text("{}\n")
        return entries

    with monkeypatch.context() as inventory_patch:
        inventory_patch.setattr(
            no_overnight_evidence_module,
            "_directory_entry_modes",
            inventory_with_concurrent_extra,
        )
        with pytest.raises(ValueError, match="unexpected root entries"):
            read_no_overnight_campaign_bundle(valid_root)
    (valid_root / "unexpected-after-inventory.json").unlink()

    post_root = tmp_path / "post-review-substitution"
    _write_campaign_bundle(
        post_root,
        reports=sampled_reports,
        parameter_review=post_uat_review,
        drills=drills,
        campaign=replace(
            ready,
            parameter_review_digest=post_uat_review.review_digest,
        ),
    )
    with pytest.raises(ValueError, match="does not reproduce"):
        read_no_overnight_campaign_bundle(post_root)

    late_root = tmp_path / "late-review-substitution"
    _write_campaign_bundle(
        late_root,
        reports=sampled_reports,
        parameter_review=late_parameter_review,
        drills=drills,
        campaign=replace(
            ready,
            parameter_review_digest=late_parameter_review.review_digest,
        ),
    )
    with pytest.raises(ValueError, match="does not reproduce"):
        read_no_overnight_campaign_bundle(late_root)

    early_drill_root = tmp_path / "early-drill-substitution"
    _write_campaign_bundle(
        early_drill_root,
        reports=sampled_reports,
        parameter_review=parameter_review,
        drills=early_drills,
        campaign=replace(
            ready,
            drill_evidence_digests=tuple(
                sorted(drill.drill_digest for drill in early_drills)
            ),
            drill_kind_digests=tuple(
                sorted(
                    (drill.kind.value, drill.drill_digest)
                    for drill in early_drills
                )
            ),
        ),
    )
    with pytest.raises(ValueError, match="does not reproduce"):
        read_no_overnight_campaign_bundle(early_drill_root)

    linked_root = tmp_path / "linked-bundle"
    linked_root.symlink_to(valid_root, target_is_directory=True)
    with pytest.raises(ValueError, match="parent path"):
        read_no_overnight_campaign_bundle(linked_root)

    raw_campaign = json.loads(campaign_path.read_text())
    raw_campaign["unattended_local_paper_allowed"] = True
    campaign_path.write_text(json.dumps(raw_campaign))
    with pytest.raises(ValueError, match="unattended Local Paper"):
        read_no_overnight_campaign_report(campaign_path)


def test_artifact_io_rejects_leaf_and_parent_symlinks(tmp_path) -> None:
    drill = NoOvernightDrillEvidence(
        campaign_id="symlink-regression",
        kind=NoOvernightDrillKind.BREACH,
        status=NoOvernightDrillStatus.PASSED,
        observed_at=datetime.fromisoformat("2026-08-26T13:45:00+08:00"),
        evidence_digest="a" * 64,
        account_scope_id="scope-v1",
        policy_family_id="family-v1",
        policy_digest="b" * 64,
        deployment_manifest_digest="c" * 64,
    )
    target = tmp_path / "target.json"
    link = tmp_path / "linked.json"
    write_no_overnight_drill_evidence(target, drill)
    link.symlink_to(target)

    with pytest.raises(ValueError, match="unsafe"):
        read_no_overnight_drill_evidence(link)
    with pytest.raises(ValueError, match="unsafe"):
        write_no_overnight_drill_evidence(link, drill)

    real_directory = tmp_path / "real"
    linked_directory = tmp_path / "linked-directory"
    real_directory.mkdir()
    write_no_overnight_drill_evidence(real_directory / "drill.json", drill)
    linked_directory.symlink_to(real_directory, target_is_directory=True)
    with pytest.raises(ValueError, match="parent path"):
        read_no_overnight_drill_evidence(linked_directory / "drill.json")
    with pytest.raises(ValueError, match="parent path"):
        write_no_overnight_drill_evidence(linked_directory / "drill.json", drill)


def test_artifact_write_fsyncs_file_and_parent_directory(
    monkeypatch,
    tmp_path,
) -> None:
    drill = NoOvernightDrillEvidence(
        campaign_id="durability-regression",
        kind=NoOvernightDrillKind.RESTART_RECOVERY,
        status=NoOvernightDrillStatus.PASSED,
        observed_at=datetime.fromisoformat("2026-08-26T13:45:00+08:00"),
        evidence_digest="a" * 64,
        account_scope_id="scope-v1",
        policy_family_id="family-v1",
        policy_digest="b" * 64,
        deployment_manifest_digest="c" * 64,
    )
    synced_types: list[str] = []
    original_fsync = os.fsync

    def tracking_fsync(file_descriptor: int) -> None:
        mode = os.fstat(file_descriptor).st_mode
        synced_types.append("directory" if stat.S_ISDIR(mode) else "file")
        original_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", tracking_fsync)

    write_no_overnight_drill_evidence(tmp_path / "durable.json", drill)

    assert synced_types == ["file", "directory"]
