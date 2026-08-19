from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from config.premarket import PREMARKET_CONTEXT_V0
from premarket.artifacts import (
    InMemoryPremarketArtifactRepository,
    create_context_artifact,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.models import (
    CompletenessStatus,
    ContextHealth,
    ContractIdentity,
    ContractIdentityStatus,
    NightBar,
    ReconciliationObservation,
    ReconciliationStatus,
    SourceObservation,
)
from premarket.reconciliation import ReconciliationService
from premarket.service import PremarketContextService
from premarket.taifex_reconciliation import (
    TAIFEX_AFTER_HOURS_VOLUME_BASIS,
    TAIFEX_FUT_DAILY_REPORT_URL,
    build_taifex_daily_report_capture,
    parse_taifex_after_hours_observation,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "taifex_fut_daily_market_report_after_hours.html"
)


def _context(
    *,
    identity_status: ContractIdentityStatus = ContractIdentityStatus.RESOLVED_HISTORICALLY,
    delivery_month: str = "202608",
):  # type: ignore[no-untyped-def]
    identity = ContractIdentity(
        status=identity_status,
        resolution_method="DATED_CONTRACT_FIXTURE",
        resolved_contract_code=(
            "TXFH6" if identity_status is not ContractIdentityStatus.UNRESOLVED else None
        ),
        delivery_month=delivery_month,
        last_trading_date=date(2026, 8, 19),
    )
    return create_context_artifact(
        schema_version="taifex_night_context_v0",
        readiness_predicate_version="taifex_night_ready_v0",
        trading_date=date(2026, 8, 19),
        timezone="Asia/Taipei",
        product_root="TXF",
        contract_alias="TXFR1",
        contract_identity=identity,
        session_start=datetime.fromisoformat("2026-08-18T15:00:00+08:00"),
        session_end=datetime.fromisoformat("2026-08-19T05:00:00+08:00"),
        query_not_before=datetime.fromisoformat("2026-08-19T05:05:00+08:00"),
        queried_at=datetime.fromisoformat("2026-08-19T05:07:00+08:00"),
        received_at=datetime.fromisoformat("2026-08-19T05:07:01+08:00"),
        provider_reference_price=Decimal("45088"),
        provider_reference_updated_at=datetime.fromisoformat(
            "2026-08-18T13:45:00+08:00"
        ),
        provider_reference_source="SHIOAJI_FUTURES_INFO_REFERENCE",
        open=Decimal("45137"),
        high=Decimal("45208"),
        low=Decimal("44424"),
        close=Decimal("44527"),
        volume=28114,
        first_event_at=datetime.fromisoformat("2026-08-18T15:00:00+08:00"),
        last_event_at=datetime.fromisoformat("2026-08-19T04:59:00+08:00"),
        completeness_status=CompletenessStatus.UNKNOWN,
        completeness_evidence=("QUERY_RETURNED_ROWS",),
        health=ContextHealth.PENDING,
        reasons=("SOURCE_COMPLETENESS_UNQUALIFIED",),
        source="SHIOAJI",
        raw_source_digest="a" * 64,
    )


def _capture():  # type: ignore[no-untyped-def]
    return build_taifex_daily_report_capture(
        trading_date=date(2026, 8, 19),
        product_code="TX",
        retrieved_at=datetime.fromisoformat("2026-08-19T07:05:00+08:00"),
        raw_response=FIXTURE.read_bytes(),
    )


def test_official_after_hours_report_creates_separate_partial_reconciliation() -> None:
    context = _context()
    capture = _capture()
    observation = parse_taifex_after_hours_observation(
        capture,
        context=context,
    )

    assert observation.source == "TAIFEX_FUT_DAILY_MARKET_REPORT"
    assert observation.contract_code == "TXFH6"
    assert observation.taifex_delivery_month == "202608"
    assert observation.taifex_settlement_price is None
    assert observation.taifex_close == Decimal("44527")
    assert observation.taifex_volume == 28126
    assert observation.taifex_volume_basis == TAIFEX_AFTER_HOURS_VOLUME_BASIS
    assert observation.comparable_fields == ("open", "high", "low", "close")
    assert observation.raw_source_json is not None

    repository = InMemoryPremarketArtifactRepository()
    repository.save_context(context)
    reconciliation = ReconciliationService(repository).reconcile(
        context,
        observation,
    )

    assert reconciliation.context_digest == context.context_digest
    assert reconciliation.taifex_settlement_price is None
    assert reconciliation.taifex_volume == 28126
    assert reconciliation.taifex_volume_basis == TAIFEX_AFTER_HOURS_VOLUME_BASIS
    assert reconciliation.field_deltas == (
        ("open", Decimal("0")),
        ("high", Decimal("0")),
        ("low", Decimal("0")),
        ("close", Decimal("0")),
    )
    assert reconciliation.status is ReconciliationStatus.PARTIAL
    assert reconciliation.reasons == ("TAIFEX_VOLUME_BASIS_UNQUALIFIED",)
    assert repository.contexts() == (context,)
    assert repository.raw_source(observation.raw_source_digest) is not None


def test_parser_rejects_tampered_response_wrong_date_and_wrong_delivery_month() -> None:
    capture = _capture()
    with pytest.raises(ValueError, match="response digest"):
        parse_taifex_after_hours_observation(
            replace(capture, raw_response_text=capture.raw_response_text + " "),
            context=_context(),
        )
    with pytest.raises(ValueError, match="trading date"):
        parse_taifex_after_hours_observation(
            build_taifex_daily_report_capture(
                trading_date=date(2026, 8, 18),
                product_code="TX",
                retrieved_at=capture.retrieved_at,
                raw_response=FIXTURE.read_bytes(),
            ),
            context=_context(),
        )
    with pytest.raises(ValueError, match="delivery month"):
        parse_taifex_after_hours_observation(
            capture,
            context=_context(delivery_month="202610"),
        )


def test_parser_requires_official_source_and_resolved_dated_identity() -> None:
    capture = _capture()
    with pytest.raises(ValueError, match="official TAIFEX source URL"):
        parse_taifex_after_hours_observation(
            replace(capture, source_url="https://example.invalid/report"),
            context=_context(),
        )
    with pytest.raises(ValueError, match="resolved contract identity"):
        parse_taifex_after_hours_observation(
            capture,
            context=_context(identity_status=ContractIdentityStatus.UNRESOLVED),
        )
    with pytest.raises(ValueError, match="resolved context contract code"):
        ReconciliationService(InMemoryPremarketArtifactRepository()).reconcile(
            _context(identity_status=ContractIdentityStatus.UNRESOLVED),
            ReconciliationObservation(
                source="TAIFEX_FIXTURE",
                raw_source_digest="d" * 64,
                taifex_trading_date=date(2026, 8, 19),
                contract_code="TXFH6",
                reconciled_at=capture.retrieved_at,
                taifex_close=Decimal("44527"),
            ),
        )


def test_capture_contract_uses_reviewed_official_after_hours_request() -> None:
    capture = _capture()

    assert capture.source_url == TAIFEX_FUT_DAILY_REPORT_URL
    assert dict(capture.request_parameters) == {
        "MarketCode": "1",
        "commodity_id": "TX",
        "commodity_idt": "TX",
        "marketCode": "1",
        "queryDate": "2026/08/19",
        "queryType": "2",
    }


def test_cached_ready_context_joins_later_reconciliation_without_source_requery() -> None:
    context = _context()
    window = TaifexTradingCalendar.from_path(
        PREMARKET_CONTEXT_V0.calendar_path
    ).session_window(date(2026, 8, 19), PREMARKET_CONTEXT_V0.query_delay)
    observation = SourceObservation(
        trading_date=context.trading_date,
        contract_identity=context.contract_identity,
        bars=(
            NightBar(
                timestamp=window.start,
                open=context.open,
                high=Decimal("45150"),
                low=Decimal("45000"),
                close=Decimal("45100"),
                volume=100,
            ),
            NightBar(
                timestamp=window.end - PREMARKET_CONTEXT_V0.session_end_tolerance,
                open=Decimal("45100"),
                high=context.high,
                low=context.low,
                close=context.close,
                volume=28014,
            ),
        ),
        queried_at=context.queried_at,
        received_at=context.received_at,
        provider_reference_price=context.provider_reference_price,
        provider_reference_updated_at=context.provider_reference_updated_at,
        provider_reference_source=context.provider_reference_source,
        completeness_status=CompletenessStatus.COMPLETE,
        completeness_evidence=("TEST_SESSION_COMPLETE",),
        source="TEST_SOURCE",
        raw_source_digest="c" * 64,
    )

    class Source:
        calls = 0

        def supports_premarket_context(self) -> bool:
            return True

        def get_taifex_night_session(self, requested_window, contract_alias):  # type: ignore[no-untyped-def]
            self.calls += 1
            assert requested_window == window
            assert contract_alias == "TXFR1"
            return observation

    source = Source()
    repository = InMemoryPremarketArtifactRepository()
    service = PremarketContextService(
        source=source,
        calendar=TaifexTradingCalendar.from_path(
            PREMARKET_CONTEXT_V0.calendar_path
        ),
        config=replace(
            PREMARKET_CONTEXT_V0,
            qualified_completion_evidence=(
                ("TEST_SOURCE", "TEST_SESSION_COMPLETE"),
            ),
        ),
        artifacts=repository,
        now=lambda: datetime.fromisoformat("2026-08-19T07:06:00+08:00"),
    )

    first = service.projection()
    stored_context = repository.contexts()[0]
    assert first["status"] == "READY"
    assert first["reconciliation"]["status"] == "PENDING"
    ReconciliationService(repository).reconcile(
        stored_context,
        parse_taifex_after_hours_observation(_capture(), context=stored_context),
    )

    second = service.projection()

    assert second["status"] == "READY"
    assert second["reconciliation"]["status"] == "PARTIAL"
    assert source.calls == 1
