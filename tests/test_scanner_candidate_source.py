"""Scanner and non-streaming Candidate source tests."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from candidate.models import Candidate, CandidateSource
from candidate.sources import (
    AutoCandidateSource,
    ManualCandidateSource,
    MarketScannerCandidateSource,
    PositionCandidateSource,
)
from market_data.scanner import (
    ScannerRankType,
    ScannerResponse,
    ScannerRow,
    ShioajiScannerClient,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def at(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 18, 9, minute, second, tzinfo=TAIPEI)


class FakeScannerClient:
    def __init__(self, responses: dict[ScannerRankType, ScannerResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[ScannerRankType, int, bool]] = []

    def scan(self, rank_type, *, count, ascending):
        self.calls.append((rank_type, count, ascending))
        return self.responses[rank_type]


def response(
    rank_type: ScannerRankType,
    minute: int,
    symbols: tuple[str, ...],
) -> ScannerResponse:
    return ScannerResponse(
        rank_type=rank_type,
        observed_at=at(minute),
        ascending=False,
        requested_count=200,
        rows=tuple(
            ScannerRow(symbol=symbol, rank=index, fields={"code": symbol})
            for index, symbol in enumerate(symbols, start=1)
        ),
    )


def test_scanner_source_unions_rankings_deduplicates_and_archives_responses():
    client = FakeScannerClient(
        {
            ScannerRankType.CHANGE_PERCENT: response(
                ScannerRankType.CHANGE_PERCENT,
                1,
                ("2330", "8039", "0050"),
            ),
            ScannerRankType.VOLUME: response(
                ScannerRankType.VOLUME,
                1,
                ("8039", "2454"),
            ),
        }
    )
    source = MarketScannerCandidateSource(
        client,
        rank_types=(
            ScannerRankType.CHANGE_PERCENT,
            ScannerRankType.VOLUME,
        ),
        count_per_rank=200,
        ttl=timedelta(minutes=2),
        priority=30,
        instrument_eligible=lambda symbol: symbol != "0050",
    )

    discoveries = source.discover()
    by_symbol = {item.symbol: item for item in discoveries}

    assert tuple(by_symbol) == ("2330", "2454", "8039")
    assert by_symbol["8039"].source is CandidateSource.SCANNER
    assert by_symbol["8039"].rank_types == ("CHANGE_PERCENT", "VOLUME")
    assert by_symbol["8039"].best_rank == 1
    assert by_symbol["8039"].expires_at == at(1) + timedelta(minutes=2)
    assert by_symbol["8039"].evidence["rank_by_type"] == {
        "CHANGE_PERCENT": 2,
        "VOLUME": 1,
    }
    assert len(source.responses) == 2
    assert all(len(item.digest) == 64 for item in source.responses)
    assert client.calls == [
        (ScannerRankType.CHANGE_PERCENT, 200, False),
        (ScannerRankType.VOLUME, 200, False),
    ]


def test_existing_auto_manual_and_position_sources_normalize_without_stock_data():
    observed_at = at(2)
    auto = AutoCandidateSource(ttl=timedelta(minutes=1), priority=20)
    auto_items = auto.discover(
        [
            Candidate(
                symbol="8039",
                sources={CandidateSource.AUTO},
                matched_rules=["gap_up", "high_volume"],
            ),
            Candidate(symbol="2330", sources={CandidateSource.MANUAL}),
        ],
        observed_at=observed_at,
    )
    manual_items = ManualCandidateSource(priority=100).discover(
        [" 8039 ", "8039", "2330"],
        observed_at=observed_at,
    )
    position_items = PositionCandidateSource(priority=200).discover(
        ["2454"],
        observed_at=observed_at,
    )

    assert [item.symbol for item in auto_items] == ["8039"]
    assert auto_items[0].rank_types == ("gap_up", "high_volume")
    assert auto_items[0].expires_at == observed_at + timedelta(minutes=1)
    assert [item.symbol for item in manual_items] == ["2330", "8039"]
    assert all(item.expires_at is None for item in manual_items)
    assert position_items[0].source is CandidateSource.POSITION


class FakeShioajiScannerAPI:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def scanners(self, **kwargs):
        self.calls.append(kwargs)
        return [
            SimpleNamespace(
                code="8039",
                name="台虹",
                close=278.0,
                change_percent=8.5,
                volume=11_112,
            ),
            {"code": "2330", "close": 980.0, "volume": 3_000},
            SimpleNamespace(code=""),
        ]


def test_shioaji_scanner_adapter_maps_rows_and_preserves_native_call_contract():
    api = FakeShioajiScannerAPI()
    client = ShioajiScannerClient(
        api,
        clock=lambda: at(3),
        native_rank_types={ScannerRankType.VOLUME: "volume-rank"},
    )

    result = client.scan(ScannerRankType.VOLUME, count=2, ascending=False)

    assert api.calls == [
        {
            "scanner_type": "volume-rank",
            "ascending": False,
            "count": 2,
        }
    ]
    assert [row.symbol for row in result.rows] == ["8039", "2330"]
    assert result.rows[0].fields["name"] == "台虹"
    assert result.rows[0].fields["change_percent"] == 8.5
    assert result.rows[1].rank == 2


def test_scanner_response_digest_is_deterministic():
    first = response(ScannerRankType.TICK_COUNT, 4, ("8039", "2330"))
    second = response(ScannerRankType.TICK_COUNT, 4, ("8039", "2330"))

    assert first.digest == second.digest


def test_scanner_and_candidate_evidence_are_deeply_immutable():
    mutable_fields = {"code": "8039", "nested": {"values": [1, 2]}}
    row = ScannerRow(symbol="8039", rank=1, fields=mutable_fields)
    mutable_fields["nested"]["values"].append(3)

    assert row.fields["nested"]["values"] == (1, 2)
    with pytest.raises(TypeError):
        row.fields["nested"]["new"] = "mutated"
