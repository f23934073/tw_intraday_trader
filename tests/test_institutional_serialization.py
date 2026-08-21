import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from institutional_data.serialization import (
    PARTITION_MANIFEST_SCHEMA_VERSION,
    PARTITION_MANIFEST_V1_FIELDS,
    InstitutionalSerializationError,
    canonical_json,
    deserialize_flow_rows,
    deserialize_partition_manifest,
    flow_rows_sha256,
    serialize_flow_rows,
    serialize_partition_manifest,
)
from institutional_data.domain import PARTITION_STATUS_V1_VALUES


FIXTURES = Path(__file__).parent / "fixtures" / "institutional"


@pytest.mark.parametrize("market", ["twse", "tpex"])
def test_normalized_flow_fixture_round_trips_canonically(market: str) -> None:
    path = FIXTURES / f"{market}_flow_rows_valid.json"
    payload = path.read_text(encoding="utf-8")

    rows = deserialize_flow_rows(payload)
    canonical = canonical_json(json.loads(payload))

    assert serialize_flow_rows(rows) == canonical
    assert (
        flow_rows_sha256(rows) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )


@pytest.mark.parametrize("market", ["twse", "tpex"])
def test_partition_manifest_fixture_round_trips_canonically(market: str) -> None:
    path = FIXTURES / f"{market}_partition_manifest_valid.json"
    payload = path.read_text(encoding="utf-8")

    manifest = deserialize_partition_manifest(payload)

    assert serialize_partition_manifest(manifest) == canonical_json(json.loads(payload))


def test_partition_manifest_v1_contract_is_frozen() -> None:
    assert PARTITION_MANIFEST_SCHEMA_VERSION == "institutional_partition_manifest_v1"
    assert PARTITION_MANIFEST_V1_FIELDS == (
        "partition_id",
        "market",
        "session_date",
        "source_product",
        "trade_scope_id",
        "correction_policy",
        "response_scope_note",
        "raw_artifact_id",
        "raw_sha256",
        "normalized_sha256",
        "retrieved_at",
        "first_observed_at",
        "usable_from_session",
        "source_row_count",
        "normalized_row_count",
        "status",
    )
    assert PARTITION_STATUS_V1_VALUES == (
        "RAW_CAPTURED",
        "NORMALIZED",
        "VALIDATED",
        "QUARANTINED",
    )


@pytest.mark.parametrize(
    ("fixture_name", "expected_sha256"),
    [
        (
            "tpex_partition_manifest_valid.json",
            "36c9287a01d6defdd2b5fbba93818a888372a5258efc2f350a1c18dfe47e43e0",
        ),
        (
            "twse_partition_manifest_valid.json",
            "d592da9dd49ea8102eadd6a15ca65c822351a637e9f98508cada440eb4721645",
        ),
    ],
)
def test_partition_manifest_v1_golden_bytes_are_stable(
    fixture_name: str,
    expected_sha256: str,
) -> None:
    payload = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    manifest = deserialize_partition_manifest(payload)

    assert (
        hashlib.sha256(
            serialize_partition_manifest(manifest).encode("utf-8")
        ).hexdigest()
        == expected_sha256
    )


def test_canonical_json_preserves_decimal_text_and_rejects_float() -> None:
    assert canonical_json({"ratio": Decimal("0.100")}) == '{"ratio":"0.100"}'
    with pytest.raises(InstitutionalSerializationError, match="float"):
        canonical_json({"ratio": 0.1})


def test_canonical_json_rejects_naive_datetime() -> None:
    with pytest.raises(InstitutionalSerializationError, match="timezone"):
        canonical_json({"retrieved_at": datetime(2026, 8, 19, 20, 10)})


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload.update({"schema_version": "unknown"}),
            "schema_version",
        ),
        (
            lambda payload: payload["rows"][0].update({"unexpected": 1}),
            "unexpected fields",
        ),
        (
            lambda payload: payload["rows"][0].update(
                {"foreign_ex_dealer_buy_shares": "10000"}
            ),
            "integer",
        ),
        (
            lambda payload: payload["rows"][0].update({"session_date": 20260819}),
            "string",
        ),
    ],
)
def test_flow_deserialization_rejects_schema_drift(
    mutate,  # type: ignore[no-untyped-def]
    message: str,
) -> None:
    payload = json.loads(
        (FIXTURES / "twse_flow_rows_valid.json").read_text(encoding="utf-8")
    )
    mutate(payload)

    with pytest.raises(InstitutionalSerializationError, match=message):
        deserialize_flow_rows(json.dumps(payload))


def test_deserialization_rejects_non_object_json() -> None:
    with pytest.raises(InstitutionalSerializationError, match="object"):
        deserialize_partition_manifest("[]")
