"""Materialize a verified daily child from a sealed intraday backtest dataset.

The command is deliberately offline: it never contacts a Provider or broker.
Every source ``(symbol, session_date)`` must be represented by a reviewed
completion-evidence digest in the supplied JSON bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.application import BacktestApplicationService
from backtest.dataset import HistoricalDatasetCatalog
from backtest.repository import BacktestRepository
from config import backtest as backtest_settings


def load_completion_proof_bundle(
    path: Path,
) -> tuple[dict[tuple[str, date], str], dict[str, Any], dict[str, Any], tuple[str, ...]]:
    """Load the explicit proof bundle accepted by the daily derivation contract."""

    if not path.is_file():
        raise ValueError(f"找不到 completion proof bundle：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"completion proof bundle 不是合法 JSON：{path}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("completion proof bundle 必須是 JSON object")
    if payload.get("schema_version") != "daily-session-completion-proofs-v1":
        raise ValueError("不支援的 completion proof bundle schema_version")
    session_contract = payload.get("session_contract")
    volume_contract = payload.get("volume_contract")
    rows = payload.get("completion_proofs")
    issues = payload.get("issues", [])
    if not isinstance(session_contract, Mapping) or not isinstance(volume_contract, Mapping):
        raise ValueError("completion proof bundle 必須包含 session_contract 與 volume_contract object")
    if not isinstance(rows, list) or not rows:
        raise ValueError("completion proof bundle 必須包含非空 completion_proofs array")
    if not isinstance(issues, list) or not all(isinstance(item, str) for item in issues):
        raise ValueError("completion proof bundle issues 必須是字串 array")

    proofs: dict[tuple[str, date], str] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"completion_proofs[{index}] 必須是 object")
        symbol = str(row.get("symbol") or "").strip()
        digest = str(row.get("digest") or "").strip()
        try:
            session_date = date.fromisoformat(str(row.get("session_date") or ""))
        except ValueError as error:
            raise ValueError(f"completion_proofs[{index}].session_date 必須是 YYYY-MM-DD") from error
        if not symbol or not digest:
            raise ValueError(f"completion_proofs[{index}] 必須包含 symbol 與 digest")
        key = (symbol, session_date)
        if key in proofs:
            raise ValueError(f"completion proof 重複：{symbol} {session_date.isoformat()}")
        proofs[key] = digest
    return proofs, dict(session_contract), dict(volume_contract), tuple(issues)


def derive_daily_dataset(
    *,
    dataset_id: str,
    base_dataset_id: str,
    proof_bundle_path: Path,
    catalog: HistoricalDatasetCatalog,
    repository: BacktestRepository,
) -> dict[str, object]:
    """Seal and register one daily dataset after READY-base validation."""

    base = repository.get_dataset(base_dataset_id)
    if base.get("status") != "READY":
        raise ValueError("base dataset 必須是 READY 才能派生日 K 資料集")
    proofs, session_contract, volume_contract, issues = load_completion_proof_bundle(proof_bundle_path)
    manifest = catalog.create_derived_daily_dataset(
        dataset_id=dataset_id,
        base_dataset_id=base_dataset_id,
        completion_proofs=proofs,
        session_contract=session_contract,
        price_adjustment_policy="RAW",
        corporate_action_adjusted=False,
        volume_contract=volume_contract,
        issues=issues,
    )
    repository.upsert_dataset(manifest.to_dict(), "READY")
    return manifest.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="從 completion evidence 派生並封存回測日 K 資料集")
    parser.add_argument("--base-dataset-id", required=True, help="已封存且 READY 的 intraday dataset ID")
    parser.add_argument("--dataset-id", required=True, help="新的 immutable dataset ID，必須以 dataset- 開頭")
    parser.add_argument(
        "--completion-proofs",
        required=True,
        type=Path,
        help="daily-session-completion-proofs-v1 JSON bundle",
    )
    args = parser.parse_args()
    catalog = HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
    repository = BacktestApplicationService._build_repository()
    try:
        manifest = derive_daily_dataset(
            dataset_id=args.dataset_id,
            base_dataset_id=args.base_dataset_id,
            proof_bundle_path=args.completion_proofs,
            catalog=catalog,
            repository=repository,
        )
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
