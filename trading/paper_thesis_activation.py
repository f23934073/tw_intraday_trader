"""Activate an immutable TradeThesis from an audited local-paper BUY fill."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from trading.journal import JournalRecord
from trading.local_paper import (
    LOCAL_PAPER_FILL_KIND,
    LocalPaperFill,
    LocalPaperSide,
)
from trading.trade_management import (
    TimestampRole,
    TimestampSource,
    TAIPEI,
    TradeThesis,
    TradeThesisDraft,
    TradeTimestamp,
    build_trade_id,
)


PAPER_FILL_THESIS_ACTIVATION_VERSION = "paper-fill-thesis-activation-v1"


class PaperFillSource(StrEnum):
    PAPER_SIMULATION = "paper_simulation"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _require_digest(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def paper_thesis_entry_idempotency_key(draft: TradeThesisDraft) -> str:
    """Return the pre-fill correlation key for one immutable Thesis draft."""

    return f"paper-thesis:{draft.thesis_id}"


@dataclass(frozen=True)
class PaperFillProvenance:
    version: str
    fill_source: PaperFillSource
    provider_identity: str
    execution_authority: bool
    fill_record_id: str
    fill_record_fingerprint: str
    command_id: str
    command_idempotency_key: str
    order_id: str
    quantity_shares: int

    def __post_init__(self) -> None:
        if self.version != PAPER_FILL_THESIS_ACTIVATION_VERSION:
            raise ValueError("unsupported paper fill Thesis activation version")
        for value, field_name in (
            (self.provider_identity, "provider_identity"),
            (self.fill_record_id, "fill_record_id"),
            (self.command_id, "command_id"),
            (self.command_idempotency_key, "command_idempotency_key"),
            (self.order_id, "order_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        _require_digest(self.fill_record_fingerprint, "fill_record_fingerprint")
        if self.execution_authority:
            raise ValueError("paper fill provenance cannot grant execution authority")
        if self.quantity_shares <= 0:
            raise ValueError("quantity_shares must be positive")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "fill_source": self.fill_source.value,
                "provider_identity": self.provider_identity,
                "execution_authority": self.execution_authority,
                "fill_record_id": self.fill_record_id,
                "fill_record_fingerprint": self.fill_record_fingerprint,
                "command_id": self.command_id,
                "command_idempotency_key": self.command_idempotency_key,
                "order_id": self.order_id,
                "quantity_shares": self.quantity_shares,
            }
        )


@dataclass(frozen=True)
class PaperFillThesisActivation:
    version: str
    activation_id: str
    input_digest: str
    thesis: TradeThesis
    provenance: PaperFillProvenance

    def __post_init__(self) -> None:
        if self.version != PAPER_FILL_THESIS_ACTIVATION_VERSION:
            raise ValueError("unsupported paper fill Thesis activation version")
        _require_digest(self.input_digest, "input_digest")
        if self.activation_id != f"paper_fill_thesis_v1_{self.input_digest}":
            raise ValueError("activation_id does not match input digest")
        if self.provenance.execution_authority:
            raise ValueError("paper fill Thesis activation cannot grant execution authority")
        if self.thesis.opening_fill_id != self.provenance.fill_record_id:
            raise ValueError("Thesis opening fill does not match provenance")
        if self.thesis.opening_order_id != self.provenance.order_id:
            raise ValueError("Thesis opening order does not match provenance")

    @property
    def digest(self) -> str:
        return self.input_digest


class PaperFillThesisBuilder:
    """Pure builder; callers own command submission and Journal persistence."""

    __slots__ = ()

    def activate(
        self,
        draft: TradeThesisDraft,
        fill_record: JournalRecord,
    ) -> PaperFillThesisActivation:
        if fill_record.kind != LOCAL_PAPER_FILL_KIND:
            raise ValueError("Thesis activation requires a local-paper fill")
        if fill_record.session_id != draft.session_id:
            raise ValueError("paper fill session does not match Thesis draft")
        if fill_record.occurred_at < draft.created_at.value:
            raise ValueError("paper fill cannot predate thesis draft")
        fill = LocalPaperFill.from_record(fill_record)
        if fill.side is not LocalPaperSide.BUY:
            raise ValueError("Thesis activation requires a BUY fill")
        if fill.symbol != draft.symbol:
            raise ValueError("paper fill symbol does not match Thesis draft")
        expected_record_id = (
            f"local-paper-fill:{fill.order_id}:{fill_record.occurred_at.isoformat()}"
        )
        if fill_record.record_id != expected_record_id:
            raise ValueError("paper fill record identity is not canonical")
        if fill_record.idempotency_key != fill.order_id:
            raise ValueError("paper fill idempotency does not match order")

        payload = fill_record.payload
        required_provenance = {
            "fill_source",
            "provider_identity",
            "execution_authority",
            "command_id",
            "command_idempotency_key",
        }
        if not required_provenance.issubset(payload):
            raise ValueError("paper fill provenance is incomplete")
        try:
            fill_source = PaperFillSource(str(payload["fill_source"]))
        except ValueError as error:
            raise ValueError("Thesis activation requires paper simulation provenance") from error
        if payload["execution_authority"] is not False:
            raise ValueError("paper fill cannot carry execution authority")
        provider_identity = str(payload["provider_identity"]).strip()
        command_id = str(payload["command_id"]).strip()
        command_idempotency_key = str(payload["command_idempotency_key"]).strip()
        if not provider_identity or not command_id:
            raise ValueError("paper fill provenance is incomplete")
        if command_idempotency_key != paper_thesis_entry_idempotency_key(draft):
            raise ValueError("paper fill does not correlate to Thesis draft")

        provenance = PaperFillProvenance(
            version=PAPER_FILL_THESIS_ACTIVATION_VERSION,
            fill_source=fill_source,
            provider_identity=provider_identity,
            execution_authority=False,
            fill_record_id=fill_record.record_id,
            fill_record_fingerprint=fill_record.fingerprint,
            command_id=command_id,
            command_idempotency_key=command_idempotency_key,
            order_id=fill.order_id,
            quantity_shares=fill.quantity_shares,
        )
        thesis = TradeThesis(
            thesis_id=draft.thesis_id,
            trade_id=build_trade_id(draft.session_id, fill_record.record_id),
            draft=draft,
            opening_order_id=fill.order_id,
            opening_fill_id=fill_record.record_id,
            entry_reference_price=fill.fill_price,
            filled_at=TradeTimestamp(
                role=TimestampRole.FILL,
                value=fill_record.occurred_at.astimezone(TAIPEI),
                source=TimestampSource.SIMULATION_CLOCK,
                source_identity=fill_record.record_id,
            ),
        )
        input_digest = _digest(
            {
                "version": PAPER_FILL_THESIS_ACTIVATION_VERSION,
                "thesis_id": draft.thesis_id,
                "trade_id": thesis.trade_id,
                "provenance_digest": provenance.digest,
            }
        )
        return PaperFillThesisActivation(
            version=PAPER_FILL_THESIS_ACTIVATION_VERSION,
            activation_id=f"paper_fill_thesis_v1_{input_digest}",
            input_digest=input_digest,
            thesis=thesis,
            provenance=provenance,
        )
