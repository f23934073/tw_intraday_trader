"""Seal a read-only PR-TM-012C0 readiness artifact for the next Shadow session."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from config.twse_calendar_2026 import PATH as CALENDAR_PATH
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.shioaji_momentum_stream import ShioajiMomentumStream
from runtime.trade_management_premarket import (
    AUTHORITATIVE_EVIDENCE_TABLES,
    DataOnlyProviderPreflight,
    PostgresReadOnlyPreflight,
    PremarketReadinessStatus,
    ShadowPremarketManifest,
    ShadowPremarketReadinessEvaluator,
    ShadowRehearsalEvidence,
)
from runtime.trade_management_artifact_io import write_json_digest_pair_exclusive
from runtime.trade_management_shadow_validation import SHADOW_VALIDATION_VERSION
from runtime.trade_management_runtime_identity import (
    RUNTIME_IDENTITY_PATHS,
    git_head,
    runtime_code_identity,
)
from trading.migrations import migration_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
PROVIDER_WORKER_ARG = "--provider-preflight-worker"
PROVIDER_WORKER_SENTINEL = "__TM_C0_PROVIDER_PREFLIGHT__="
REHEARSAL_TARGETS = tuple(
    sorted(
        (
            "tests/test_trade_management_c1_session.py",
            "tests/test_trade_management_operational_composition.py",
            "tests/test_trade_management_replay.py",
            "tests/test_trade_management_shadow_operation.py",
            "tests/test_trade_management_shadow_validation.py",
        )
    )
)
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", type=date.fromisoformat, required=True)
    parser.add_argument("--prepared-at", type=datetime.fromisoformat)
    parser.add_argument("--symbol", default="2330")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--connection-session-id", required=True)
    parser.add_argument("--strategy-id", default="opening_range_breakout")
    parser.add_argument("--strategy-version", default="opening_range_breakout_entry_v1")
    parser.add_argument("--thesis-version", default="orb-breakout-v1")
    parser.add_argument("--exit-policy-version", default="exit-policy-v1")
    parser.add_argument("--risk-policy-version", default="risk-v1")
    parser.add_argument("--fill-model-version", default="shadow-observation-no-fill-v1")
    parser.add_argument("--code-identity")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--skip-provider-login",
        action="store_true",
        help="Produce a BLOCKED artifact without connecting to Shioaji.",
    )
    parser.add_argument(
        "--skip-rehearsal",
        action="store_true",
        help="Produce a BLOCKED artifact without running the C0 rehearsal suite.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    prepared_at = args.prepared_at or datetime.now(TAIPEI)
    if prepared_at.tzinfo is None or prepared_at.utcoffset() is None:
        raise ValueError("--prepared-at must include a timezone offset")
    calendar = ReviewedEquityCalendar.from_path(CALENDAR_PATH)
    reviewed = calendar.is_trading_day(args.market_date)
    code_identity = args.code_identity or _runtime_code_identity()
    provider = _provider_preflight(skip_login=args.skip_provider_login)
    provider_name, provider_version, simulation = _provider_parts(
        provider.environment_identity
    )
    postgres = _postgres_preflight(
        (os.getenv("TRADE_MANAGEMENT_SHADOW_DATABASE_URL") or "").strip(),
        session_id=args.session_id,
    )
    rehearsal = _rehearsal(skip=args.skip_rehearsal)
    manifest = ShadowPremarketManifest(
        prepared_at=prepared_at.astimezone(TAIPEI),
        market_date=args.market_date,
        scheduled_open=datetime.combine(args.market_date, time(9), tzinfo=TAIPEI),
        scheduled_close=datetime.combine(
            args.market_date,
            time(13, 30),
            tzinfo=TAIPEI,
        ),
        calendar_schema_version=calendar.schema_version,
        calendar_digest=calendar.source_digest,
        session_id=args.session_id,
        symbol=args.symbol.strip().upper(),
        provider=provider_name,
        provider_version=provider_version,
        provider_simulation=simulation,
        connection_session_id=args.connection_session_id,
        code_identity=code_identity,
        migration_versions=tuple(path.name for path in migration_files()),
        strategy_id=args.strategy_id,
        strategy_version=args.strategy_version,
        thesis_version=args.thesis_version,
        exit_policy_version=args.exit_policy_version,
        risk_policy_version=args.risk_policy_version,
        fill_model_version=args.fill_model_version,
        validator_version=SHADOW_VALIDATION_VERSION,
    )
    report = ShadowPremarketReadinessEvaluator().evaluate(
        manifest,
        trading_date_reviewed=reviewed,
        provider=provider,
        postgres=postgres,
        rehearsal=rehearsal,
    )
    artifact = {
        "artifact_type": "TradeManagementShadowPremarketReadiness",
        "manifest": manifest.to_dict(),
        "manifest_digest": manifest.digest,
        "provider_preflight": {
            "credential_keys_present": list(provider.credential_keys_present),
            "login_succeeded": provider.login_succeeded,
            "logout_succeeded": provider.logout_succeeded,
            "subscribe_trade": provider.subscribe_trade,
            "environment_identity": provider.environment_identity,
            "error_code": provider.error_code,
            "digest": provider.digest,
        },
        "postgres_preflight": {
            "dsn_configured": postgres.dsn_configured,
            "driver_version": postgres.driver_version,
            "connected": postgres.connected,
            "transaction_read_only": postgres.transaction_read_only,
            "server_major": postgres.server_major,
            "table_names": list(postgres.table_names),
            "migration_versions": list(postgres.migration_versions),
            "evidence_row_counts": {
                table: count for table, count in postgres.evidence_row_counts
            },
            "evidence_scope_session_id": postgres.evidence_scope_session_id,
            "error_code": postgres.error_code,
            "digest": postgres.digest,
        },
        "rehearsal": {
            "source_class": "TEST_FIXTURE_AND_HISTORICAL_REPLAY",
            "test_targets": list(rehearsal.test_targets),
            "historical_replay_verified": rehearsal.historical_replay_verified,
            "operational_composition_verified": rehearsal.operational_composition_verified,
            "journal_recovery_verified": rehearsal.journal_recovery_verified,
            "replay_parity_matched": rehearsal.replay_parity_matched,
            "readiness_report_deterministic": rehearsal.readiness_report_deterministic,
            "qualifying_real_session": False,
            "execution_enabled": False,
            "digest": rehearsal.digest,
        },
        "readiness_report": report.to_dict(),
        "readiness_report_digest": report.digest,
        "production_shadow_gate": "NOT_PASSED",
    }
    write_json_digest_pair_exclusive(args.output, artifact, report.digest)
    print(
        json.dumps(
            {
                "status": report.status.value,
                "blockers": [item.value for item in report.blockers],
                "artifact": str(args.output),
                "report_digest": report.digest,
                "production_shadow_gate": "NOT_PASSED",
            },
            sort_keys=True,
        )
    )
    return 0 if report.status is PremarketReadinessStatus.READY_FOR_SESSION else 2


def _provider_preflight(*, skip_login: bool) -> DataOnlyProviderPreflight:
    credentials = _provider_credentials()
    if skip_login or len(credentials) != 2:
        return DataOnlyProviderPreflight(
            credential_keys_present=credentials,
            login_succeeded=False,
            logout_succeeded=False,
            subscribe_trade=False,
            environment_identity=None,
            error_code=("SKIPPED" if skip_login else "CREDENTIALS_MISSING"),
        )
    if not _loopback_bind_supported():
        return DataOnlyProviderPreflight(
            credential_keys_present=credentials,
            login_succeeded=False,
            logout_succeeded=False,
            subscribe_trade=False,
            environment_identity=None,
            error_code="LOOPBACK_BIND_DENIED",
        )
    result = _run_provider_preflight_worker()
    if result.returncode != 0:
        error_code = (
            f"NATIVE_SIGNAL_{-result.returncode}"
            if result.returncode < 0
            else f"WORKER_EXIT_{result.returncode}"
        )
        return DataOnlyProviderPreflight(
            credential_keys_present=credentials,
            login_succeeded=False,
            logout_succeeded=False,
            subscribe_trade=False,
            environment_identity=None,
            error_code=error_code,
        )
    try:
        payload_line = next(
            line
            for line in reversed(result.stdout.splitlines())
            if line.startswith(PROVIDER_WORKER_SENTINEL)
        )
        payload = json.loads(payload_line.removeprefix(PROVIDER_WORKER_SENTINEL))
        return DataOnlyProviderPreflight(
            credential_keys_present=tuple(payload["credential_keys_present"]),
            login_succeeded=payload["login_succeeded"],
            logout_succeeded=payload["logout_succeeded"],
            subscribe_trade=payload["subscribe_trade"],
            environment_identity=payload["environment_identity"],
            error_code=payload["error_code"],
        )
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
        return DataOnlyProviderPreflight(
            credential_keys_present=credentials,
            login_succeeded=False,
            logout_succeeded=False,
            subscribe_trade=False,
            environment_identity=None,
            error_code="WORKER_OUTPUT_INVALID",
        )


def _provider_credentials() -> tuple[str, ...]:
    credentials: list[str] = []
    if os.getenv("SHIOAJI_API_KEY") or os.getenv("SJ_API_KEY"):
        credentials.append("API_KEY")
    if (
        os.getenv("SHIOAJI_SECRET")
        or os.getenv("SJ_SECRET_KEY")
        or os.getenv("SJ_SEC_KEY")
    ):
        credentials.append("SECRET")
    return tuple(credentials)


def _loopback_bind_supported() -> bool:
    for socket_type in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
        try:
            with socket.socket(socket.AF_INET, socket_type) as probe:
                probe.bind(("127.0.0.1", 0))
        except OSError:
            return False
    return True


def _run_provider_preflight_worker() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), PROVIDER_WORKER_ARG],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def _provider_preflight_worker_main() -> int:
    provider = _provider_preflight_in_process()
    payload = {
        "credential_keys_present": list(provider.credential_keys_present),
        "login_succeeded": provider.login_succeeded,
        "logout_succeeded": provider.logout_succeeded,
        "subscribe_trade": provider.subscribe_trade,
        "environment_identity": provider.environment_identity,
        "error_code": provider.error_code,
    }
    print(PROVIDER_WORKER_SENTINEL + json.dumps(payload, sort_keys=True))
    return 0


def _provider_preflight_in_process() -> DataOnlyProviderPreflight:
    credentials = _provider_credentials()
    stream = None
    identity = None
    login_succeeded = False
    logout_succeeded = False
    error_code = None
    try:
        stream = ShioajiMomentumStream.connect_from_env(
            session_id="trade-management-c0-data-only-preflight"
        )
        identity = stream.environment_identity
        login_succeeded = True
    except Exception as error:
        error_code = type(error).__name__.upper()
    finally:
        if stream is not None:
            try:
                stream.close()
                logout_succeeded = True
            except Exception:
                logout_succeeded = False
                error_code = error_code or "LOGOUT_FAILED"
    return DataOnlyProviderPreflight(
        credential_keys_present=credentials,
        login_succeeded=login_succeeded,
        logout_succeeded=logout_succeeded,
        subscribe_trade=False,
        environment_identity=identity,
        error_code=error_code,
    )


def _provider_parts(identity: str | None) -> tuple[str, str, bool]:
    if identity is None:
        return "shioaji", "unknown", True
    parts = identity.split(":")
    if len(parts) != 3 or not parts[2].startswith("simulation="):
        return "shioaji", "unknown", True
    return parts[0], parts[1], parts[2].split("=", 1)[1].lower() == "true"


def _postgres_preflight(
    dsn: str,
    *,
    session_id: str,
) -> PostgresReadOnlyPreflight:
    empty_counts = tuple((table, 0) for table in AUTHORITATIVE_EVIDENCE_TABLES)
    if not dsn:
        return PostgresReadOnlyPreflight(
            dsn_configured=False,
            driver_version=None,
            connected=False,
            transaction_read_only=False,
            server_major=None,
            table_names=(),
            migration_versions=(),
            evidence_row_counts=empty_counts,
            evidence_scope_session_id=session_id,
            error_code="DSN_MISSING",
        )
    try:
        import psycopg
    except ImportError:
        return PostgresReadOnlyPreflight(
            dsn_configured=True,
            driver_version=None,
            connected=False,
            transaction_read_only=False,
            server_major=None,
            table_names=(),
            migration_versions=(),
            evidence_row_counts=empty_counts,
            evidence_scope_session_id=session_id,
            error_code="DRIVER_MISSING",
        )
    try:
        connection = psycopg.connect(
            dsn,
            options="-c default_transaction_read_only=on",
            connect_timeout=5,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                read_only = str(cursor.fetchone()[0]).lower() == "on"
                cursor.execute("SHOW server_version_num")
                server_major = int(str(cursor.fetchone()[0])) // 10000
                cursor.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'trading'
                    ORDER BY table_name
                    """
                )
                tables = tuple(str(row[0]) for row in cursor.fetchall())
                migrations: tuple[str, ...] = ()
                if "journal_schema_migrations" in tables:
                    cursor.execute(
                        """
                        SELECT version
                        FROM trading.journal_schema_migrations
                        ORDER BY version
                        """
                    )
                    migrations = tuple(str(row[0]) for row in cursor.fetchall())
                counts: list[tuple[str, int]] = []
                for table in AUTHORITATIVE_EVIDENCE_TABLES:
                    if table not in tables:
                        counts.append((table, 0))
                        continue
                    cursor.execute(
                        f"SELECT COUNT(*) FROM trading.{table} WHERE session_id = %s",
                        (session_id,),
                    )
                    counts.append((table, int(cursor.fetchone()[0])))
            connection.rollback()
        finally:
            connection.close()
        return PostgresReadOnlyPreflight(
            dsn_configured=True,
            driver_version=psycopg.__version__,
            connected=True,
            transaction_read_only=read_only,
            server_major=server_major,
            table_names=tables,
            migration_versions=migrations,
            evidence_row_counts=tuple(counts),
            evidence_scope_session_id=session_id,
        )
    except Exception as error:
        return PostgresReadOnlyPreflight(
            dsn_configured=True,
            driver_version=psycopg.__version__,
            connected=False,
            transaction_read_only=False,
            server_major=None,
            table_names=(),
            migration_versions=(),
            evidence_row_counts=empty_counts,
            evidence_scope_session_id=session_id,
            error_code=type(error).__name__.upper(),
        )


def _rehearsal(*, skip: bool) -> ShadowRehearsalEvidence:
    passed = False
    if not skip:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *REHEARSAL_TARGETS],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        passed = result.returncode == 0
    return ShadowRehearsalEvidence(
        test_targets=REHEARSAL_TARGETS,
        historical_replay_verified=passed,
        operational_composition_verified=passed,
        journal_recovery_verified=passed,
        replay_parity_matched=passed,
        readiness_report_deterministic=passed,
    )


def _git_head() -> str:
    return git_head(PROJECT_ROOT)


def _runtime_code_identity() -> str:
    return runtime_code_identity(
        project_root=PROJECT_ROOT,
        identity_paths=RUNTIME_IDENTITY_PATHS,
        git_head_value=_git_head(),
    )


if __name__ == "__main__":
    if sys.argv[1:] == [PROVIDER_WORKER_ARG]:
        raise SystemExit(_provider_preflight_worker_main())
    raise SystemExit(main())
