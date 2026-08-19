import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backtest.dataset import HistoricalDatasetCatalog
from backtest.domain import HistoricalBar
from backtest.sqlite_repository import SQLiteBacktestRepository
from scripts.derive_backtest_daily_dataset import derive_daily_dataset, load_completion_proof_bundle


def _bar(
    *,
    session: date,
    hour: int,
    minute: int,
    close: str,
    volume: int,
) -> HistoricalBar:
    timestamp = datetime(
        session.year,
        session.month,
        session.day,
        hour,
        minute,
        tzinfo=ZoneInfo("Asia/Taipei"),
    )
    value = Decimal(close)
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=timestamp,
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=volume,
        amount=value * volume,
        session_date=session,
    )


def _session_contract() -> dict[str, object]:
    return {
        "version": "twse_holiday_schedule_2026_v1",
        "timezone": "Asia/Taipei",
        "regular_session": {"start": "09:00:00", "end": "13:30:00"},
    }


def _volume_contract() -> dict[str, object]:
    return {
        "scope": "REGULAR_SESSION",
        "unit": "COMMON_LOT",
        "shares_per_lot": 1000,
    }


def test_derived_daily_dataset_is_sealed_with_lineage_and_canonical_decimal(tmp_path: Path):
    first = date(2026, 8, 17)
    second = date(2026, 8, 18)
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    base = catalog.create_imported_dataset(
        bars=(
            _bar(session=first, hour=9, minute=1, close="100.00", volume=2),
            _bar(session=first, hour=13, minute=30, close="101.0", volume=3),
            _bar(session=second, hour=9, minute=1, close="102.00", volume=5),
            _bar(session=second, hour=13, minute=30, close="103.0", volume=7),
        ),
        source="fixture",
    )

    derived = catalog.create_derived_daily_dataset(
        dataset_id="dataset-derived-daily",
        base_dataset_id=base.dataset_id,
        completion_proofs={
            ("2330", first): "proof-17",
            ("2330", second): "proof-18",
        },
        session_contract=_session_contract(),
        price_adjustment_policy="RAW",
        corporate_action_adjusted=False,
        volume_contract=_volume_contract(),
    )

    assert derived.profile == "KBAR_DAILY_V1"
    assert derived.capabilities == ("OHLCV", "KBAR_DAILY")
    assert derived.daily_bar_contract == "DERIVED_FINALIZED_SESSION_V1"
    assert derived.derivation is not None
    assert derived.derivation["parent_dataset_digest"] == base.manifest_digest
    assert derived.price_adjustment_policy == "RAW"
    assert derived.corporate_action_adjusted is False
    assert derived.research_eligible is False
    bars = catalog.load_bars(derived.dataset_id)
    assert [(item.session_date, str(item.open), str(item.close), item.volume) for item in bars] == [
        (first, "100", "101", 5),
        (second, "102", "103", 12),
    ]
    assert len(catalog.load_bars(base.dataset_id)) == 4
    assert "session_date" not in HistoricalBar(
        symbol="legacy",
        timestamp=bars[0].timestamp,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=1,
    ).to_dict()

    replayed = catalog.create_derived_daily_dataset(
        dataset_id="dataset-derived-daily",
        base_dataset_id=base.dataset_id,
        completion_proofs={
            ("2330", first): "proof-17",
            ("2330", second): "proof-18",
        },
        session_contract=_session_contract(),
        price_adjustment_policy="RAW",
        corporate_action_adjusted=False,
        volume_contract=_volume_contract(),
    )
    assert replayed.manifest_digest == derived.manifest_digest
    with pytest.raises(ValueError, match="different immutable contract"):
        catalog.create_derived_daily_dataset(
            dataset_id="dataset-derived-daily",
            base_dataset_id=base.dataset_id,
            completion_proofs={
                ("2330", first): "proof-17",
                ("2330", second): "different-proof",
            },
            session_contract=_session_contract(),
            price_adjustment_policy="RAW",
            corporate_action_adjusted=False,
            volume_contract=_volume_contract(),
        )


def test_derived_daily_dataset_rejects_missing_session_completion_proof(tmp_path: Path):
    session = date(2026, 8, 18)
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    base = catalog.create_imported_dataset(
        bars=(
            _bar(session=session, hour=9, minute=1, close="100", volume=1),
            _bar(session=session, hour=9, minute=2, close="100", volume=1),
        ),
        source="fixture",
    )

    with pytest.raises(ValueError, match="completion evidence"):
        catalog.create_derived_daily_dataset(
            dataset_id="dataset-derived-daily",
            base_dataset_id=base.dataset_id,
            completion_proofs={},
            session_contract=_session_contract(),
            price_adjustment_policy="RAW",
            corporate_action_adjusted=False,
            volume_contract=_volume_contract(),
        )


def test_daily_derivation_cli_adapter_requires_versioned_proof_bundle_and_registers_ready_child(
    tmp_path: Path,
):
    session = date(2026, 8, 18)
    catalog = HistoricalDatasetCatalog(tmp_path / "datasets")
    repository = SQLiteBacktestRepository(tmp_path / "backtest.sqlite3")
    base = catalog.create_imported_dataset(
        bars=(
            _bar(session=session, hour=9, minute=1, close="100", volume=1),
            _bar(session=session, hour=13, minute=30, close="101", volume=1),
        ),
        source="fixture",
    )
    repository.upsert_dataset(base.to_dict(), "READY")
    proof_bundle = tmp_path / "proofs.json"
    proof_bundle.write_text(
        json.dumps(
            {
                "schema_version": "daily-session-completion-proofs-v1",
                "session_contract": _session_contract(),
                "volume_contract": _volume_contract(),
                "completion_proofs": [
                    {"symbol": "2330", "session_date": session.isoformat(), "digest": "proof-18"}
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        proofs, session_contract, volume_contract, issues = load_completion_proof_bundle(proof_bundle)
        assert proofs == {("2330", session): "proof-18"}
        assert session_contract == _session_contract()
        assert volume_contract == _volume_contract()
        assert issues == ()

        derived = derive_daily_dataset(
            dataset_id="dataset-cli-derived-daily",
            base_dataset_id=base.dataset_id,
            proof_bundle_path=proof_bundle,
            catalog=catalog,
            repository=repository,
        )
        assert derived["daily_bar_contract"] == "DERIVED_FINALIZED_SESSION_V1"
        assert repository.get_dataset("dataset-cli-derived-daily")["status"] == "READY"
    finally:
        repository.close()
