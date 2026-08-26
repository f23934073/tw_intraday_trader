"""Run one complete data-only PR-TM-012C1 Shadow session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal
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
from runtime.trade_management_live_capture import (
    LiveShadowCaptureConfig,
    LiveShadowProviderIdentity,
)
from runtime.trade_management_operational_composition import LiveShadowDecisionPolicy
from scripts.preflight_trade_management_shadow import _runtime_code_identity
from trading.live_entry_thesis_draft import (
    LiveThesisDraftPolicy,
    LiveTradeThesisDraftBuilder,
)
from trading.risk import CommandSide, RiskPolicy, RiskSnapshot
from trading.postgres_journal import PostgresJournalRepository
from trading.trade_management_serialization import (
    deserialize_live_entry_decision,
    deserialize_trade_thesis_draft,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-artifact", type=Path, required=True)
    parser.add_argument("--entry-decision", type=Path, required=True)
    parser.add_argument("--thesis-draft", type=Path, required=True)
    parser.add_argument("--shadow-policy", type=Path, required=True)
    parser.add_argument("--risk-snapshot", type=Path, required=True)
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
            "preflight_sha256": _file_sha256(args.preflight_artifact),
            "entry_decision_artifact": str(args.entry_decision.resolve()),
            "entry_decision_sha256": _file_sha256(args.entry_decision),
            "thesis_draft_artifact": str(args.thesis_draft.resolve()),
            "thesis_draft_sha256": _file_sha256(args.thesis_draft),
            "shadow_policy_artifact": str(args.shadow_policy.resolve()),
            "shadow_policy_sha256": _file_sha256(args.shadow_policy),
            "risk_snapshot_artifact": str(args.risk_snapshot.resolve()),
            "risk_snapshot_sha256": _file_sha256(args.risk_snapshot),
            "session_evidence": evidence.to_dict(),
            "session_evidence_digest": evidence.digest,
            "production_shadow_gate": "NOT_PASSED",
        }
        _write_exclusive(args.output, artifact)
        _write_digest_exclusive(
            args.output.with_suffix(args.output.suffix + ".sha256"),
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
    preflight = _read_json(args.preflight_artifact)
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
    if (
        report.get("manifest_digest") != preflight.get("manifest_digest")
        or report.get("provider_preflight_digest") != provider.get("digest")
        or report.get("postgres_preflight_digest") != postgres.get("digest")
        or report.get("rehearsal_digest") != rehearsal.get("digest")
    ):
        raise RuntimeError("C0_COMPONENT_DIGEST_BINDING_MISMATCH")
    sidecar = args.preflight_artifact.with_suffix(
        args.preflight_artifact.suffix + ".sha256"
    )
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").strip() != preflight.get(
        "readiness_report_digest"
    ):
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
    if manifest.get("code_identity") != _runtime_code_identity():
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
    scheduled_open = datetime.fromisoformat(str(manifest["scheduled_open"]))
    earliest_connect = scheduled_open - timedelta(
        seconds=args.preopen_wait_timeout_seconds
    )
    if now < earliest_connect or now >= scheduled_open:
        raise RuntimeError("C1_MUST_START_INSIDE_PREOPEN_CONNECTION_WINDOW")

    decision = deserialize_live_entry_decision(
        args.entry_decision.read_text(encoding="utf-8")
    )
    reviewed_draft = deserialize_trade_thesis_draft(
        args.thesis_draft.read_text(encoding="utf-8")
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
    shadow_policy = _load_shadow_policy(
        args.shadow_policy,
        code_identity=str(manifest["code_identity"]),
    )
    if (
        shadow_policy.exit_policy_version != manifest.get("exit_policy_version")
        or shadow_policy.risk_policy.version != manifest.get("risk_policy_version")
        or shadow_policy.fill_model_version != manifest.get("fill_model_version")
    ):
        raise RuntimeError("SHADOW_POLICY_C0_BINDING_MISMATCH")
    return {
        "calendar": calendar,
        "manifest": manifest,
        "decision": decision,
        "draft_policy": draft_policy,
        "shadow_policy": shadow_policy,
        "risk_snapshot": _load_risk_snapshot(args.risk_snapshot),
    }


def _load_shadow_policy(path: Path, *, code_identity: str) -> LiveShadowDecisionPolicy:
    value = _read_json(path)
    risk = _mapping(value.get("risk_policy"), "risk_policy")
    sides = frozenset(
        CommandSide(str(item)) for item in risk.get("fresh_book_sides", ())
    )
    return LiveShadowDecisionPolicy(
        exit_policy_version=str(value["exit_policy_version"]),
        risk_policy=RiskPolicy(
            version=str(risk["version"]),
            allow_strategy_origin=_bool(
                risk["allow_strategy_origin"],
                "risk_policy.allow_strategy_origin",
            ),
            max_order_notional=Decimal(str(risk["max_order_notional"])),
            max_position_notional=Decimal(str(risk["max_position_notional"])),
            max_daily_loss=Decimal(str(risk["max_daily_loss"])),
            max_daily_buy_notional=(
                None
                if risk.get("max_daily_buy_notional") is None
                else Decimal(str(risk["max_daily_buy_notional"]))
            ),
            commission_rate=Decimal(str(risk.get("commission_rate", "0"))),
            minimum_commission=Decimal(str(risk.get("minimum_commission", "0"))),
            require_fresh_book=_bool(
                risk.get("require_fresh_book", False),
                "risk_policy.require_fresh_book",
            ),
            max_book_age_seconds=int(risk.get("max_book_age_seconds", 15)),
            fresh_book_sides=sides or frozenset(CommandSide),
        ),
        volume_baseline_shares=Decimal(str(value["volume_baseline_shares"])),
        shares_per_lot=int(value["shares_per_lot"]),
        remaining_quantity_shares=int(value["remaining_quantity_shares"]),
        fill_model_version=str(value["fill_model_version"]),
        code_identity=code_identity,
    )


def _load_risk_snapshot(path: Path) -> RiskSnapshot:
    value = _read_json(path)
    return RiskSnapshot(
        data_health_state=str(value["data_health_state"]),
        market_open=_bool(value["market_open"], "market_open"),
        instrument_tradable=_bool(
            value["instrument_tradable"],
            "instrument_tradable",
        ),
        available_cash=Decimal(str(value["available_cash"])),
        current_position_shares=int(value["current_position_shares"]),
        pending_buy_shares=int(value["pending_buy_shares"]),
        pending_sell_shares=int(value["pending_sell_shares"]),
        daily_realized_pnl=Decimal(str(value["daily_realized_pnl"])),
        daily_filled_buy_notional=Decimal(
            str(value.get("daily_filled_buy_notional", "0"))
        ),
        pending_buy_notional=Decimal(str(value.get("pending_buy_notional", "0"))),
        same_side_pending_order=_bool(
            value.get("same_side_pending_order", False),
            "same_side_pending_order",
        ),
        book_age_seconds=(
            None
            if value.get("book_age_seconds") is None
            else int(value["book_age_seconds"])
        ),
        daily_loss=(
            None if value.get("daily_loss") is None else Decimal(str(value["daily_loss"]))
        ),
    )


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


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a JSON boolean")
    return value


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_exclusive(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_digest_exclusive(path: Path, digest: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(digest + "\n")


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
