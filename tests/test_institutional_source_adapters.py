import json
import ssl
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from institutional_data.application import InstitutionalIngestionService
from institutional_data.artifacts import InMemoryInstitutionalRawArtifactStore
from institutional_data.domain import PartitionStatus
from institutional_data.serialization import deserialize_flow_rows
from institutional_data.sources import (
    TPEX_ENDPOINT,
    TPEX_TRADE_SCOPE_ID,
    TWSE_ENDPOINT,
    TWSE_TRADE_SCOPE_ID,
    InstitutionalSourceResponse,
    TpexInstitutionalSourceAdapter,
    TwseInstitutionalSourceAdapter,
    _official_https_context,
)


FIXTURES = Path(__file__).parent / "fixtures" / "institutional"
SESSION = date(2026, 8, 19)
USABLE_FROM = date(2026, 8, 20)
OBSERVED_AT = datetime.fromisoformat("2026-08-19T20:10:00+08:00")


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_official_https_context_preserves_peer_and_hostname_validation() -> None:
    context = _official_https_context()

    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        assert not context.verify_flags & strict_flag


def response(adapter, body: bytes) -> InstitutionalSourceResponse:  # type: ignore[no-untyped-def]
    if isinstance(adapter, TwseInstitutionalSourceAdapter):
        source_url = (
            f"{TWSE_ENDPOINT}?date=20260819&selectType=ALLBUT0999&response=json"
        )
        method = "GET"
        parameters = (
            ("date", "20260819"),
            ("selectType", "ALLBUT0999"),
            ("response", "json"),
        )
    else:
        source_url = TPEX_ENDPOINT
        method = "POST"
        parameters = (
            ("type", "Daily"),
            ("sect", "EW"),
            ("date", "2026/08/19"),
            ("response", "json"),
        )
    return InstitutionalSourceResponse(
        source_url=source_url,
        request_method=method,
        request_parameters=parameters,
        response_headers=(("Content-Type", "application/json"),),
        content_type="application/json",
        retrieved_at=OBSERVED_AT,
        first_observed_at=OBSERVED_AT,
        body=body,
    )


def ingest(adapter, body: bytes, *, scope: str | None = None, store=None):  # type: ignore[no-untyped-def]
    artifact_store = store or InMemoryInstitutionalRawArtifactStore()
    result = InstitutionalIngestionService(artifact_store).ingest_response(
        adapter,
        response=response(adapter, body),
        requested_session=SESSION,
        usable_from_session=USABLE_FROM,
        requested_trade_scope_id=scope or adapter.trade_scope_id,
    )
    return result, artifact_store


@pytest.mark.parametrize(
    ("adapter", "fixture_name", "symbols"),
    [
        (
            TwseInstitutionalSourceAdapter(),
            "twse_t86_2026-08-19_reviewed_sample.json",
            {"2317", "2330"},
        ),
        (
            TpexInstitutionalSourceAdapter(),
            "tpex_insti_daily_2026-08-19_reviewed_sample.json",
            {"006201", "6488"},
        ),
    ],
)
def test_reviewed_official_samples_replay_to_validated_normalized_artifacts(
    adapter,  # type: ignore[no-untyped-def]
    fixture_name: str,
    symbols: set[str],
) -> None:
    result, _ = ingest(adapter, fixture(fixture_name))

    assert result.is_validated
    assert result.manifest.status is PartitionStatus.VALIDATED
    assert {row.symbol for row in result.rows} == symbols
    assert deserialize_flow_rows(result.normalized_json) == tuple(
        sorted(
            result.rows,
            key=lambda row: (
                row.market.value,
                row.session_date,
                row.symbol,
                row.partition_id,
            ),
        )
    )
    assert all(
        row.raw_artifact_id == result.raw_artifact.artifact_id for row in result.rows
    )


def test_tpex_fetch_uses_the_official_page_date_encoding() -> None:
    adapter = TpexInstitutionalSourceAdapter()
    source_response = response(
        adapter,
        fixture("tpex_insti_daily_2026-08-19_reviewed_sample.json"),
    )

    with patch(
        "institutional_data.sources._fetch_response",
        return_value=source_response,
    ) as fetch_response:
        assert adapter.fetch(SESSION) is source_response

    fetch_response.assert_called_once_with(
        source_url=TPEX_ENDPOINT,
        method="POST",
        parameters=(
            ("type", "Daily"),
            ("sect", "EW"),
            ("date", "2026/08/19"),
            ("response", "json"),
        ),
        timeout_seconds=30.0,
    )


def test_twse_mapping_uses_component_fields_without_double_counting() -> None:
    result, _ = ingest(
        TwseInstitutionalSourceAdapter(),
        fixture("twse_t86_2026-08-19_reviewed_sample.json"),
    )
    row = next(row for row in result.rows if row.symbol == "2330")

    assert row.foreign_ex_dealer_net_shares == -7_417_943
    assert row.foreign_dealer_net_shares == 0
    assert row.investment_trust_net_shares == -668_410
    assert row.dealer_total_buy_shares == 1_154_254
    assert row.dealer_total_sell_shares == 434_912
    assert row.dealer_total_net_shares == 719_342
    assert row.published_total_net_shares == -7_367_011


def test_tpex_mapping_preserves_foreign_and_dealer_component_splits() -> None:
    result, _ = ingest(
        TpexInstitutionalSourceAdapter(),
        fixture("tpex_insti_daily_2026-08-19_reviewed_sample.json"),
    )
    row = next(row for row in result.rows if row.symbol == "6488")

    assert row.foreign_ex_dealer_net_shares == -2_583_248
    assert row.foreign_dealer_net_shares == 0
    assert row.investment_trust_net_shares == 62_000
    assert row.dealer_proprietary_net_shares == -129_991
    assert row.dealer_hedge_net_shares == -154_741
    assert row.dealer_total_net_shares == -284_732
    assert row.published_total_net_shares == -2_805_980


@pytest.mark.parametrize(
    ("adapter", "fixture_name"),
    [
        (
            TwseInstitutionalSourceAdapter(),
            "twse_t86_2026-08-19_reviewed_sample.json",
        ),
        (
            TpexInstitutionalSourceAdapter(),
            "tpex_insti_daily_2026-08-19_reviewed_sample.json",
        ),
    ],
)
def test_response_date_pollution_is_quarantined(
    adapter,  # type: ignore[no-untyped-def]
    fixture_name: str,
) -> None:
    payload = json.loads(fixture(fixture_name))
    payload["date"] = "20260818"

    result, _ = ingest(adapter, json.dumps(payload).encode())

    assert result.manifest.status is PartitionStatus.QUARANTINED
    assert "RESPONSE_DATE_MISMATCH" in {
        issue.code for issue in result.validation_report.issues
    }


def test_schema_drift_empty_table_and_scope_mismatch_are_quarantined() -> None:
    adapter = TwseInstitutionalSourceAdapter()
    base = json.loads(fixture("twse_t86_2026-08-19_reviewed_sample.json"))

    drift = dict(base, unexpected=True)
    drift_result, _ = ingest(adapter, json.dumps(drift).encode())

    empty = dict(base, data=[], total=0)
    empty_result, _ = ingest(adapter, json.dumps(empty).encode())

    scope_result, _ = ingest(
        adapter,
        fixture("twse_t86_2026-08-19_reviewed_sample.json"),
        scope=TPEX_TRADE_SCOPE_ID,
    )

    assert "SCHEMA_DRIFT" in {
        issue.code for issue in drift_result.validation_report.issues
    }
    assert "EMPTY_RESPONSE" in {
        issue.code for issue in empty_result.validation_report.issues
    }
    assert "SCOPE_MISMATCH" in {
        issue.code for issue in scope_result.validation_report.issues
    }
    assert all(
        result.manifest.status is PartitionStatus.QUARANTINED
        for result in (drift_result, empty_result, scope_result)
    )


def test_formula_error_is_quarantined_after_normalization() -> None:
    adapter = TwseInstitutionalSourceAdapter()
    payload = json.loads(fixture("twse_t86_2026-08-19_reviewed_sample.json"))
    payload["data"][0][18] = "1"

    result, _ = ingest(adapter, json.dumps(payload).encode())

    assert result.rows
    assert result.manifest.status is PartitionStatus.QUARANTINED
    assert "PUBLISHED_TOTAL_MISMATCH" in {
        issue.code for issue in result.validation_report.issues
    }


def test_raw_artifact_survives_parser_failure() -> None:
    adapter = TwseInstitutionalSourceAdapter()
    store = InMemoryInstitutionalRawArtifactStore()

    result, _ = ingest(adapter, b"not-json", store=store)

    assert result.manifest.status is PartitionStatus.QUARANTINED
    assert store.get(result.raw_artifact.artifact_id) == result.raw_artifact
    assert store.get(result.raw_artifact.artifact_id).payload == b"not-json"  # type: ignore[union-attr]


def test_same_source_key_changed_content_appends_without_overwriting() -> None:
    adapter = TwseInstitutionalSourceAdapter()
    store = InMemoryInstitutionalRawArtifactStore()
    original = fixture("twse_t86_2026-08-19_reviewed_sample.json")
    revised_payload = json.loads(original)
    revised_payload["title"] += " revision"
    revised = json.dumps(revised_payload, ensure_ascii=False).encode()

    first, _ = ingest(adapter, original, store=store)
    duplicate, _ = ingest(adapter, original, store=store)
    second, _ = ingest(adapter, revised, store=store)

    assert first.raw_artifact.revision == 1
    assert duplicate.raw_artifact.artifact_id == first.raw_artifact.artifact_id
    assert second.raw_artifact.revision == 2
    assert second.raw_artifact.artifact_id != first.raw_artifact.artifact_id
    assert store.get(first.raw_artifact.artifact_id).payload == original  # type: ignore[union-attr]
    assert len(store.revisions(first.raw_artifact.key)) == 2


def test_source_scope_constants_are_not_interchangeable() -> None:
    assert TWSE_TRADE_SCOPE_ID != TPEX_TRADE_SCOPE_ID
