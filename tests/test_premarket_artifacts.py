from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from config.premarket import PREMARKET_CONTEXT_V0
from premarket.artifacts import (
    ArtifactIntegrityError,
    FilePremarketArtifactRepository,
    InMemoryPremarketArtifactRepository,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.models import ReconciliationObservation
from premarket.reconciliation import ReconciliationService
from premarket.service import PremarketContextService
from tests.test_premarket_context import FixtureSource, _observation


def test_context_and_reconciliation_are_separate_immutable_artifacts() -> None:
    repository = InMemoryPremarketArtifactRepository()
    config = replace(
        PREMARKET_CONTEXT_V0,
        qualified_completion_evidence=(("TEST_SOURCE", "TEST_SESSION_COMPLETE"),),
    )
    context_service = PremarketContextService(
        source=FixtureSource(_observation()),
        calendar=TaifexTradingCalendar.from_path(config.calendar_path),
        config=config,
        artifacts=repository,
        now=lambda: datetime.fromisoformat("2026-08-22T05:07:00+08:00"),
    )
    context_service.projection()
    context = repository.contexts()[0]
    original_digest = context.context_digest

    observation = ReconciliationObservation(
        source="TAIFEX_DAILY_REPORT_FIXTURE",
        raw_source_digest="b" * 64,
        taifex_trading_date=date(2026, 8, 24),
        contract_code="TXF202608",
        reconciled_at=datetime.fromisoformat("2026-08-24T07:05:00+08:00"),
        taifex_settlement_price=Decimal("23980"),
        taifex_open=Decimal("24000"),
        taifex_high=Decimal("24220"),
        taifex_low=Decimal("23910"),
        taifex_close=Decimal("24180"),
        taifex_volume=30,
    )
    service = ReconciliationService(repository)
    reconciliation = service.reconcile(context, observation)

    assert reconciliation.context_digest == original_digest
    assert reconciliation.reconciliation_digest != original_digest
    assert repository.contexts()[0] == context
    assert repository.reconciliations(original_digest) == (reconciliation,)
    with pytest.raises(FrozenInstanceError):
        context.health = "MUTATED"  # type: ignore[misc]
    with pytest.raises(ValueError, match="context digest"):
        service.project_summary("c" * 64, reconciliation)
    with pytest.raises(ValueError, match="trading date"):
        service.reconcile(
            context,
            replace(observation, taifex_trading_date=date(2026, 8, 25)),
        )
    with pytest.raises(ValueError, match="contract code"):
        service.reconcile(
            context,
            replace(observation, contract_code="TXF202609"),
        )


def test_filesystem_repository_rehydrates_separate_raw_context_and_reconciliation(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    repository = FilePremarketArtifactRepository(tmp_path)
    config = replace(
        PREMARKET_CONTEXT_V0,
        qualified_completion_evidence=(("TEST_SOURCE", "TEST_SESSION_COMPLETE"),),
    )
    context_service = PremarketContextService(
        source=FixtureSource(_observation()),
        calendar=TaifexTradingCalendar.from_path(config.calendar_path),
        config=config,
        artifacts=repository,
        now=lambda: datetime.fromisoformat("2026-08-22T05:07:00+08:00"),
    )

    context_service.projection()
    context = repository.contexts()[0]
    raw = repository.raw_source(context.raw_source_digest)
    assert raw is not None
    assert raw.source == "TEST_SOURCE"

    observation = ReconciliationObservation(
        source="TAIFEX_DAILY_REPORT_FIXTURE",
        raw_source_digest="b" * 64,
        taifex_trading_date=context.trading_date,
        contract_code=context.contract_identity.resolved_contract_code or "",
        reconciled_at=datetime.fromisoformat("2026-08-24T07:05:00+08:00"),
        taifex_close=context.close,
    )
    reconciliation = ReconciliationService(repository).reconcile(context, observation)

    reloaded = FilePremarketArtifactRepository(tmp_path)
    assert reloaded.contexts() == (context,)
    assert reloaded.reconciliations(context.context_digest) == (reconciliation,)
    assert reloaded.latest_reconciliation(context.context_digest) == reconciliation
    assert len(tuple((tmp_path / "raw").glob("*.json"))) == 1
    assert len(tuple((tmp_path / "contexts").glob("*.json"))) == 1
    assert len(tuple((tmp_path / "reconciliations" / context.context_digest).glob("*.json"))) == 1


def test_filesystem_repository_rejects_tampered_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = FilePremarketArtifactRepository(tmp_path)
    config = replace(
        PREMARKET_CONTEXT_V0,
        qualified_completion_evidence=(("TEST_SOURCE", "TEST_SESSION_COMPLETE"),),
    )
    PremarketContextService(
        source=FixtureSource(_observation()),
        calendar=TaifexTradingCalendar.from_path(config.calendar_path),
        config=config,
        artifacts=repository,
        now=lambda: datetime.fromisoformat("2026-08-22T05:07:00+08:00"),
    ).projection()
    path = next((tmp_path / "contexts").glob("*.json"))
    path.write_text(path.read_text(encoding="utf-8").replace('"close":"24180"', '"close":"1"'), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError):
        FilePremarketArtifactRepository(tmp_path).contexts()


def test_filesystem_raw_save_is_idempotent_when_only_capture_time_changes(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    repository = FilePremarketArtifactRepository(tmp_path)
    config = replace(
        PREMARKET_CONTEXT_V0,
        qualified_completion_evidence=(("TEST_SOURCE", "TEST_SESSION_COMPLETE"),),
    )
    PremarketContextService(
        source=FixtureSource(_observation()),
        calendar=TaifexTradingCalendar.from_path(config.calendar_path),
        config=config,
        artifacts=repository,
        now=lambda: datetime.fromisoformat("2026-08-22T05:07:00+08:00"),
    ).projection()
    context = repository.contexts()[0]
    original = repository.raw_source(context.raw_source_digest)
    assert original is not None

    repository.save_raw(
        replace(original, captured_at=original.captured_at + timedelta(minutes=1))
    )

    assert repository.raw_source(context.raw_source_digest) == original
