from datetime import datetime
from decimal import Decimal

import pytest

from simulation.settings import (
    JsonLocalPaperSettingsRepository,
    LocalPaperSettings,
    LocalPaperSettingsConflict,
    SETTINGS_SCHEMA_V1,
    SETTINGS_SCHEMA_V2,
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


@pytest.mark.parametrize(
    "payload",
    ["[]", '{"schema_version": "local-paper-settings-v2"}'],
)
def test_file_repository_normalizes_structurally_corrupt_documents(
    tmp_path,
    payload: str,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="設定檔損壞"):
        JsonLocalPaperSettingsRepository(path).load()


def test_v1_file_load_and_v2_draft_preview_do_not_rewrite_file(tmp_path) -> None:
    path = tmp_path / "settings.json"
    repository = JsonLocalPaperSettingsRepository(path)
    repository.save_draft(settings(), expected_revision=0, updated_at=AT)
    before = path.read_bytes()

    state = repository.load()
    draft = state.v2_draft()

    assert path.read_bytes() == before
    assert state.active.schema_version == SETTINGS_SCHEMA_V1
    assert draft.schema_version == SETTINGS_SCHEMA_V2
    assert draft.starting_cash_twd == state.draft.starting_cash_twd
    assert draft.max_daily_buy_notional_twd == state.draft.max_daily_buy_notional_twd
    assert draft.slippage_bps == Decimal("5")
    assert draft.commission_rate == Decimal("0.001425")
    assert draft.minimum_commission_twd == Decimal("20")


def test_v2_draft_save_and_explicit_activation_support_mixed_migration(tmp_path) -> None:
    path = tmp_path / "settings.json"
    repository = JsonLocalPaperSettingsRepository(path)
    initial = repository.load()
    v2_draft = initial.v2_draft()

    drafted = repository.save_draft(
        v2_draft,
        expected_revision=initial.revision,
        updated_at=AT,
    )
    reloaded_draft = repository.load()

    assert reloaded_draft.document_schema_version == SETTINGS_SCHEMA_V2
    assert reloaded_draft.active.schema_version == SETTINGS_SCHEMA_V1
    assert reloaded_draft.draft.schema_version == SETTINGS_SCHEMA_V2
    assert reloaded_draft.active_session_id == initial.active_session_id

    activated = repository.activate_draft(
        expected_revision=drafted.revision,
        updated_at=AT,
        session_id="local-paper-runtime-v2-test",
    )
    reloaded_active = repository.load()

    assert reloaded_active == activated
    assert reloaded_active.active.schema_version == SETTINGS_SCHEMA_V2
    assert reloaded_active.active_session_id == "local-paper-runtime-v2-test"


def test_v2_digest_pins_frozen_policy_and_slippage() -> None:
    baseline = LocalPaperSettings.v2_from_v1(settings())
    changed = LocalPaperSettings(
        starting_cash_twd=baseline.starting_cash_twd,
        max_daily_buy_notional_twd=baseline.max_daily_buy_notional_twd,
        commission_rate=baseline.commission_rate,
        minimum_commission_twd=baseline.minimum_commission_twd,
        slippage_bps=Decimal("6"),
        schema_version=SETTINGS_SCHEMA_V2,
    )

    assert baseline.digest != changed.digest
    assert baseline.to_dict()["sell_tax_rate"] == "0.003"
    assert baseline.to_dict()["fee_policy_version"] == "tw_stock_standard_v1"
    assert baseline.to_dict()["rounding_policy_version"] == "twd_round_down_v1"
    assert baseline.commission_for(Decimal("100000")) == Decimal("142")


def test_v2_reader_rejects_policy_override_or_missing_identity() -> None:
    payload = LocalPaperSettings.v2_from_v1(settings()).to_dict()
    payload["commission_rate"] = "0.001"

    with pytest.raises(ValueError, match="policy identity"):
        LocalPaperSettings.from_mapping(payload)


def test_v2_reader_normalizes_schema_before_enforcing_policy_identity() -> None:
    payload = LocalPaperSettings.v2_from_v1(settings()).to_dict()
    payload["settings_schema_version"] = f" {SETTINGS_SCHEMA_V2} "
    del payload["fee_policy_version"]

    with pytest.raises(ValueError, match="policy identity"):
        LocalPaperSettings.from_mapping(payload)


def test_v2_reader_requires_boolean_false_day_trade() -> None:
    payload = LocalPaperSettings.v2_from_v1(settings()).to_dict()
    payload["day_trade"] = 0

    with pytest.raises(ValueError, match="policy identity"):
        LocalPaperSettings.from_mapping(payload)


def test_v2_reader_rejects_missing_slippage() -> None:
    payload = LocalPaperSettings.v2_from_v1(settings()).to_dict()
    del payload["slippage_bps"]

    with pytest.raises(ValueError, match="缺少 slippage_bps"):
        LocalPaperSettings.from_mapping(payload)
