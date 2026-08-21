from datetime import date, datetime

from institutional_data.artifacts import (
    DirectoryInstitutionalRawArtifactStore,
    InMemoryInstitutionalRawArtifactStore,
    InstitutionalRawArtifactKey,
    InstitutionalRawCapture,
)
from institutional_data.domain import InstitutionalMarket


KEY = InstitutionalRawArtifactKey(
    market=InstitutionalMarket.TWSE,
    session_date=date(2026, 8, 19),
    source_product="TWSE_T86_FINAL",
    trade_scope_id="TWSE_T86_FINAL_WITH_BLOCK_V1",
)
OBSERVED_AT = datetime.fromisoformat("2026-08-19T20:10:00+08:00")


def capture(payload: bytes) -> InstitutionalRawCapture:
    return InstitutionalRawCapture(
        key=KEY,
        source_url=(
            "https://www.twse.com.tw/rwd/zh/fund/T86?"
            "date=20260819&selectType=ALLBUT0999&response=json"
        ),
        request_method="GET",
        request_parameters=(
            ("date", "20260819"),
            ("selectType", "ALLBUT0999"),
            ("response", "json"),
        ),
        response_headers=(("Content-Type", "application/json"),),
        content_type="application/json",
        parser_version="twse_t86_json_v1",
        retrieved_at=OBSERVED_AT,
        first_observed_at=OBSERVED_AT,
        payload=payload,
    )


def test_same_key_same_bytes_is_idempotent_and_changed_bytes_append_revision() -> None:
    store = InMemoryInstitutionalRawArtifactStore()

    first = store.capture(capture(b'{"version":1}'))
    duplicate = store.capture(capture(b'{"version":1}'))
    changed = store.capture(capture(b'{"version":2}'))

    assert duplicate is first
    assert first.revision == 1
    assert changed.revision == 2
    assert changed.artifact_id != first.artifact_id
    assert store.revisions(KEY) == (first, changed)
    assert store.get(first.artifact_id) == first
    assert first.payload == b'{"version":1}'


def test_directory_store_reloads_raw_bytes_and_revisions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = DirectoryInstitutionalRawArtifactStore(tmp_path)
    first = store.capture(capture(b'{"version":1}'))
    second = store.capture(capture(b'{"version":2}'))

    reloaded = DirectoryInstitutionalRawArtifactStore(tmp_path)

    assert reloaded.get(first.artifact_id) == first
    assert reloaded.revisions(KEY) == (first, second)
    assert reloaded.revisions(KEY)[0].payload == b'{"version":1}'
