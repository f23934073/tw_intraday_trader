from datetime import datetime
from decimal import Decimal

import pytest

from simulation.settings import (
    JsonLocalPaperSettingsRepository,
    LocalPaperSettings,
    LocalPaperSettingsConflict,
)


AT = datetime.fromisoformat("2026-08-23T10:00:00+08:00")


def settings(**changes: str) -> LocalPaperSettings:
    values = {
        "starting_cash_twd": "10000000",
        "max_daily_buy_notional_twd": "2000000",
        "commission_rate": "0.001425",
        "minimum_commission_twd": "20",
    }
    values.update(changes)
    return LocalPaperSettings.from_mapping(values)


def test_settings_validate_independent_cash_limit_and_commission() -> None:
    configured = settings(
        starting_cash_twd="10000000",
        max_daily_buy_notional_twd="12000000",
    )

    assert configured.starting_cash_twd == Decimal("10000000")
    assert configured.max_daily_buy_notional_twd == Decimal("12000000")
    assert configured.commission_for(Decimal("100000")) == Decimal("142.50")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("starting_cash_twd", "0"),
        ("max_daily_buy_notional_twd", "0"),
        ("commission_rate", "0.02"),
        ("minimum_commission_twd", "-1"),
        ("commission_rate", "NaN"),
    ],
)
def test_settings_reject_invalid_values(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        settings(**{field: value})


def test_settings_reject_sub_cent_minimum_commission() -> None:
    with pytest.raises(ValueError, match="minimum_commission_twd 必須以 0.01 元為單位"):
        settings(minimum_commission_twd="0.001")


def test_settings_digest_uses_canonical_decimal_strings() -> None:
    assert settings(minimum_commission_twd="20").digest == settings(
        minimum_commission_twd="20.00"
    ).digest


def test_file_repository_persists_draft_and_active_revision(tmp_path) -> None:
    repository = JsonLocalPaperSettingsRepository(tmp_path / "settings.json")
    initial = repository.load()

    drafted = repository.save_draft(
        settings(),
        expected_revision=initial.revision,
        updated_at=AT,
    )
    active = repository.activate_draft(
        expected_revision=drafted.revision,
        updated_at=AT,
        session_id="local-paper-runtime-settings-test",
    )
    restored = repository.load()

    assert restored == active
    assert restored.active == settings()
    assert restored.active_session_id == "local-paper-runtime-settings-test"
    assert restored.active_settings_revision == drafted.draft_settings_revision
    assert restored.draft_settings_revision == drafted.draft_settings_revision


def test_file_repository_rejects_stale_revision_and_corrupt_file(tmp_path) -> None:
    path = tmp_path / "settings.json"
    repository = JsonLocalPaperSettingsRepository(path)
    repository.save_draft(settings(), expected_revision=0, updated_at=AT)

    with pytest.raises(LocalPaperSettingsConflict):
        repository.save_draft(settings(), expected_revision=0, updated_at=AT)

    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="設定檔損壞"):
        repository.load()
