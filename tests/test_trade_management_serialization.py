import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.trade_management_builders import (
    build_exit_recommendation,
    build_replay_verification,
    build_trade_outcome,
    build_trade_thesis,
)
from trading.trade_management_serialization import (
    TradeManagementDeserializationError,
    deserialize_exit_recommendation,
    deserialize_trade_outcome,
    deserialize_trade_thesis,
    deserialize_trade_thesis_draft,
    serialize_exit_recommendation,
    serialize_lifecycle_contract,
    serialize_replay_verification,
    serialize_trade_outcome,
    serialize_trade_thesis,
    serialize_trade_thesis_draft,
)
from trading.canonical_values import canonical_decimal_string


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "trade_management" / "v1"


@pytest.mark.parametrize(
    ("filename", "actual"),
    (
        ("trade_thesis.json", serialize_trade_thesis(build_trade_thesis())),
        (
            "exit_recommendation.json",
            serialize_exit_recommendation(build_exit_recommendation()),
        ),
        ("trade_outcome.json", serialize_trade_outcome(build_trade_outcome())),
        (
            "replay_verification.json",
            serialize_replay_verification(build_replay_verification()),
        ),
        ("lifecycle.json", serialize_lifecycle_contract()),
    ),
)
def test_trade_management_v1_golden_serialization(filename: str, actual: str):
    expected = (FIXTURE_DIR / filename).read_text(encoding="utf-8").strip()

    assert actual == expected


def test_same_replay_contract_serializes_identically_ten_times():
    verification = build_replay_verification()

    outputs = {
        serialize_replay_verification(verification)
        for _iteration in range(10)
    }

    assert len(outputs) == 1


@pytest.mark.parametrize(
    ("value", "serializer", "deserializer"),
    (
        (
            build_trade_thesis().draft,
            serialize_trade_thesis_draft,
            deserialize_trade_thesis_draft,
        ),
        (build_trade_thesis(), serialize_trade_thesis, deserialize_trade_thesis),
        (
            build_exit_recommendation(),
            serialize_exit_recommendation,
            deserialize_exit_recommendation,
        ),
        (build_trade_outcome(), serialize_trade_outcome, deserialize_trade_outcome),
    ),
)
def test_journal_aggregate_contracts_round_trip_exactly(
    value,
    serializer,
    deserializer,
):
    assert deserializer(serializer(value)) == value


def test_draft_envelope_matches_the_frozen_nested_thesis_representation():
    thesis = build_trade_thesis()
    draft_envelope = json.loads(serialize_trade_thesis_draft(thesis.draft))
    thesis_envelope = json.loads(serialize_trade_thesis(thesis))

    assert draft_envelope == {
        "contract_type": "TradeThesisDraft",
        "payload": thesis_envelope["payload"]["draft"],
        "schema_version": thesis_envelope["schema_version"],
    }


def test_decimal_canonicalization_matches_frozen_golden_contract():
    fixture = json.loads(
        (FIXTURE_DIR / "decimal_canonicalization.json").read_text(encoding="utf-8")
    )

    assert {
        raw: canonical_decimal_string(Decimal(raw))
        for raw in fixture
    } == fixture


def test_equivalent_decimal_inputs_have_one_json_digest_and_record_identity():
    theses = tuple(
        replace(build_trade_thesis(), entry_reference_price=Decimal(raw))
        for raw in ("100", "100.0", "100.00", "1E+2")
    )

    serialized = {serialize_trade_thesis(thesis) for thesis in theses}

    assert len(serialized) == 1
    assert json.loads(serialized.pop())["payload"]["entry_reference_price"] == "100"


def test_v1_reader_fails_closed_for_unknown_schema_field_and_enum_value():
    serialized = serialize_trade_thesis(build_trade_thesis())
    unknown_schema = json.loads(serialized)
    unknown_schema["schema_version"] = "trade-management-v2"
    with pytest.raises(TradeManagementDeserializationError, match="unsupported"):
        deserialize_trade_thesis(json.dumps(unknown_schema))

    unknown_field = json.loads(serialized)
    unknown_field["payload"]["future_field"] = "not-v1"
    with pytest.raises(TradeManagementDeserializationError, match="fields mismatch"):
        deserialize_trade_thesis(json.dumps(unknown_field))

    unknown_enum = json.loads(serialized)
    unknown_enum["payload"]["draft"]["side"] = "SHORT"
    with pytest.raises(TradeManagementDeserializationError, match="unsupported v1 value"):
        deserialize_trade_thesis(json.dumps(unknown_enum))

    noncanonical_decimal = json.loads(serialized)
    noncanonical_decimal["payload"]["entry_reference_price"] = "+600.5"
    with pytest.raises(TradeManagementDeserializationError, match="canonical decimal"):
        deserialize_trade_thesis(json.dumps(noncanonical_decimal))

    duplicate_key = serialized.replace(
        '"contract_type":"TradeThesis"',
        '"contract_type":"TradeThesis","contract_type":"TradeThesis"',
        1,
    )
    with pytest.raises(TradeManagementDeserializationError, match="duplicate"):
        deserialize_trade_thesis(duplicate_key)


@pytest.mark.parametrize(
    "raw",
    ("100.0", "100.00", "100.50", "-0", "-0.00", "1E+2"),
)
def test_v1_reader_rejects_noncanonical_decimal_artifacts(raw: str):
    payload = json.loads(serialize_trade_thesis(build_trade_thesis()))
    payload["payload"]["entry_reference_price"] = raw

    with pytest.raises(TradeManagementDeserializationError, match="canonical decimal"):
        deserialize_trade_thesis(json.dumps(payload))


def test_v1_reader_rejects_json_number_for_decimal_field():
    payload = json.loads(serialize_trade_thesis(build_trade_thesis()))
    payload["payload"]["entry_reference_price"] = 100

    with pytest.raises(TradeManagementDeserializationError, match="must be a string"):
        deserialize_trade_thesis(json.dumps(payload))
