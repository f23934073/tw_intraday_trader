"""Run one complete data-only PR-TM-012C1 Shadow session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.qualification_capture import (
    HistoricalQualificationCapture,
    QualificationCaptureConfig,
    require_qualification_flags_off,
)
from market_data.shioaji_momentum_stream import ShioajiMomentumStream
from runtime.clock import SystemClock
from runtime.trade_management_c1_session import (
    C1SessionStatus,
    TradeManagementC1SessionCoordinator,
)
from runtime.trade_management_artifact_io import (
    require_complete_artifact_pair,
    write_json_digest_pair_exclusive,
)
from runtime.trade_management_live_capture import (
    LiveShadowCaptureConfig,
    LiveShadowProviderIdentity,
)
from runtime.trade_management_premarket import (
    AUTHORITATIVE_EVIDENCE_TABLES,
    DataOnlyProviderPreflight,
    PostgresReadOnlyPreflight,
    ShadowRehearsalEvidence,
)
from runtime.trade_management_input_loading import (
    parse_risk_snapshot_document,
    parse_shadow_policy,
    require_risk_snapshot_capture_window,
)
from runtime.trade_management_input_review import (
    REVIEW_PACKET_VERSION,
    SOURCE_FILENAMES,
    canonical_promotion_lock_path,
    load_digest_bound_json,
    require_review_packet_path,
    require_approval_fields,
    sha256_bytes,
)
from runtime.trade_management_runtime_identity import runtime_code_identity
from trading.live_entry_thesis_draft import (
    LiveThesisDraftPolicy,
    LiveTradeThesisDraftBuilder,
)
from trading.postgres_journal import PostgresJournalRepository
from trading.trade_management_serialization import (
    deserialize_live_entry_decision,
    deserialize_trade_thesis_draft,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_INPUTS_ROOT = (
    PROJECT_ROOT / "research" / "trade_management_shadow" / "session_inputs"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-artifact", type=Path, required=True)
    parser.add_argument("--entry-decision", type=Path, required=True)
    parser.add_argument("--thesis-draft", type=Path, required=True)
    parser.add_argument("--shadow-policy", type=Path, required=True)
    parser.add_argument("--risk-snapshot", type=Path, required=True)
    parser.add_argument("--input-approval", type=Path, required=True)
    parser.add_argument("--connection-session-id", required=True)
    parser.add_argument(
        "--records-root",
        type=Path,
        default=Path("records/trade_management_shadow"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("A", "B"), default="A")
    parser.add_argument("--subscribe-ack-timeout-seconds", type=int, default=30)
    parser.add_argument("--preopen-wait-timeout-seconds", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    now = datetime.now(TAIPEI)
    try:
        require_qualification_flags_off()
        inputs = _load_and_verify_inputs(args, now=now)
        fill_dsn, evidence_dsn = _journal_dsns()
    except Exception as error:
        _print_result("BLOCKED", (f"{type(error).__name__}:{error}",))
        return 2

    fill_journal = None
    evidence_journal = None
    stream = None
    try:
        fill_journal = _postgres_journal(fill_dsn, read_only=True)
        evidence_journal = _postgres_journal(evidence_dsn, read_only=False)
        stream = ShioajiMomentumStream.connect_from_env(
            session_id=args.connection_session_id
        )
        manifest = inputs["manifest"]
        if stream.environment_identity != manifest["provider_identity"]:
            raise RuntimeError("C1_PROVIDER_IDENTITY_MISMATCH")
        provider_parts = stream.environment_identity.split(":")
        provider = LiveShadowProviderIdentity(
            provider=provider_parts[0],
            sdk_version=provider_parts[1],
            simulation=provider_parts[2] == "simulation=true",
            connection_session_id=args.connection_session_id,
        )
        capture_config = LiveShadowCaptureConfig(
            session_id=str(manifest["session_id"]),
            symbol=str(manifest["symbol"]),
            provider=provider,
            scheduled_open=datetime.fromisoformat(str(manifest["scheduled_open"])),
            scheduled_close=datetime.fromisoformat(str(manifest["scheduled_close"])),
            subscribe_ack_timeout_seconds=args.subscribe_ack_timeout_seconds,
        )
        clock = SystemClock()
        baseline_risk = inputs["risk_snapshot"]
        coordinator = TradeManagementC1SessionCoordinator(
            decision=inputs["decision"],
            draft_policy=inputs["draft_policy"],
            fill_journal=fill_journal,
            evidence_journal=evidence_journal,
            shadow_policy=inputs["shadow_policy"],
            risk_snapshot_provider=lambda event, result: replace(
                baseline_risk,
                data_health_state=result.health_after.value,
                market_open=(
                    capture_config.scheduled_open
                    <= event.event_at
                    <= capture_config.scheduled_close
                ),
            ),
            capture_config=capture_config,
            clock=clock,
        )
        duration = int(
            (capture_config.scheduled_close - capture_config.scheduled_open)
            .total_seconds()
        )
        calendar = inputs["calendar"]
        capture = HistoricalQualificationCapture(
            stream,
            QualificationCaptureConfig(
                symbol=capture_config.symbol,
                session_id=capture_config.session_id,
                records_root=args.records_root,
                duration_seconds=duration,
                subscribe_ack_timeout_seconds=args.subscribe_ack_timeout_seconds,
                preopen_wait_timeout_seconds=args.preopen_wait_timeout_seconds,
                qualification_case=args.case,
            ),
            prior_session_date=calendar.previous_trading_day(
                capture_config.scheduled_open.date()
            ),
            calendar_version=(
                f"{calendar.schema_version}:{calendar.source_digest}"
            ),
            clock=clock,
            process_observer=coordinator,
        )
        evidence = coordinator.run(capture)
        artifact = {
            "artifact_type": "TradeManagementC1SessionEvidence",
            "preflight_artifact": str(args.preflight_artifact.resolve()),
            "preflight_sha256": inputs["preflight_sha256"],
            "entry_decision_artifact": str(args.entry_decision.resolve()),
            "entry_decision_sha256": inputs["source_digests"]["entry_decision"],
            "thesis_draft_artifact": str(args.thesis_draft.resolve()),
            "thesis_draft_sha256": inputs["source_digests"]["thesis_draft"],
            "shadow_policy_artifact": str(args.shadow_policy.resolve()),
            "shadow_policy_sha256": inputs["source_digests"]["shadow_policy"],
            "risk_snapshot_artifact": str(args.risk_snapshot.resolve()),
            "risk_snapshot_sha256": inputs["source_digests"]["risk_snapshot"],
            "input_approval_artifact": str(args.input_approval.resolve()),
            "input_approval_digest": inputs["input_approval"]["approval_digest"],
            "review_packet_digest": inputs["input_approval"][
                "review_packet_digest"
            ],
            "approved_attempt_id": inputs["input_approval"]["attempt_id"],
            "canonical_bundle_artifact": str(
                (args.input_approval.parent / "bundle_manifest.json").resolve()
            ),
            "canonical_bundle_digest": inputs["canonical_bundle"][
                "bundle_digest"
            ],
            "session_evidence": evidence.to_dict(),
            "session_evidence_digest": evidence.digest,
            "production_shadow_gate": "NOT_PASSED",
        }
        write_json_digest_pair_exclusive(
            args.output,
            artifact,
            evidence.digest,
        )
        _print_result(
            evidence.status.value,
            evidence.reasons,
            artifact=args.output,
            digest=evidence.digest,
        )
        return 2 if evidence.status is C1SessionStatus.BLOCKED else 0
    except Exception as error:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        _print_result("BLOCKED", (f"{type(error).__name__}:{error}",))
        return 2
    finally:
        for journal in (evidence_journal, fill_journal):
            if journal is not None:
                close = getattr(journal, "close", None)
                if close is not None:
                    close()


def _load_and_verify_inputs(args, *, now: datetime) -> dict[str, object]:
    preflight, preflight_sha256, preflight_sidecar_digest = (
        _read_preflight_artifact(args.preflight_artifact)
    )
    manifest = _mapping(preflight.get("manifest"), "manifest")
    report = _mapping(preflight.get("readiness_report"), "readiness_report")
    provider = _mapping(preflight.get("provider_preflight"), "provider_preflight")
    postgres = _mapping(preflight.get("postgres_preflight"), "postgres_preflight")
    rehearsal = _mapping(preflight.get("rehearsal"), "rehearsal")
    if report.get("status") != "READY_FOR_SESSION" or report.get("blockers") != []:
        raise RuntimeError("C0_NOT_READY_FOR_SESSION")
    if _canonical_digest(manifest) != preflight.get("manifest_digest"):
        raise RuntimeError("C0_MANIFEST_DIGEST_MISMATCH")
    if _canonical_digest(report) != preflight.get("readiness_report_digest"):
        raise RuntimeError("C0_READINESS_DIGEST_MISMATCH")
    _require_c0_component_digests(
        provider=provider,
        postgres=postgres,
        rehearsal=rehearsal,
        report=report,
    )
    if report.get("manifest_digest") != preflight.get("manifest_digest"):
        raise RuntimeError("C0_COMPONENT_DIGEST_BINDING_MISMATCH")
    if preflight_sidecar_digest != preflight.get("readiness_report_digest"):
        raise RuntimeError("C0_READINESS_SIDECAR_MISMATCH")
    if (
        manifest.get("execution_authority") is not False
        or manifest.get("execution_enabled") is not False
        or manifest.get("evidence_only") is not True
        or provider.get("subscribe_trade") is not False
        or manifest.get("provider_simulation") is not True
        or provider.get("environment_identity") != manifest.get("provider_identity")
    ):
        raise RuntimeError("C0_DATA_ONLY_AUTHORITY_MISMATCH")
    if postgres.get("evidence_scope_session_id") != manifest.get("session_id"):
        raise RuntimeError("C0_POSTGRES_SCOPE_MISMATCH")
    current_code_identity = runtime_code_identity()
    if manifest.get("code_identity") != current_code_identity:
        raise RuntimeError("C0_RUNTIME_CODE_IDENTITY_CHANGED")

    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    market_date = datetime.fromisoformat(str(manifest["scheduled_open"])).date()
    if not calendar.is_trading_day(market_date):
        raise RuntimeError("NOT_A_REVIEWED_TRADING_DAY")
    if (
        manifest.get("market_date") != market_date.isoformat()
        or manifest.get("calendar_schema_version") != calendar.schema_version
        or manifest.get("calendar_digest") != calendar.source_digest
    ):
        raise RuntimeError("C0_REVIEWED_CALENDAR_BINDING_MISMATCH")
    if market_date != now.date():
        raise RuntimeError("C0_MARKET_DATE_IS_NOT_TODAY")
    _require_canonical_input_paths(args, market_date=market_date)
    approval, source_contents, canonical_bundle = _load_and_verify_input_approval(
        args,
        market_date=market_date,
        current_code_identity=current_code_identity,
        observed_at=now,
    )
    scheduled_open = datetime.fromisoformat(str(manifest["scheduled_open"]))
    earliest_connect = scheduled_open - timedelta(
        seconds=args.preopen_wait_timeout_seconds
    )
    if now < earliest_connect or now >= scheduled_open:
        raise RuntimeError("C1_MUST_START_INSIDE_PREOPEN_CONNECTION_WINDOW")

    decision = deserialize_live_entry_decision(
        source_contents["entry_decision"].decode("utf-8")
    )
    reviewed_draft = deserialize_trade_thesis_draft(
        source_contents["thesis_draft"].decode("utf-8")
    )
    draft_policy = LiveThesisDraftPolicy(
        policy_id=reviewed_draft.expected_behavior.policy_id,
        strategy_id=reviewed_draft.strategy_id,
        strategy_version=reviewed_draft.strategy_version,
        thesis_type=reviewed_draft.thesis_type,
        thesis_version=reviewed_draft.thesis_version,
        side=reviewed_draft.side,
        expected_behavior=reviewed_draft.expected_behavior,
        invalid_conditions=reviewed_draft.invalid_conditions,
    )
    if LiveTradeThesisDraftBuilder().build(decision, draft_policy) != reviewed_draft:
        raise RuntimeError("ENTRY_DECISION_DRAFT_PARITY_MISMATCH")
    if (
        decision.session_id != manifest.get("session_id")
        or decision.symbol != manifest.get("symbol")
        or reviewed_draft.strategy_id != manifest.get("strategy_id")
        or reviewed_draft.strategy_version != manifest.get("strategy_version")
        or reviewed_draft.thesis_version != manifest.get("thesis_version")
        or args.connection_session_id != manifest.get("connection_session_id")
    ):
        raise RuntimeError("ENTRY_DECISION_C0_BINDING_MISMATCH")
    shadow_policy = parse_shadow_policy(
        source_contents["shadow_policy"],
        code_identity=str(manifest["code_identity"]),
    )
    if (
        shadow_policy.exit_policy_version != manifest.get("exit_policy_version")
        or shadow_policy.risk_policy.version != manifest.get("risk_policy_version")
        or shadow_policy.fill_model_version != manifest.get("fill_model_version")
    ):
        raise RuntimeError("SHADOW_POLICY_C0_BINDING_MISMATCH")
    risk_snapshot, risk_provenance = parse_risk_snapshot_document(
        source_contents["risk_snapshot"]
    )
    require_risk_snapshot_capture_window(
        risk_provenance,
        window_start=earliest_connect,
        window_end=scheduled_open,
        admitted_at=now,
    )
    if (
        risk_provenance.session_id != manifest.get("session_id")
        or risk_provenance.symbol != manifest.get("symbol")
        or risk_provenance.market_date != market_date
    ):
        raise RuntimeError("RISK_SNAPSHOT_C0_BINDING_MISMATCH")
    approval_binding = approval.get("binding")
    if not isinstance(approval_binding, dict) or (
        approval_binding.get("session_id") != decision.session_id
        or approval_binding.get("symbol") != decision.symbol
        or approval_binding.get("strategy_id") != reviewed_draft.strategy_id
        or approval_binding.get("strategy_version")
        != reviewed_draft.strategy_version
        or approval_binding.get("thesis_version") != reviewed_draft.thesis_version
        or approval_binding.get("exit_policy_version")
        != shadow_policy.exit_policy_version
        or approval_binding.get("risk_policy_version")
        != shadow_policy.risk_policy.version
        or approval_binding.get("fill_model_version")
        != shadow_policy.fill_model_version
        or approval_binding.get("risk_snapshot_provenance")
        != risk_provenance.to_dict()
    ):
        raise RuntimeError("INPUT_APPROVAL_DOMAIN_BINDING_MISMATCH")
    return {
        "calendar": calendar,
        "manifest": manifest,
        "decision": decision,
        "draft_policy": draft_policy,
        "shadow_policy": shadow_policy,
        "risk_snapshot": risk_snapshot,
        "input_approval": approval,
        "canonical_bundle": canonical_bundle,
        "preflight_sha256": preflight_sha256,
        "source_digests": {
            name: sha256_bytes(content)
            for name, content in source_contents.items()
        },
    }


def _require_canonical_input_paths(
    args,
    *,
    market_date: date,
    session_inputs_root: Path = SESSION_INPUTS_ROOT,
) -> None:
    canonical_root = session_inputs_root.absolute()
    promotion_lock = canonical_promotion_lock_path(canonical_root, market_date)
    if promotion_lock.exists():
        raise RuntimeError("C1_CANONICAL_PROMOTION_INCOMPLETE")
    expected_dir = canonical_root / market_date.isoformat()
    expected = {
        "entry_decision": expected_dir / "live_entry_decision.json",
        "thesis_draft": expected_dir / "trade_thesis_draft.json",
        "shadow_policy": expected_dir / "shadow_policy.json",
        "risk_snapshot": expected_dir / "risk_snapshot.json",
        "input_approval": expected_dir / "review_approval.json",
    }
    if any(
        getattr(args, name).absolute() != path
        for name, path in expected.items()
    ):
        raise RuntimeError("C1_CANONICAL_INPUT_PATH_MISMATCH")
    for path in expected.values():
        _reject_symlink_components(path, root=canonical_root)
    _reject_symlink_components(
        expected_dir / "bundle_manifest.json",
        root=canonical_root,
    )


def _load_and_verify_input_approval(
    args,
    *,
    market_date: date,
    current_code_identity: str | None = None,
    observed_at: datetime | None = None,
) -> tuple[dict[str, object], dict[str, bytes], dict[str, object]]:
    approval = load_digest_bound_json(
        args.input_approval,
        digest_field="approval_digest",
    )
    require_approval_fields(approval, observed_at=observed_at)
    code_identity = current_code_identity or runtime_code_identity()
    if (
        approval.get("market_date") != market_date.isoformat()
        or approval.get("runtime_code_identity") != code_identity
    ):
        raise RuntimeError("INPUT_APPROVAL_SESSION_BINDING_MISMATCH")
    approved_sources = approval.get("approved_sources")
    if not isinstance(approved_sources, dict) or set(approved_sources) != set(
        SOURCE_FILENAMES
    ):
        raise RuntimeError("INPUT_APPROVAL_SOURCE_SET_INVALID")
    _verify_review_packet_reference(
        approval,
        approved_sources=approved_sources,
        market_date=market_date,
        code_identity=code_identity,
    )
    source_contents = {
        name: getattr(args, name).read_bytes() for name in SOURCE_FILENAMES
    }
    for name, filename in SOURCE_FILENAMES.items():
        item = approved_sources[name]
        if (
            not isinstance(item, dict)
            or item.get("filename") != filename
            or item.get("sha256") != sha256_bytes(source_contents[name])
        ):
            raise RuntimeError("INPUT_APPROVAL_CANONICAL_DIGEST_MISMATCH")
    bundle_path = args.input_approval.parent / "bundle_manifest.json"
    bundle = load_digest_bound_json(bundle_path, digest_field="bundle_digest")
    if (
        bundle.get("artifact_type")
        != "TradeManagementShadowCanonicalInputBundle"
        or bundle.get("version")
        != "trade-management-shadow-canonical-input-bundle-v1"
        or bundle.get("market_date") != market_date.isoformat()
        or bundle.get("attempt_id") != approval.get("attempt_id")
        or bundle.get("approval_digest") != approval.get("approval_digest")
        or bundle.get("review_packet_digest")
        != approval.get("review_packet_digest")
        or bundle.get("runtime_code_identity") != code_identity
        or bundle.get("execution_authority") is not False
        or bundle.get("execution_enabled") is not False
        or bundle.get("evidence_only") is not True
        or bundle.get("production_shadow_gate") != "NOT_PASSED"
    ):
        raise RuntimeError("CANONICAL_INPUT_BUNDLE_INVALID")
    expected_digests = {
        name: approved_sources[name]["sha256"] for name in SOURCE_FILENAMES
    }
    if bundle.get("file_digests") != expected_digests:
        raise RuntimeError("CANONICAL_INPUT_BUNDLE_DIGEST_MISMATCH")
    return approval, source_contents, bundle


def _require_c0_component_digests(
    *,
    provider: Mapping[str, object],
    postgres: Mapping[str, object],
    rehearsal: Mapping[str, object],
    report: Mapping[str, object],
) -> None:
    provider_value = DataOnlyProviderPreflight(
        credential_keys_present=_string_tuple(
            provider.get("credential_keys_present"),
            "provider_preflight.credential_keys_present",
        ),
        login_succeeded=_json_bool(
            provider.get("login_succeeded"),
            "provider_preflight.login_succeeded",
        ),
        logout_succeeded=_json_bool(
            provider.get("logout_succeeded"),
            "provider_preflight.logout_succeeded",
        ),
        subscribe_trade=_json_bool(
            provider.get("subscribe_trade"),
            "provider_preflight.subscribe_trade",
        ),
        environment_identity=_optional_string(
            provider.get("environment_identity"),
            "provider_preflight.environment_identity",
        ),
        error_code=_optional_string(
            provider.get("error_code"),
            "provider_preflight.error_code",
        ),
    )
    row_counts = _mapping(
        postgres.get("evidence_row_counts"),
        "postgres_preflight.evidence_row_counts",
    )
    if set(row_counts) != set(AUTHORITATIVE_EVIDENCE_TABLES):
        raise RuntimeError("C0_COMPONENT_DIGEST_MISMATCH")
    postgres_value = PostgresReadOnlyPreflight(
        dsn_configured=_json_bool(
            postgres.get("dsn_configured"),
            "postgres_preflight.dsn_configured",
        ),
        driver_version=_optional_string(
            postgres.get("driver_version"),
            "postgres_preflight.driver_version",
        ),
        connected=_json_bool(
            postgres.get("connected"),
            "postgres_preflight.connected",
        ),
        transaction_read_only=_json_bool(
            postgres.get("transaction_read_only"),
            "postgres_preflight.transaction_read_only",
        ),
        server_major=_optional_json_int(
            postgres.get("server_major"),
            "postgres_preflight.server_major",
        ),
        table_names=_string_tuple(
            postgres.get("table_names"),
            "postgres_preflight.table_names",
        ),
        migration_versions=_string_tuple(
            postgres.get("migration_versions"),
            "postgres_preflight.migration_versions",
        ),
        evidence_row_counts=tuple(
            (
                table,
                _json_int(
                    row_counts[table],
                    f"postgres_preflight.evidence_row_counts.{table}",
                ),
            )
            for table in AUTHORITATIVE_EVIDENCE_TABLES
        ),
        evidence_scope_session_id=_json_string(
            postgres.get("evidence_scope_session_id"),
            "postgres_preflight.evidence_scope_session_id",
        ),
        error_code=_optional_string(
            postgres.get("error_code"),
            "postgres_preflight.error_code",
        ),
    )
    if rehearsal.get("source_class") != "TEST_FIXTURE_AND_HISTORICAL_REPLAY":
        raise RuntimeError("C0_COMPONENT_DIGEST_MISMATCH")
    rehearsal_value = ShadowRehearsalEvidence(
        test_targets=_string_tuple(
            rehearsal.get("test_targets"),
            "rehearsal.test_targets",
        ),
        historical_replay_verified=_json_bool(
            rehearsal.get("historical_replay_verified"),
            "rehearsal.historical_replay_verified",
        ),
        operational_composition_verified=_json_bool(
            rehearsal.get("operational_composition_verified"),
            "rehearsal.operational_composition_verified",
        ),
        journal_recovery_verified=_json_bool(
            rehearsal.get("journal_recovery_verified"),
            "rehearsal.journal_recovery_verified",
        ),
        replay_parity_matched=_json_bool(
            rehearsal.get("replay_parity_matched"),
            "rehearsal.replay_parity_matched",
        ),
        readiness_report_deterministic=_json_bool(
            rehearsal.get("readiness_report_deterministic"),
            "rehearsal.readiness_report_deterministic",
        ),
        execution_enabled=_json_bool(
            rehearsal.get("execution_enabled"),
            "rehearsal.execution_enabled",
        ),
        qualifying_real_session=_json_bool(
            rehearsal.get("qualifying_real_session"),
            "rehearsal.qualifying_real_session",
        ),
    )
    computed = (
        provider_value.digest,
        postgres_value.digest,
        rehearsal_value.digest,
    )
    claimed = (
        provider.get("digest"),
        postgres.get("digest"),
        rehearsal.get("digest"),
    )
    bound = (
        report.get("provider_preflight_digest"),
        report.get("postgres_preflight_digest"),
        report.get("rehearsal_digest"),
    )
    if claimed != computed or bound != computed:
        raise RuntimeError("C0_COMPONENT_DIGEST_MISMATCH")


def _verify_review_packet_reference(
    approval: dict[str, object],
    *,
    approved_sources: dict[str, object],
    market_date: date,
    code_identity: str,
) -> None:
    packet_path = Path(str(approval.get("review_packet_path", "")))
    require_review_packet_path(
        packet_path,
        project_root=PROJECT_ROOT,
        market_date=market_date,
        attempt_id=str(approval.get("attempt_id", "")),
    )
    packet = load_digest_bound_json(packet_path, digest_field="packet_digest")
    if (
        packet.get("artifact_type")
        != "TradeManagementShadowInputReviewPacket"
        or packet.get("version") != REVIEW_PACKET_VERSION
        or packet.get("status") != "PENDING_REVIEW"
        or packet.get("candidate_valid") is not True
        or packet.get("blockers") != []
        or packet.get("reviewed") is not False
        or packet.get("formal_c1_eligible") is not False
        or packet.get("market_date") != market_date.isoformat()
        or packet.get("attempt_id") != approval.get("attempt_id")
        or packet.get("runtime_code_identity") != code_identity
        or packet.get("packet_digest") != approval.get("review_packet_digest")
        or packet.get("binding") != approval.get("binding")
        or packet.get("execution_authority") is not False
        or packet.get("execution_enabled") is not False
        or packet.get("evidence_only") is not True
        or packet.get("production_shadow_gate") != "NOT_PASSED"
    ):
        raise RuntimeError("INPUT_APPROVAL_REVIEW_PACKET_MISMATCH")
    packet_sources = packet.get("candidate_sources")
    if not isinstance(packet_sources, dict) or set(packet_sources) != set(
        SOURCE_FILENAMES
    ):
        raise RuntimeError("INPUT_APPROVAL_REVIEW_PACKET_SOURCE_SET_INVALID")
    for name, filename in SOURCE_FILENAMES.items():
        packet_source = packet_sources[name]
        approved_source = approved_sources[name]
        if (
            not isinstance(packet_source, dict)
            or not isinstance(approved_source, dict)
            or approved_source.get("filename") != filename
            or approved_source.get("sha256") != packet_source.get("sha256")
        ):
            raise RuntimeError("INPUT_APPROVAL_REVIEW_PACKET_DIGEST_MISMATCH")


def _reject_symlink_components(path: Path, *, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise RuntimeError("C1_CANONICAL_INPUT_PATH_MISMATCH") from error
    cursor = root
    if cursor.is_symlink():
        raise RuntimeError("C1_CANONICAL_INPUT_SYMLINK_REJECTED")
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeError("C1_CANONICAL_INPUT_SYMLINK_REJECTED")


def _journal_dsns() -> tuple[str, str]:
    fill = (os.getenv("LOCAL_PAPER_DATABASE_URL") or "").strip()
    evidence = (os.getenv("TRADE_MANAGEMENT_SHADOW_DATABASE_URL") or "").strip()
    if not fill or not evidence:
        raise RuntimeError("LOCAL_PAPER_AND_SHADOW_DSNS_ARE_REQUIRED")
    if fill == evidence:
        raise RuntimeError("SHADOW_DSN_MUST_BE_DEDICATED")
    return fill, evidence


def _postgres_journal(
    dsn: str,
    *,
    read_only: bool,
) -> PostgresJournalRepository:
    try:
        from psycopg_pool import ConnectionPool
    except ImportError as error:
        raise RuntimeError("POSTGRES_DRIVER_MISSING") from error
    connection_kwargs: dict[str, object] = {"connect_timeout": 5}
    if read_only:
        connection_kwargs["options"] = "-c default_transaction_read_only=on"
    pool = ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=1,
        kwargs=connection_kwargs,
        open=False,
    )
    try:
        pool.open(wait=True, timeout=5)
        repository = PostgresJournalRepository(pool=pool, owns_pool=True)
        repository.check_health()
        return repository
    except Exception:
        pool.close()
        raise


def _read_preflight_artifact(
    path: Path,
) -> tuple[dict[str, object], str, str]:
    sidecar = require_complete_artifact_pair(path)
    content = path.read_bytes()
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return (
        value,
        sha256_bytes(content),
        sidecar.read_text(encoding="utf-8").strip(),
    )


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _json_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a JSON boolean")
    return value


def _json_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a JSON integer")
    return value


def _optional_json_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _json_int(value, field_name)


def _json_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a JSON string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _json_string(value, field_name)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError(f"{field_name} must be an array of strings")
    return tuple(value)


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _print_result(
    status: str,
    reasons: tuple[str, ...],
    *,
    artifact: Path | None = None,
    digest: str | None = None,
) -> None:
    print(
        json.dumps(
            {
                "status": status,
                "reasons": list(reasons),
                "artifact": None if artifact is None else str(artifact.resolve()),
                "digest": digest,
                "production_shadow_gate": "NOT_PASSED",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
