"""Durable, offline provenance for deterministic FinMind universe selection."""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.dataset import DatasetManifest
from backtest.domain import canonical_json
from backtest.finmind_history import SOURCE, SOURCE_VERSION, VOLUME_UNIT
from backtest.finmind_snapshot import FinMindSnapshotPlan


SCHEMA_VERSION = "finmind-selection-bundle-v1"
SELECTOR_VERSION = "phase82-diversified-market-value-v1"
SELECTOR_CONTRACT: dict[str, Any] = {
    "aggregate_industries": ["創新板股票", "化學生技醫療", "電子工業"],
    "broad_industry_aliases": {
        "其他電子業": "其他電子",
        "化學工業": "化學",
        "汽車工業": "汽車",
        "生技醫療業": "生技醫療",
        "金融保險": "金融",
        "金融業": "金融",
        "食品工業": "食品",
    },
    "current_identity_rule": (
        "latest FinMind TaiwanStockInfo date; exactly one active TWSE/TPEx "
        "market/name identity and exactly one specific industry after aggregate removal"
    ),
    "eligible_market_rule": ["tpex", "twse"],
    "industry_leader_order": ["market_value_desc", "symbol_asc"],
    "listing_rule": "official_listing_date < window_start",
    "market_value_rule": "latest sealed date and positive integer market_value",
    "non_company_industries": [
        "ETF",
        "ETN",
        "Index",
        "創新板股票",
        "受益證券",
        "大盤",
        "存託憑證",
    ],
    "ranking_order": [
        "dataset_broad_industry_coverage_asc",
        "market_value_desc",
        "symbol_asc",
    ],
    "selected_count": 8,
    "symbol_rule": "exactly four decimal digits",
}


class FinMindSelectionBundleError(RuntimeError):
    """Raised when durable selection provenance cannot be reproduced."""


_TARGET_JOB_IMMUTABLE_FIELDS = (
    "calendar_symbol",
    "created_at",
    "end_date",
    "job_id",
    "source",
    "source_version",
    "start_date",
    "symbols",
    "volume_unit",
)
_TARGET_JOB_LIFECYCLE_FIELDS = frozenset(
    {
        "calendar_raw_payload_is_null",
        "calendar_raw_sha256",
        "status",
        "status_message",
        "trading_dates_json",
        "updated_at",
    }
)
_TARGET_JOB_STATUSES = frozenset(
    {"QUEUED", "RUNNING", "PAUSED", "COMPLETED", "BLOCKED_DATA_QUALITY"}
)


def digest_json(value: Mapping[str, Any] | list[Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def seal_bundle(document: Mapping[str, Any]) -> dict[str, Any]:
    sealed = json.loads(canonical_json(document))
    sealed.pop("bundle_digest", None)
    sealed["bundle_digest"] = digest_json(sealed)
    return sealed


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _project_path(project_root: Path, path: Path) -> tuple[Path, str]:
    root = project_root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise FinMindSelectionBundleError(
            f"selection evidence escapes project root: {path}"
        ) from error
    if not resolved.is_file():
        raise FinMindSelectionBundleError(f"selection evidence is missing: {relative}")
    return resolved, relative.as_posix()


def _file_reference(
    project_root: Path,
    path: Path,
    *,
    source_label: str,
    row_count: int | None = None,
) -> dict[str, Any]:
    resolved, relative = _project_path(project_root, path)
    payload = resolved.read_bytes()
    reference: dict[str, Any] = {
        "path": relative,
        "sha256": _sha256(payload),
        "size_bytes": len(payload),
        "source_label": source_label,
    }
    if row_count is not None:
        reference["row_count"] = row_count
    return reference


def verify_file_reference(project_root: Path, reference: Mapping[str, Any]) -> bytes:
    raw_path = str(reference.get("path") or "")
    if not raw_path or Path(raw_path).is_absolute():
        raise FinMindSelectionBundleError("evidence path must be project-relative")
    resolved, relative = _project_path(project_root, project_root / raw_path)
    payload = resolved.read_bytes()
    if len(payload) != int(reference.get("size_bytes", -1)):
        raise FinMindSelectionBundleError(f"evidence size mismatch: {relative}")
    if _sha256(payload) != str(reference.get("sha256")):
        raise FinMindSelectionBundleError(f"evidence digest mismatch: {relative}")
    return payload


def _json_rows(payload: bytes, *, label: str) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinMindSelectionBundleError(f"{label} is not valid JSON") from error
    if not isinstance(decoded, list) or not all(isinstance(row, dict) for row in decoded):
        raise FinMindSelectionBundleError(f"{label} must be a JSON object array")
    return decoded


def _gzip_rows(payload: bytes, *, label: str) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = gzip.decompress(payload)
        decoded = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinMindSelectionBundleError(f"{label} is not valid gzip JSON") from error
    rows = decoded.get("data") if isinstance(decoded, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise FinMindSelectionBundleError(f"{label} does not contain data rows")
    return rows, raw


def _broad_industry(value: str, aliases: Mapping[str, str]) -> str:
    normalized = value.removesuffix("類")
    return str(aliases.get(normalized, normalized))


def _current_info(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[tuple[date, str, str, str]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("stock_id") or "").strip().upper()
        market = str(row.get("type") or "").strip().lower()
        industry = str(row.get("industry_category") or "").strip()
        name = str(row.get("stock_name") or "").strip()
        if not symbol or not industry or not name:
            continue
        try:
            observed_date = date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        grouped[symbol].append((observed_date, market, industry, name))

    result: dict[str, dict[str, Any]] = {}
    aggregates = set(SELECTOR_CONTRACT["aggregate_industries"])
    for symbol, observations in grouped.items():
        latest_date = max(item[0] for item in observations)
        latest_active = {
            item
            for item in observations
            if item[0] == latest_date and item[1] in {"twse", "tpex"}
        }
        identities = {(item[1], item[3]) for item in latest_active}
        if len(identities) != 1:
            continue
        industries = {item[2] for item in latest_active}
        specific = industries - aggregates
        if len(specific) == 1:
            industry = next(iter(specific))
        elif len(industries) == 1:
            industry = next(iter(industries))
        else:
            continue
        market, name = next(iter(identities))
        result[symbol] = {
            "industry": industry,
            "info_date": latest_date.isoformat(),
            "market": market,
            "name": name,
        }
    return result


def _official_listings(
    twse_rows: Sequence[Mapping[str, Any]],
    tpex_rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in twse_rows:
        symbol = str(row.get("公司代號") or "").strip()
        value = str(row.get("上市日期") or "").strip()
        if symbol and len(value) == 8 and value.isdigit():
            result[("twse", symbol)] = {
                "listing_date": f"{value[:4]}-{value[4:6]}-{value[6:]}",
                "official_name": str(row.get("公司簡稱") or "").strip(),
                "official_source": "TWSE_OPENAPI_COMPANY",
            }
    for row in tpex_rows:
        symbol = str(row.get("SecuritiesCompanyCode") or "").strip()
        value = str(row.get("DateOfListing") or "").strip()
        if symbol and len(value) == 8 and value.isdigit():
            result[("tpex", symbol)] = {
                "listing_date": f"{value[:4]}-{value[4:6]}-{value[6:]}",
                "official_name": str(row.get("CompanyAbbreviation") or "").strip(),
                "official_source": "TPEX_OPENAPI_COMPANY",
            }
    return result


def _selection_projection(
    *,
    info_rows: Sequence[Mapping[str, Any]],
    value_rows: Sequence[Mapping[str, Any]],
    twse_rows: Sequence[Mapping[str, Any]],
    tpex_rows: Sequence[Mapping[str, Any]],
    dataset_symbols: Sequence[str],
    excluded_symbols: Sequence[str],
    window_start: date,
) -> dict[str, Any]:
    info = _current_info(info_rows)
    try:
        market_value_date = max(date.fromisoformat(str(row["date"])) for row in value_rows)
    except (KeyError, TypeError, ValueError) as error:
        raise FinMindSelectionBundleError("market-value date is invalid") from error
    values: dict[str, int] = {}
    for row in value_rows:
        try:
            row_date = date.fromisoformat(str(row["date"]))
            market_value = int(row["market_value"])
        except (KeyError, TypeError, ValueError) as error:
            raise FinMindSelectionBundleError("market-value row is invalid") from error
        if row_date == market_value_date and market_value > 0:
            values[str(row["stock_id"]).strip().upper()] = market_value

    aliases = SELECTOR_CONTRACT["broad_industry_aliases"]
    non_company = set(SELECTOR_CONTRACT["non_company_industries"])
    listings = _official_listings(twse_rows, tpex_rows)
    coverage = Counter(
        _broad_industry(str(info[symbol]["industry"]), aliases)
        for symbol in dataset_symbols
        if symbol in info
    )
    excluded = set(excluded_symbols)
    eligible: list[dict[str, Any]] = []
    rejected = Counter()
    for symbol, market_value in values.items():
        metadata = info.get(symbol)
        if metadata is None:
            rejected["missing_current_identity"] += 1
            continue
        market = str(metadata["market"])
        industry = str(metadata["industry"])
        if len(symbol) != 4 or not symbol.isdigit():
            rejected["not_four_digit_common_stock"] += 1
            continue
        if market not in {"twse", "tpex"} or industry in non_company:
            rejected["non_company_or_market"] += 1
            continue
        if symbol in excluded:
            rejected["already_included_or_completed"] += 1
            continue
        official = listings.get((market, symbol))
        if official is None:
            rejected["missing_local_official_listing"] += 1
            continue
        listing_date = date.fromisoformat(official["listing_date"])
        if listing_date >= window_start:
            rejected["recent_or_incomplete_listing"] += 1
            continue
        broad = _broad_industry(industry, aliases)
        eligible.append(
            {
                "broad_industry": broad,
                "industry": industry,
                "industry_coverage": coverage[broad],
                "listing_date": listing_date.isoformat(),
                "market": market,
                "market_value": market_value,
                "name": metadata["name"],
                "official_name": official["official_name"],
                "official_source": official["official_source"],
                "symbol": symbol,
            }
        )

    leaders: dict[str, dict[str, Any]] = {}
    for row in eligible:
        industry = str(row["broad_industry"])
        current = leaders.get(industry)
        key = (-int(row["market_value"]), str(row["symbol"]))
        if current is None or key < (
            -int(current["market_value"]),
            str(current["symbol"]),
        ):
            leaders[industry] = row
    ranked = sorted(
        leaders.values(),
        key=lambda row: (
            int(row["industry_coverage"]),
            -int(row["market_value"]),
            str(row["symbol"]),
        ),
    )
    return {
        "eligible_count": len(eligible),
        "eligible_industry_count": len(leaders),
        "market_value_date": market_value_date.isoformat(),
        "ranked_candidates": ranked,
        "rejected_counts": dict(sorted(rejected.items())),
        "selected": ranked[: int(SELECTOR_CONTRACT["selected_count"])],
    }


def _completed_job_bindings(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT job_id, source, source_version, start_date, end_date, symbols_json,
               calendar_symbol, volume_unit, status
        FROM finmind_history_jobs
        WHERE status = 'COMPLETED'
        ORDER BY job_id
        """
    ).fetchall()
    return [
        {
            "calendar_symbol": str(row["calendar_symbol"]),
            "end_date": str(row["end_date"]),
            "job_id": str(row["job_id"]),
            "source": str(row["source"]),
            "source_version": str(row["source_version"]),
            "start_date": str(row["start_date"]),
            "status": str(row["status"]),
            "symbols": list(json.loads(row["symbols_json"])),
            "volume_unit": str(row["volume_unit"]),
        }
        for row in rows
    ]


def _job_config(symbols: Sequence[str], start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "calendar_symbol": "2330",
        "end_date": end_date,
        "source": SOURCE,
        "start_date": start_date,
        "symbols": sorted(set(symbols)),
    }


def _verify_target_job_state(
    *,
    observed_row: Mapping[str, Any],
    expected_state: Mapping[str, Any],
    partition_count: int,
    attempt_count: int,
    calendar_raw_payload: bytes | None,
) -> None:
    """Verify immutable job identity while allowing append-only acquisition lifecycle."""

    expected_row = expected_state["row"]
    expected_fields = set(_TARGET_JOB_IMMUTABLE_FIELDS) | _TARGET_JOB_LIFECYCLE_FIELDS
    if set(expected_row) != expected_fields or set(observed_row) != expected_fields:
        raise FinMindSelectionBundleError("bound target job schema drifted")
    expected_identity = {
        field: expected_row[field] for field in _TARGET_JOB_IMMUTABLE_FIELDS
    }
    observed_identity = {
        field: observed_row[field] for field in _TARGET_JOB_IMMUTABLE_FIELDS
    }
    if observed_identity != expected_identity:
        raise FinMindSelectionBundleError("bound target job identity drifted")

    expected_attempt_count = int(expected_state["attempt_count"])
    expected_partition_count = int(expected_state["partition_count"])
    if int(expected_state["recorded_request_count"]) != expected_attempt_count:
        raise FinMindSelectionBundleError("sealed target request count is inconsistent")
    if bool(expected_state["calendar_is_null"]) != (
        expected_row["trading_dates_json"] is None
    ):
        raise FinMindSelectionBundleError("sealed target calendar state is inconsistent")
    if partition_count < expected_partition_count:
        raise FinMindSelectionBundleError("target partition count regressed")
    if attempt_count < expected_attempt_count:
        raise FinMindSelectionBundleError("target attempt count regressed")

    status = str(observed_row["status"])
    if status not in _TARGET_JOB_STATUSES:
        raise FinMindSelectionBundleError("bound target job lifecycle status is invalid")
    observed_dates = observed_row["trading_dates_json"]
    observed_sha256 = observed_row["calendar_raw_sha256"]
    observed_payload_is_null = bool(observed_row["calendar_raw_payload_is_null"])
    if observed_dates is None:
        if observed_sha256 is not None or not observed_payload_is_null:
            raise FinMindSelectionBundleError("bound target calendar state is inconsistent")
    else:
        try:
            dates = json.loads(str(observed_dates))
        except json.JSONDecodeError as error:
            raise FinMindSelectionBundleError(
                "bound target trading calendar is invalid"
            ) from error
        if not isinstance(dates, list) or not all(isinstance(value, str) for value in dates):
            raise FinMindSelectionBundleError("bound target trading calendar is invalid")
        if observed_sha256 is None or observed_payload_is_null or calendar_raw_payload is None:
            raise FinMindSelectionBundleError("bound target calendar state is inconsistent")
        try:
            raw_calendar = gzip.decompress(calendar_raw_payload)
        except OSError as error:
            raise FinMindSelectionBundleError(
                "bound target calendar payload is invalid"
            ) from error
        if _sha256(raw_calendar) != str(observed_sha256):
            raise FinMindSelectionBundleError("bound target calendar digest mismatch")

    for field in ("trading_dates_json", "calendar_raw_sha256"):
        sealed_value = expected_row[field]
        if sealed_value is not None and observed_row[field] != sealed_value:
            raise FinMindSelectionBundleError(f"bound target {field} drifted")
    if not bool(expected_row["calendar_raw_payload_is_null"]) and observed_payload_is_null:
        raise FinMindSelectionBundleError("bound target calendar payload regressed")


def build_selection_bundle(
    *,
    project_root: Path,
    database_path: Path,
    stock_info_path: Path,
    market_value_path: Path,
    twse_path: Path,
    tpex_path: Path,
    dataset_manifest_path: Path,
    snapshot_plan_path: Path,
    target_job_id: str,
    window_start: date,
    window_end: date,
) -> dict[str, Any]:
    root = project_root.resolve()
    info_payload = stock_info_path.read_bytes()
    value_payload = market_value_path.read_bytes()
    info_rows, info_raw = _gzip_rows(info_payload, label="TaiwanStockInfo")
    value_rows, value_raw = _gzip_rows(value_payload, label="TaiwanStockMarketValue")
    twse_rows = _json_rows(twse_path.read_bytes(), label="TWSE company snapshot")
    tpex_rows = _json_rows(tpex_path.read_bytes(), label="TPEx company snapshot")

    manifest_payload = dataset_manifest_path.read_bytes()
    manifest_value = json.loads(manifest_payload)
    manifest = DatasetManifest.from_dict(manifest_value)
    if manifest.manifest_digest != str(manifest_value.get("manifest_digest")):
        raise FinMindSelectionBundleError("Dataset manifest digest mismatch")
    plan_payload = snapshot_plan_path.read_bytes()
    plan_value = json.loads(plan_payload)
    plan = FinMindSnapshotPlan.from_dict(plan_value)
    if manifest.plan_identity_digest != plan.plan_identity_digest:
        raise FinMindSelectionBundleError("Dataset/plan identity digest mismatch")

    connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise FinMindSelectionBundleError("SQLite quick_check failed")
        completed_jobs = _completed_job_bindings(connection)
        target = connection.execute(
            "SELECT * FROM finmind_history_jobs WHERE job_id = ?", (target_job_id,)
        ).fetchone()
        if target is None:
            raise FinMindSelectionBundleError(f"target job is missing: {target_job_id}")
        partition_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM finmind_history_partitions WHERE job_id = ?",
                (target_job_id,),
            ).fetchone()[0]
        )
        attempt_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM finmind_history_attempts WHERE job_id = ?",
                (target_job_id,),
            ).fetchone()[0]
        )
    finally:
        connection.close()

    dataset_symbols = sorted(set(manifest.requested_symbols))
    completed_symbols = sorted(
        {symbol for job in completed_jobs for symbol in job["symbols"]}
    )
    manual_exclusions = ["7610"]
    excluded_symbols = sorted(set(dataset_symbols) | set(completed_symbols) | {"7610"})
    selection = _selection_projection(
        info_rows=info_rows,
        value_rows=value_rows,
        twse_rows=twse_rows,
        tpex_rows=tpex_rows,
        dataset_symbols=dataset_symbols,
        excluded_symbols=excluded_symbols,
        window_start=window_start,
    )
    selected_symbols = [str(row["symbol"]) for row in selection["selected"]]
    config = _job_config(selected_symbols, window_start.isoformat(), window_end.isoformat())
    config_digest = digest_json(config)
    expected_job_id = f"finmind-sponsor-{config_digest[:16]}"
    if expected_job_id != target_job_id:
        raise FinMindSelectionBundleError("selected symbols do not reproduce target job id")

    target_row = {
        key: target[key]
        for key in target.keys()
        if key not in {"calendar_raw_payload"}
    }
    target_row["symbols"] = json.loads(target_row.pop("symbols_json"))
    target_row["calendar_raw_payload_is_null"] = target["calendar_raw_payload"] is None
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "selector_version": SELECTOR_VERSION,
        "selector_contract": SELECTOR_CONTRACT,
        "selector_contract_digest": digest_json(SELECTOR_CONTRACT),
        "source_evidence": {
            "approved_dataset": {
                **_file_reference(
                    root,
                    dataset_manifest_path,
                    source_label="APPROVED_FINMIND_DATASET_MANIFEST",
                ),
                "bars_sha256": manifest.bars_sha256,
                "dataset_id": manifest.dataset_id,
                "manifest_digest": manifest.manifest_digest,
                "plan_identity_digest": manifest.plan_identity_digest,
                "requested_symbol_count": len(dataset_symbols),
                "source_snapshot_digest": manifest.source_snapshot_digest,
            },
            "approved_snapshot_plan": {
                **_file_reference(
                    root,
                    snapshot_plan_path,
                    source_label="APPROVED_FINMIND_SNAPSHOT_PLAN",
                ),
                "plan_identity_digest": plan.plan_identity_digest,
            },
            "finmind_stock_info": {
                **_file_reference(
                    root,
                    stock_info_path,
                    source_label="SEALED_FINMIND_TAIWAN_STOCK_INFO_2026-08-20",
                    row_count=len(info_rows),
                ),
                "raw_body_sha256": _sha256(info_raw),
            },
            "finmind_market_value": {
                **_file_reference(
                    root,
                    market_value_path,
                    source_label="SEALED_FINMIND_TAIWAN_STOCK_MARKET_VALUE_2026-08-20",
                    row_count=len(value_rows),
                ),
                "raw_body_sha256": _sha256(value_raw),
            },
            "official_tpex_company": _file_reference(
                root,
                tpex_path,
                source_label="TPEX_OPENAPI_COMPANY",
                row_count=len(tpex_rows),
            ),
            "official_twse_company": _file_reference(
                root,
                twse_path,
                source_label="TWSE_OPENAPI_COMPANY",
                row_count=len(twse_rows),
            ),
        },
        "exclusion_evidence": {
            "completed_job_bindings": completed_jobs,
            "completed_job_bindings_digest": digest_json(completed_jobs),
            "completed_symbols": completed_symbols,
            "completed_symbols_digest": digest_json(completed_symbols),
            "dataset_symbols": dataset_symbols,
            "dataset_symbols_digest": digest_json(dataset_symbols),
            "excluded_symbols": excluded_symbols,
            "excluded_symbols_digest": digest_json(excluded_symbols),
            "manual_exclusions": manual_exclusions,
        },
        "selection": {
            **selection,
            "window_end": window_end.isoformat(),
            "window_start": window_start.isoformat(),
        },
        "job_binding": {
            "config": config,
            "config_sha256": config_digest,
            "job_id": target_job_id,
            "post_create_state": {
                "attempt_count": attempt_count,
                "calendar_is_null": target["trading_dates_json"] is None,
                "partition_count": partition_count,
                "recorded_request_count": attempt_count,
                "row": target_row,
            },
        },
    }
    return seal_bundle(document)


def validate_bundle_document(bundle: Mapping[str, Any]) -> None:
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise FinMindSelectionBundleError("unsupported selection bundle schema")
    if bundle.get("selector_version") != SELECTOR_VERSION:
        raise FinMindSelectionBundleError("unsupported selector version")
    without_digest = dict(bundle)
    observed_digest = str(without_digest.pop("bundle_digest", ""))
    if digest_json(without_digest) != observed_digest:
        raise FinMindSelectionBundleError("selection bundle self-digest mismatch")
    if bundle.get("selector_contract") != SELECTOR_CONTRACT:
        raise FinMindSelectionBundleError("selector contract/alias map mismatch")
    if bundle.get("selector_contract_digest") != digest_json(SELECTOR_CONTRACT):
        raise FinMindSelectionBundleError("selector contract digest mismatch")

    exclusion = bundle["exclusion_evidence"]
    dataset_symbols = list(exclusion["dataset_symbols"])
    completed_symbols = list(exclusion["completed_symbols"])
    manual = list(exclusion["manual_exclusions"])
    expected_union = sorted(set(dataset_symbols) | set(completed_symbols) | set(manual))
    if list(exclusion["excluded_symbols"]) != expected_union:
        raise FinMindSelectionBundleError("exclusion set does not match bound inputs")
    for field in (
        "dataset_symbols",
        "completed_symbols",
        "excluded_symbols",
        "completed_job_bindings",
    ):
        if exclusion[f"{field}_digest"] != digest_json(list(exclusion[field])):
            raise FinMindSelectionBundleError(f"{field} digest mismatch")

    selection = bundle["selection"]
    ranked = list(selection["ranked_candidates"])
    selected = list(selection["selected"])
    if selected != ranked[: int(SELECTOR_CONTRACT["selected_count"])]:
        raise FinMindSelectionBundleError("selected ordering does not match ranking")
    config = bundle["job_binding"]["config"]
    selected_symbols = sorted(str(row["symbol"]) for row in selected)
    if list(config["symbols"]) != selected_symbols:
        raise FinMindSelectionBundleError("job config symbols do not match selection")
    config_digest = digest_json(config)
    if bundle["job_binding"]["config_sha256"] != config_digest:
        raise FinMindSelectionBundleError("job config digest mismatch")
    if bundle["job_binding"]["job_id"] != f"finmind-sponsor-{config_digest[:16]}":
        raise FinMindSelectionBundleError("job id does not match config digest")


def verify_selection_bundle(
    bundle_path: Path,
    *,
    project_root: Path,
    database_path: Path,
) -> dict[str, Any]:
    bundle = json.loads(bundle_path.read_bytes())
    validate_bundle_document(bundle)
    expected_name = f"phase82_selection_{bundle['bundle_digest']}.json"
    if bundle_path.name != expected_name:
        raise FinMindSelectionBundleError("bundle filename does not match self-digest")

    sources = bundle["source_evidence"]
    twse_payload = verify_file_reference(project_root, sources["official_twse_company"])
    tpex_payload = verify_file_reference(project_root, sources["official_tpex_company"])
    info_payload = verify_file_reference(project_root, sources["finmind_stock_info"])
    value_payload = verify_file_reference(project_root, sources["finmind_market_value"])
    manifest_payload = verify_file_reference(project_root, sources["approved_dataset"])
    plan_payload = verify_file_reference(project_root, sources["approved_snapshot_plan"])

    twse_rows = _json_rows(twse_payload, label="TWSE company snapshot")
    tpex_rows = _json_rows(tpex_payload, label="TPEx company snapshot")
    info_rows, info_raw = _gzip_rows(info_payload, label="TaiwanStockInfo")
    value_rows, value_raw = _gzip_rows(value_payload, label="TaiwanStockMarketValue")
    for key, rows in (
        ("official_twse_company", twse_rows),
        ("official_tpex_company", tpex_rows),
        ("finmind_stock_info", info_rows),
        ("finmind_market_value", value_rows),
    ):
        if int(sources[key]["row_count"]) != len(rows):
            raise FinMindSelectionBundleError(f"source row count mismatch: {key}")
    if sources["finmind_stock_info"]["raw_body_sha256"] != _sha256(info_raw):
        raise FinMindSelectionBundleError("TaiwanStockInfo raw digest mismatch")
    if sources["finmind_market_value"]["raw_body_sha256"] != _sha256(value_raw):
        raise FinMindSelectionBundleError("TaiwanStockMarketValue raw digest mismatch")

    manifest_value = json.loads(manifest_payload)
    manifest = DatasetManifest.from_dict(manifest_value)
    dataset_reference = sources["approved_dataset"]
    if manifest.manifest_digest != dataset_reference["manifest_digest"]:
        raise FinMindSelectionBundleError("approved Dataset manifest digest mismatch")
    if manifest.dataset_id != dataset_reference["dataset_id"]:
        raise FinMindSelectionBundleError("approved Dataset id mismatch")
    if manifest.bars_sha256 != dataset_reference["bars_sha256"]:
        raise FinMindSelectionBundleError("approved Dataset bars digest mismatch")
    if manifest.source_snapshot_digest != dataset_reference["source_snapshot_digest"]:
        raise FinMindSelectionBundleError("approved Dataset source snapshot mismatch")
    if len(set(manifest.requested_symbols)) != int(
        dataset_reference["requested_symbol_count"]
    ):
        raise FinMindSelectionBundleError("approved Dataset symbol count mismatch")
    plan = FinMindSnapshotPlan.from_dict(json.loads(plan_payload))
    if plan.plan_identity_digest != sources["approved_snapshot_plan"]["plan_identity_digest"]:
        raise FinMindSelectionBundleError("approved snapshot plan digest mismatch")
    if manifest.plan_identity_digest != plan.plan_identity_digest:
        raise FinMindSelectionBundleError("approved Dataset/plan binding mismatch")

    exclusion = bundle["exclusion_evidence"]
    if sorted(set(manifest.requested_symbols)) != list(exclusion["dataset_symbols"]):
        raise FinMindSelectionBundleError("Dataset requested symbols drifted")
    selection = bundle["selection"]
    reproduced = _selection_projection(
        info_rows=info_rows,
        value_rows=value_rows,
        twse_rows=twse_rows,
        tpex_rows=tpex_rows,
        dataset_symbols=exclusion["dataset_symbols"],
        excluded_symbols=exclusion["excluded_symbols"],
        window_start=date.fromisoformat(str(selection["window_start"])),
    )
    expected_selection = {key: selection[key] for key in reproduced}
    if reproduced != expected_selection:
        raise FinMindSelectionBundleError("sealed inputs do not reproduce selection")

    connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise FinMindSelectionBundleError("SQLite quick_check failed")
        for expected in exclusion["completed_job_bindings"]:
            row = connection.execute(
                """
                SELECT job_id, source, source_version, start_date, end_date,
                       symbols_json, calendar_symbol, volume_unit, status
                FROM finmind_history_jobs WHERE job_id = ?
                """,
                (expected["job_id"],),
            ).fetchone()
            if row is None:
                raise FinMindSelectionBundleError(
                    f"completed job binding is missing: {expected['job_id']}"
                )
            observed = {
                "calendar_symbol": str(row["calendar_symbol"]),
                "end_date": str(row["end_date"]),
                "job_id": str(row["job_id"]),
                "source": str(row["source"]),
                "source_version": str(row["source_version"]),
                "start_date": str(row["start_date"]),
                "status": str(row["status"]),
                "symbols": list(json.loads(row["symbols_json"])),
                "volume_unit": str(row["volume_unit"]),
            }
            if observed != expected:
                raise FinMindSelectionBundleError(
                    f"completed job binding drifted: {expected['job_id']}"
                )

        job_id = str(bundle["job_binding"]["job_id"])
        row = connection.execute(
            "SELECT * FROM finmind_history_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise FinMindSelectionBundleError("bound target job is missing")
        observed_row = {
            key: row[key] for key in row.keys() if key != "calendar_raw_payload"
        }
        observed_row["symbols"] = json.loads(observed_row.pop("symbols_json"))
        observed_row["calendar_raw_payload_is_null"] = row["calendar_raw_payload"] is None
        expected_state = bundle["job_binding"]["post_create_state"]
        partition_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM finmind_history_partitions WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
        )
        attempt_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM finmind_history_attempts WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
        )
        _verify_target_job_state(
            observed_row=observed_row,
            expected_state=expected_state,
            partition_count=partition_count,
            attempt_count=attempt_count,
            calendar_raw_payload=(
                bytes(row["calendar_raw_payload"])
                if row["calendar_raw_payload"] is not None
                else None
            ),
        )
    finally:
        connection.close()

    return {
        "bundle_digest": bundle["bundle_digest"],
        "eligible_count": selection["eligible_count"],
        "job_id": bundle["job_binding"]["job_id"],
        "quick_check": "ok",
        "ranked_candidate_count": len(selection["ranked_candidates"]),
        "selected_symbols": [row["symbol"] for row in selection["selected"]],
        "status": "VERIFIED",
    }
