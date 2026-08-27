"""Daily FinMind institutional MVP application and provider adapter tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backtest.finmind_history import FinMindRequestError, FinMindResponse, FinMindUsage
from config import twse_calendar_2026
from config.institutional_mvp import (
    CALENDAR_SCOPE,
    EXPECTED_BASE_POLICY_DIGEST,
    EXPECTED_CALENDAR_SCHEMA_VERSION,
    EXPECTED_CALENDAR_SOURCE_DIGEST,
    EXPECTED_CALENDAR_TIMEZONE,
    load_daily_policy,
)
from institutional_mvp.application import DailyInstitutionalMvpService
from institutional_mvp.artifacts import (
    DirectoryInstitutionalMvpCandidateBatchRepository,
)
from institutional_mvp.domain import (
    DailyRunStatus,
    InstitutionalMvpDailyError,
    InstitutionalMvpSourceNotReady,
)
from institutional_mvp.finmind_adapter import (
    FLOW_DATASET,
    STOCK_INFO_DATASET,
    FinMindInstitutionalFlowProvider,
)
from institutional_mvp.ports import InstitutionalFlowSnapshot
from market_data.equity_calendar import ReviewedEquityCalendar


TAIPEI = ZoneInfo("Asia/Taipei")
GENERATED_AT = datetime(2026, 8, 21, 18, 0, tzinfo=TAIPEI)


def _payload(rows: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"status": 200, "msg": "success", "data": rows},
        separators=(",", ":"),
    ).encode()


def _wide_row(
    source_session: date,
    *,
    symbol: str = "1101",
    foreign_buy: int = 10,
) -> dict[str, object]:
    return {
        "Dealer_Hedging_buy": 1,
        "Dealer_Hedging_sell": 0,
        "Dealer_buy": 0,
        "Dealer_self_buy": 2,
        "Dealer_self_sell": 0,
        "Dealer_sell": 0,
        "Foreign_Investor_buy": foreign_buy,
        "Foreign_Investor_sell": 1,
        "Investment_Trust_buy": 5,
        "Investment_Trust_sell": 1,
        "date": source_session.isoformat(),
        "stock_id": symbol,
    }


def _stock_info(symbol: str = "1101") -> bytes:
    return _payload(
        [
            {
                "date": "2026-01-01",
                "stock_id": symbol,
                "stock_name": "Company A",
                "type": "twse",
            }
        ]
    )


class FakeProvider:
    def __init__(self, snapshot: InstitutionalFlowSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[date] = []

    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        self.calls.append(source_session)
        return self.snapshot


def _snapshot(
    source_session: date,
    *,
    wide_rows: list[dict[str, object]] | None = None,
    stock_info_payload: bytes | None = None,
) -> InstitutionalFlowSnapshot:
    rows = wide_rows if wide_rows is not None else [_wide_row(source_session)]
    info = stock_info_payload if stock_info_payload is not None else _stock_info()
    return InstitutionalFlowSnapshot(
        provider="FINMIND",
        source_version="FINMIND_API_V4",
        retrieved_at=GENERATED_AT,
        wide_payload=_payload(rows),
        stock_info_payload=info,
        wide_row_count=len(rows),
        stock_info_row_count=len(json.loads(info)["data"]),
        usage_user_count_before=100,
        usage_request_limit=1000,
        usage_remaining_before=900,
    )


def _service(
    tmp_path: Path,
    provider: FakeProvider,
    *,
    calendar_scope: str = CALENDAR_SCOPE,
    clock=lambda: GENERATED_AT,
) -> DailyInstitutionalMvpService:
    policy = load_daily_policy()
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    return DailyInstitutionalMvpService(
        provider=provider,
        repository=DirectoryInstitutionalMvpCandidateBatchRepository(
            tmp_path,
            calendar=calendar,
            expected_policy_digest=policy.canonical_sha256,
            expected_base_policy_digest=EXPECTED_BASE_POLICY_DIGEST,
            expected_calendar_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        ),
        calendar=calendar,
        policy=policy,
        expected_calendar_schema_version=EXPECTED_CALENDAR_SCHEMA_VERSION,
        expected_calendar_timezone=EXPECTED_CALENDAR_TIMEZONE,
        expected_calendar_source_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        calendar_scope=calendar_scope,
        clock=clock,
    )


def test_daily_batch_resolves_next_session_and_publishes_provider_neutral_entry(
    tmp_path: Path,
) -> None:
    source_session = date(2026, 8, 21)
    provider = FakeProvider(_snapshot(source_session))

    publication = _service(tmp_path, provider).run(source_session)
    payload = json.loads(publication.path.read_text(encoding="utf-8"))

    assert publication.status is DailyRunStatus.PUBLISHED
    assert publication.target_session == date(2026, 8, 24)
    assert payload["expires_at"] == "2026-08-24T13:30:00+08:00"
    assert payload["calendar_evidence"]["scope"] == CALENDAR_SCOPE
    assert payload["research_eligibility"] == {
        "formal_pit_eligible": False,
        "research_eligible": False,
    }
    assert payload["evidence_scope"]["price_or_kbar_read"] is False
    assert payload["evidence_scope"]["return_or_pnl_read"] is False
    assert payload["execution_permissions"]["order_submission_allowed"] is False
    assert set(payload["candidate_observation"]["candidates"][0]) == {
        "entry_digest",
        "expires_at",
        "market",
        "name",
        "rank",
        "source_session",
        "symbol",
        "target_session",
    }
    assert provider.calls == [source_session]


def test_empty_wide_payload_is_source_not_ready_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    source_session = date(2026, 8, 21)
    provider = FakeProvider(_snapshot(source_session, wide_rows=[]))

    with pytest.raises(InstitutionalMvpSourceNotReady):
        _service(tmp_path, provider).run(source_session)

    assert list(tmp_path.rglob("*.json")) == []


def test_calendar_failure_happens_before_provider_call(tmp_path: Path) -> None:
    provider = FakeProvider(_snapshot(date(2026, 8, 22)))

    with pytest.raises(InstitutionalMvpDailyError) as captured:
        _service(tmp_path, provider).run(date(2026, 8, 22))

    assert captured.value.code == "CALENDAR_SESSION_UNAVAILABLE"
    assert provider.calls == []


def test_calendar_digest_drift_happens_before_provider_call(tmp_path: Path) -> None:
    source_session = date(2026, 8, 21)
    provider = FakeProvider(_snapshot(source_session))
    calendar = replace(
        ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        source_digest="0" * 64,
    )
    policy = load_daily_policy()
    service = DailyInstitutionalMvpService(
        provider=provider,
        repository=DirectoryInstitutionalMvpCandidateBatchRepository(
            tmp_path,
            calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
            expected_policy_digest=policy.canonical_sha256,
            expected_base_policy_digest=EXPECTED_BASE_POLICY_DIGEST,
            expected_calendar_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        ),
        calendar=calendar,
        policy=policy,
        expected_calendar_schema_version=EXPECTED_CALENDAR_SCHEMA_VERSION,
        expected_calendar_timezone=EXPECTED_CALENDAR_TIMEZONE,
        expected_calendar_source_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        calendar_scope=CALENDAR_SCOPE,
        clock=lambda: GENERATED_AT,
    )

    with pytest.raises(InstitutionalMvpDailyError) as captured:
        service.run(source_session)

    assert captured.value.code == "CALENDAR_CONTRACT_DRIFT"
    assert provider.calls == []
    assert list(tmp_path.rglob("*.json")) == []


def test_calendar_scope_drift_happens_before_provider_call(tmp_path: Path) -> None:
    source_session = date(2026, 8, 21)
    provider = FakeProvider(_snapshot(source_session))

    with pytest.raises(InstitutionalMvpDailyError) as captured:
        _service(tmp_path, provider, calendar_scope="BAD_SCOPE").run(source_session)

    assert captured.value.code == "CALENDAR_CONTRACT_DRIFT"
    assert provider.calls == []
    assert list(tmp_path.rglob("*.json")) == []


def test_wrong_source_date_and_zero_mapping_fail_closed(tmp_path: Path) -> None:
    requested = date(2026, 8, 21)
    wrong = FakeProvider(_snapshot(requested, wide_rows=[_wide_row(date(2026, 8, 20))]))
    with pytest.raises(InstitutionalMvpDailyError) as wrong_date:
        _service(tmp_path / "wrong", wrong).run(requested)
    assert wrong_date.value.code == "SOURCE_SCHEMA_INVALID"

    unmapped = FakeProvider(
        _snapshot(requested, wide_rows=[_wide_row(requested, symbol="9999")])
    )
    with pytest.raises(InstitutionalMvpDailyError) as no_mapping:
        _service(tmp_path / "unmapped", unmapped).run(requested)
    assert no_mapping.value.code == "STOCK_INFO_MAPPING_UNAVAILABLE"


def test_snapshot_row_count_must_match_raw_payload(tmp_path: Path) -> None:
    source_session = date(2026, 8, 21)
    mismatched = replace(_snapshot(source_session), wide_row_count=2)
    provider = FakeProvider(mismatched)

    with pytest.raises(InstitutionalMvpDailyError) as captured:
        _service(tmp_path, provider).run(source_session)

    assert captured.value.code == "SOURCE_METADATA_MISMATCH"
    assert list(tmp_path.rglob("*.json")) == []


def test_nonempty_flow_with_zero_candidates_is_valid_empty_batch(
    tmp_path: Path,
) -> None:
    source_session = date(2026, 8, 21)
    provider = FakeProvider(
        _snapshot(
            source_session,
            wide_rows=[_wide_row(source_session, foreign_buy=0)],
        )
    )

    publication = _service(tmp_path, provider).run(source_session)
    payload = json.loads(publication.path.read_text(encoding="utf-8"))

    assert publication.status is DailyRunStatus.PUBLISHED
    assert payload["candidate_observation"] == {"candidates": [], "count": 0}
    assert payload["source_evidence"]["mapped_flow_rows"] == 1


class FakeClient:
    def __init__(self, *, remaining: int = 500, empty_wide: bool = False) -> None:
        self.remaining = remaining
        self.empty_wide = empty_wide
        self.data_calls: list[dict[str, object]] = []

    def usage(self) -> FinMindUsage:
        return FinMindUsage(user_count=1000 - self.remaining, api_request_limit=1000)

    def data(self, **kwargs: object) -> FinMindResponse:
        self.data_calls.append(dict(kwargs))
        dataset = kwargs["dataset"]
        body = (
            _payload([] if self.empty_wide else [_wide_row(date(2026, 8, 21))])
            if dataset == FLOW_DATASET
            else _stock_info()
        )
        return FinMindResponse(
            http_status=200,
            body=body,
            payload=json.loads(body),
        )


class RejectedClient(FakeClient):
    def __init__(
        self, *, http_status: int, payload_status: int, remaining: int = 500
    ) -> None:
        super().__init__(remaining=remaining)
        self.http_status = http_status
        self.payload_status = payload_status

    def data(self, **kwargs: object) -> FinMindResponse:
        self.data_calls.append(dict(kwargs))
        body = json.dumps(
            {"status": self.payload_status, "msg": "provider failure detail"}
        ).encode()
        raise FinMindRequestError(
            "FinMind request was rejected",
            response=FinMindResponse(
                http_status=self.http_status,
                body=body,
                payload=json.loads(body),
            ),
        )


def test_finmind_adapter_uses_only_allowlisted_datasets_and_exact_session(
    tmp_path: Path,
) -> None:
    client = FakeClient()
    provider = FinMindInstitutionalFlowProvider(
        "secret-token",
        minimum_remaining_after_batch=100,
        acquisition_lock_path=tmp_path / "acquisition.lock",
        client_factory=lambda token: client,  # type: ignore[arg-type,return-value]
        clock=lambda: GENERATED_AT,
    )

    snapshot = provider.fetch_daily(date(2026, 8, 21))

    assert snapshot.wide_row_count == 1
    assert client.data_calls == [
        {
            "dataset": FLOW_DATASET,
            "start_date": date(2026, 8, 21),
        },
        {"dataset": STOCK_INFO_DATASET},
    ]


def test_finmind_adapter_quota_preflight_sends_no_data_request(tmp_path: Path) -> None:
    client = FakeClient(remaining=101)
    provider = FinMindInstitutionalFlowProvider(
        "secret-token",
        minimum_remaining_after_batch=100,
        acquisition_lock_path=tmp_path / "acquisition.lock",
        client_factory=lambda token: client,  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(InstitutionalMvpDailyError) as captured:
        provider.fetch_daily(date(2026, 8, 21))

    assert captured.value.code == "PROVIDER_QUOTA_INSUFFICIENT"
    assert client.data_calls == []


def test_finmind_adapter_empty_wide_short_circuits_stock_info(tmp_path: Path) -> None:
    client = FakeClient(remaining=102, empty_wide=True)
    provider = FinMindInstitutionalFlowProvider(
        "secret-token",
        minimum_remaining_after_batch=100,
        acquisition_lock_path=tmp_path / "acquisition.lock",
        client_factory=lambda token: client,  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(InstitutionalMvpSourceNotReady):
        provider.fetch_daily(date(2026, 8, 21))

    assert client.data_calls == [
        {"dataset": FLOW_DATASET, "start_date": date(2026, 8, 21)}
    ]


@pytest.mark.parametrize(
    ("http_status", "payload_status", "expected_code"),
    [
        (400, 400, "PROVIDER_REQUEST_REJECTED"),
        (403, 403, "PROVIDER_ACCESS_DENIED"),
        (200, 400, "PROVIDER_REQUEST_REJECTED"),
        (200, 402, "PROVIDER_QUOTA_REACHED"),
        (200, 408, "PROVIDER_REQUEST_FAILED"),
        (200, 429, "PROVIDER_REQUEST_FAILED"),
        (200, 500, "PROVIDER_REQUEST_FAILED"),
        (200, 503, "PROVIDER_REQUEST_FAILED"),
        (200, 200, "PROVIDER_RESPONSE_INVALID"),
        (429, 429, "PROVIDER_REQUEST_FAILED"),
        (500, 500, "PROVIDER_REQUEST_FAILED"),
    ],
)
def test_finmind_adapter_classifies_permanent_and_temporary_failures(
    tmp_path: Path, http_status: int, payload_status: int, expected_code: str
) -> None:
    client = RejectedClient(
        http_status=http_status,
        payload_status=payload_status,
        remaining=102,
    )
    provider = FinMindInstitutionalFlowProvider(
        "secret-token",
        minimum_remaining_after_batch=100,
        acquisition_lock_path=tmp_path / "acquisition.lock",
        client_factory=lambda token: client,  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(InstitutionalMvpDailyError) as captured:
        provider.fetch_daily(date(2026, 8, 21))

    assert captured.value.code == expected_code
