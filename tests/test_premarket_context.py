import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from config.premarket import PREMARKET_CONTEXT_V0
from premarket.artifacts import (
    InMemoryPremarketArtifactRepository,
    canonical_json,
    sha256_text_digest,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.models import (
    CompletenessStatus,
    ContractIdentity,
    ContractIdentityStatus,
    NightBar,
    SourceObservation,
)
from premarket.service import PremarketContextService


class FixtureSource:
    def __init__(self, observation: SourceObservation) -> None:
        self.observation = observation
        self.calls = 0

    def supports_premarket_context(self) -> bool:
        return True

    def get_taifex_night_session(self, window, contract_alias):  # type: ignore[no-untyped-def]
        self.calls += 1
        assert contract_alias == "TXFR1"
        assert self.observation.trading_date == window.trading_date
        return self.observation


def _calendar() -> TaifexTradingCalendar:
    return TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path)


def _observation(
    *,
    completeness: CompletenessStatus = CompletenessStatus.COMPLETE,
    evidence: tuple[str, ...] = ("TEST_SESSION_COMPLETE",),
    last_offset: timedelta = timedelta(minutes=1),
    identity_status: ContractIdentityStatus = ContractIdentityStatus.RESOLVED_AS_OF_QUERY,
) -> SourceObservation:
    window = _calendar().session_window(date(2026, 8, 24), timedelta(minutes=5))
    raw_source_json = canonical_json(
        {
            "source": "TEST_SOURCE",
            "trading_date": window.trading_date,
            "fixture": "night-session-v0",
        }
    )
    return SourceObservation(
        trading_date=window.trading_date,
        contract_identity=ContractIdentity(
            status=identity_status,
            resolution_method="QUERY_TIME_ALIAS" if identity_status is ContractIdentityStatus.RESOLVED_AS_OF_QUERY else "UNRESOLVED",
            resolved_contract_code="TXF202608" if identity_status is ContractIdentityStatus.RESOLVED_AS_OF_QUERY else None,
            delivery_month="202608",
            last_trading_date=date(2026, 8, 19),
        ),
        bars=(
            NightBar(
                timestamp=window.start,
                open=Decimal("24000"),
                high=Decimal("24100"),
                low=Decimal("23910"),
                close=Decimal("24050"),
                volume=10,
            ),
            NightBar(
                timestamp=window.end - last_offset,
                open=Decimal("24050"),
                high=Decimal("24220"),
                low=Decimal("24020"),
                close=Decimal("24180"),
                volume=20,
            ),
        ),
        queried_at=datetime.fromisoformat("2026-08-22T05:07:00+08:00"),
        received_at=datetime.fromisoformat("2026-08-22T05:07:01+08:00"),
        provider_reference_price=Decimal("24000"),
        provider_reference_updated_at=datetime.fromisoformat("2026-08-21T13:45:00+08:00"),
        provider_reference_source="TEST_CONTRACT_INFO",
        completeness_status=completeness,
        completeness_evidence=evidence,
        source="TEST_SOURCE",
        raw_source_digest=sha256_text_digest(raw_source_json),
        raw_source_json=raw_source_json,
    )


def _service(source: FixtureSource, now: datetime) -> PremarketContextService:
    config = replace(
        PREMARKET_CONTEXT_V0,
        qualified_completion_evidence=(("TEST_SOURCE", "TEST_SESSION_COMPLETE"),),
    )
    return PremarketContextService(
        source=source,
        calendar=_calendar(),
        config=config,
        artifacts=InMemoryPremarketArtifactRepository(),
        now=lambda: now,
    )


def test_query_cutoff_does_not_call_source_or_imply_ready() -> None:
    source = FixtureSource(_observation())
    service = _service(source, datetime.fromisoformat("2026-08-22T05:04:59+08:00"))

    projection = service.projection()

    assert projection["status"] == "PENDING"
    assert projection["query_not_before"] == "2026-08-22T05:05:00+08:00"
    assert source.calls == 0


def test_unqualified_completion_after_cutoff_is_not_ready() -> None:
    source = FixtureSource(
        _observation(
            completeness=CompletenessStatus.UNKNOWN,
            evidence=("QUERY_RETURNED_ROWS",),
        )
    )
    service = _service(source, datetime.fromisoformat("2026-08-22T05:07:00+08:00"))

    projection = service.projection()

    assert projection["status"] == "PENDING"
    assert "SOURCE_COMPLETENESS_UNQUALIFIED" in projection["health"]["reasons"]


def test_incomplete_final_window_is_not_ready_even_with_complete_label() -> None:
    source = FixtureSource(_observation(last_offset=timedelta(minutes=2)))
    service = _service(source, datetime.fromisoformat("2026-08-22T05:07:00+08:00"))

    projection = service.projection()

    assert projection["status"] == "PENDING"
    assert "SESSION_END_NOT_OBSERVED" in projection["health"]["reasons"]


def test_qualified_context_exposes_signed_metrics_without_categories_and_caches() -> None:
    source = FixtureSource(_observation())
    service = _service(source, datetime.fromisoformat("2026-08-22T05:07:00+08:00"))

    first = service.projection()
    second = service.projection()

    assert first["status"] == "READY"
    assert first["metrics"]["session_move_pct"] == 0.75
    assert first["metrics"]["session_range_pct"] > 0
    assert first["provider_reference"]["source"] == "TEST_CONTRACT_INFO"
    assert first["reconciliation"]["status"] == "PENDING"
    serialized = json.dumps(first, ensure_ascii=False)
    assert '"direction"' not in serialized
    assert '"regime"' not in serialized
    assert "FLAT" not in serialized
    assert second == first
    assert source.calls == 1


def test_unresolved_live_identity_cannot_be_ready() -> None:
    source = FixtureSource(_observation(identity_status=ContractIdentityStatus.UNRESOLVED))
    service = _service(source, datetime.fromisoformat("2026-08-22T05:07:00+08:00"))

    projection = service.projection()

    assert projection["status"] == "DEGRADED"
    assert projection["contract_identity"]["resolved_contract_code"] is None
    assert "CONTRACT_IDENTITY_UNRESOLVED" in projection["health"]["reasons"]
