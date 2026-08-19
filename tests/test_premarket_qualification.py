from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from config.premarket import PREMARKET_CONTEXT_V0
from premarket.artifacts import (
    InMemoryPremarketArtifactRepository,
    canonical_json,
    sha256_text_digest,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.models import HistoricalTick, QualificationCapture, QualificationStatus
from premarket.qualification import PremarketQualificationService, QualificationNotEligible
from tests.test_premarket_context import _observation


class FixtureQualificationSource:
    def __init__(self, capture: QualificationCapture) -> None:
        self.capture = capture
        self.calls = 0

    def supports_premarket_qualification(self) -> bool:
        return True

    def capture_taifex_night_qualification(self, window, contract_alias):  # type: ignore[no-untyped-def]
        self.calls += 1
        assert window.trading_date == self.capture.trading_date
        assert contract_alias == "TXFR1"
        return self.capture


def _capture(*, final_tick: Decimal = Decimal("24180")) -> QualificationCapture:
    observation = _observation()
    window = TaifexTradingCalendar.from_path(
        PREMARKET_CONTEXT_V0.calendar_path
    ).session_window(date(2026, 8, 24), timedelta(minutes=5))
    ticks = (
        HistoricalTick(window.start, Decimal("24000"), 5),
        HistoricalTick(window.start + timedelta(minutes=1), Decimal("24220"), 5),
        HistoricalTick(window.end - timedelta(minutes=2), Decimal("23910"), 10),
        HistoricalTick(window.end - timedelta(minutes=1), final_tick, 10),
    )
    raw_json = canonical_json(
        {
            "source": "TEST_KBAR_TICK_CAPTURE",
            "trading_date": window.trading_date,
            "ticks": tuple(
                {"timestamp": tick.timestamp, "close": tick.close, "volume": tick.volume}
                for tick in ticks
            ),
        }
    )
    return QualificationCapture(
        trading_date=window.trading_date,
        contract_identity=observation.contract_identity,
        bars=observation.bars,
        ticks=ticks,
        captured_at=datetime.fromisoformat("2026-08-22T05:10:00+08:00"),
        source="TEST_KBAR_TICK_CAPTURE",
        raw_source_digest=sha256_text_digest(raw_json),
        raw_source_json=raw_json,
    )


def _service(source: FixtureQualificationSource, now: datetime):  # type: ignore[no-untyped-def]
    artifacts = InMemoryPremarketArtifactRepository()
    service = PremarketQualificationService(
        source=source,
        calendar=TaifexTradingCalendar.from_path(PREMARKET_CONTEXT_V0.calendar_path),
        config=PREMARKET_CONTEXT_V0,
        artifacts=artifacts,
        now=lambda: now,
    )
    return service, artifacts


def test_matching_tick_and_kbar_capture_remains_unqualified() -> None:
    source = FixtureQualificationSource(_capture())
    service, artifacts = _service(
        source,
        datetime.fromisoformat("2026-08-22T05:10:00+08:00"),
    )

    report = service.capture()

    assert report.status is QualificationStatus.CAPTURED_UNQUALIFIED
    assert report.field_deltas == (
        ("open", Decimal("0")),
        ("high", Decimal("0")),
        ("low", Decimal("0")),
        ("close", Decimal("0")),
        ("volume", Decimal("0")),
    )
    assert report.reasons == ("SOURCE_COMPLETION_REVIEW_REQUIRED",)
    assert artifacts.raw_source(report.raw_source_digest) is not None
    assert artifacts.raw_source(report.qualification_digest) is not None
    assert source.calls == 1


def test_tick_kbar_mismatch_is_invalid_and_never_complete() -> None:
    source = FixtureQualificationSource(_capture(final_tick=Decimal("24170")))
    service, _ = _service(
        source,
        datetime.fromisoformat("2026-08-22T05:10:00+08:00"),
    )

    report = service.capture()

    assert report.status is QualificationStatus.INVALID
    assert ("close", Decimal("-10")) in report.field_deltas
    assert "TICK_KBAR_MISMATCH" in report.reasons
    assert "SOURCE_COMPLETION_REVIEW_REQUIRED" in report.reasons


def test_qualification_before_query_cutoff_does_not_call_source() -> None:
    source = FixtureQualificationSource(_capture())
    service, _ = _service(
        source,
        datetime.fromisoformat("2026-08-22T05:04:59+08:00"),
    )

    with pytest.raises(QualificationNotEligible):
        service.capture()

    assert source.calls == 0


def test_duplicate_tick_timestamps_are_not_treated_as_reverse_order() -> None:
    capture = _capture()
    duplicate = HistoricalTick(
        capture.ticks[1].timestamp,
        capture.ticks[1].close,
        0,
    )
    capture = QualificationCapture(
        **{
            **capture.__dict__,
            "ticks": capture.ticks[:2] + (duplicate,) + capture.ticks[2:],
        }
    )
    source = FixtureQualificationSource(capture)
    service, _ = _service(
        source,
        datetime.fromisoformat("2026-08-22T05:10:00+08:00"),
    )

    report = service.capture()

    assert report.status is QualificationStatus.CAPTURED_UNQUALIFIED
    assert "TICK_ORDER_INVALID" not in report.reasons
