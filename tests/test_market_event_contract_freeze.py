import json
from pathlib import Path

import pytest

from market_data.events import (
    BidAskEvent,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketStreamKind,
    TickEvent,
)
from market_data.serialization import (
    deserialize_event_envelope,
    serialize_event_envelope,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "market_events" / "v1"


@pytest.mark.parametrize(
    ("filename", "stream_kind", "payload_type"),
    (
        ("tick.json", MarketStreamKind.TICK, TickEvent),
        ("bidask.json", MarketStreamKind.BIDASK, BidAskEvent),
    ),
)
def test_market_event_v1_golden_round_trip(
    filename: str,
    stream_kind: MarketStreamKind,
    payload_type: type[TickEvent] | type[BidAskEvent],
):
    canonical_json = (FIXTURE_DIR / filename).read_text(encoding="utf-8").strip()

    envelope = deserialize_event_envelope(canonical_json)

    assert envelope.schema_version == MARKET_EVENT_SCHEMA_VERSION
    assert envelope.stream_kind is stream_kind
    assert isinstance(envelope.payload, payload_type)
    assert serialize_event_envelope(envelope) == canonical_json


def test_market_event_v1_rejects_unknown_schema():
    raw = json.loads((FIXTURE_DIR / "tick.json").read_text(encoding="utf-8"))
    raw["schema_version"] = "market-event-v2"

    with pytest.raises(ValueError, match="unsupported market event schema"):
        deserialize_event_envelope(json.dumps(raw))


def test_market_event_v1_rejects_missing_or_unknown_fields():
    raw = json.loads((FIXTURE_DIR / "tick.json").read_text(encoding="utf-8"))
    del raw["source_identity"]

    with pytest.raises(ValueError, match="envelope fields do not match"):
        deserialize_event_envelope(json.dumps(raw))

    raw = json.loads((FIXTURE_DIR / "tick.json").read_text(encoding="utf-8"))
    raw["event_type"] = "tick"
    with pytest.raises(ValueError, match="envelope fields do not match"):
        deserialize_event_envelope(json.dumps(raw))
