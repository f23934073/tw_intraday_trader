"""Activate an immutable TradeThesis from an audited local-paper BUY fill."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from trading.canonical_values import canonical_decimal_string
from trading.journal import JournalRecord
from trading.local_paper import (
    LOCAL_PAPER_FILL_KIND,
    LOCAL_PAPER_FILL_V2_KIND,
    LOCAL_PAPER_FILL_V3_KIND,
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
PAPER_FILL_THESIS_AGGREGATION_VERSION = "paper-fill-thesis-activation-v2"
PAPER_FILL_AGGREGATION_VERSION = "paper-fill-aggregation-v1"
PAPER_FILL_TERMINAL_EVIDENCE_VERSION = "paper-fill-terminal-evidence-v1"
_AGGREGATE_FILL_KINDS = frozenset(
    {LOCAL_PAPER_FILL_V2_KIND, LOCAL_PAPER_FILL_V3_KIND}
)
_ACTIVATION_PREFIXES = {
    PAPER_FILL_THESIS_ACTIVATION_VERSION: "paper_fill_thesis_v1_",
    PAPER_FILL_THESIS_AGGREGATION_VERSION: "paper_fill_thesis_v2_",
}
_AGGREGATE_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)
_AGGREGATE_COMMON_STRING_FIELDS = frozenset(
    {
        "order_id",
        "symbol",
        "name",
        "side",
        "fill_price",
        "commission",
        "net_cash_effect",
        "cumulative_order_commission",
        "settings_digest",
        "fill_source",
        "provider_identity",
        "command_id",
        "command_idempotency_key",
    }
)
_AGGREGATE_V2_STRING_FIELDS = frozenset({"gross_notional"})
_AGGREGATE_V3_STRING_FIELDS = frozenset(
    {
        "tax",
        "gross_amount",
        "reference_price",
        "reference_source",
        "configured_slippage_bps",
        "realized_slippage_bps",
        "slippage_cost",
        "cumulative_order_gross",
        "cumulative_order_tax",
        "fee_policy_version",
        "rounding_policy_version",
        "slippage_policy_version",
        "price_tick_policy_version",
        "instrument_descriptor_digest",
        "limit_price",
    }
)


class PaperFillSource(StrEnum):
    PAPER_SIMULATION = "paper_simulation"


class PaperFillAggregationConflictError(ValueError):
    """Correlated records cannot form one authoritative fill aggregate."""


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
class PaperFillRecordProvenance:
    fill_kind: str
    fill_sequence: int
    fill_record_id: str
    fill_record_fingerprint: str
    occurred_at: str
    quantity_shares: int
    fill_price: str

    def __post_init__(self) -> None:
        if self.fill_kind not in _AGGREGATE_FILL_KINDS:
            raise ValueError("aggregate fill lineage requires v2 or v3 records")
        if (
            isinstance(self.fill_sequence, bool)
            or not isinstance(self.fill_sequence, int)
            or self.fill_sequence <= 0
        ):
            raise ValueError("fill_sequence must be positive")
        if not self.fill_record_id.strip():
            raise ValueError("fill_record_id must not be empty")
        _require_digest(self.fill_record_fingerprint, "fill_record_fingerprint")
        parsed_at = datetime.fromisoformat(self.occurred_at)
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError("fill occurred_at must be timezone-aware")
        if (
            isinstance(self.quantity_shares, bool)
            or not isinstance(self.quantity_shares, int)
            or self.quantity_shares <= 0
        ):
            raise ValueError("quantity_shares must be positive")
        price = Decimal(self.fill_price)
        if not price.is_finite() or price <= 0:
            raise ValueError("fill_price must be positive")

    @property
    def digest_payload(self) -> dict[str, object]:
        return {
            "fill_kind": self.fill_kind,
            "fill_sequence": self.fill_sequence,
            "fill_record_id": self.fill_record_id,
            "fill_record_fingerprint": self.fill_record_fingerprint,
            "occurred_at": self.occurred_at,
            "quantity_shares": self.quantity_shares,
            "fill_price": self.fill_price,
        }


@dataclass(frozen=True)
class PaperFillTerminalEvidence:
    version: str
    journal_sequence: int
    order_state_record_id: str
    order_state_record_fingerprint: str
    occurred_at: str
    session_id: str
    order_id: str
    command_idempotency_key: str
    symbol: str
    side: LocalPaperSide
    quantity_shares: int
    filled_quantity_shares: int
    remaining_quantity_shares: int
    fill_sequence: int
    status: str

    def __post_init__(self) -> None:
        if self.version != PAPER_FILL_TERMINAL_EVIDENCE_VERSION:
            raise ValueError("unsupported paper fill terminal evidence version")
        if (
            isinstance(self.journal_sequence, bool)
            or not isinstance(self.journal_sequence, int)
            or self.journal_sequence <= 0
        ):
            raise ValueError("terminal order-state Journal sequence must be positive")
        for value, field_name in (
            (self.order_state_record_id, "order_state_record_id"),
            (self.session_id, "session_id"),
            (self.order_id, "order_id"),
            (self.command_idempotency_key, "command_idempotency_key"),
            (self.symbol, "symbol"),
            (self.status, "status"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        _require_digest(
            self.order_state_record_fingerprint,
            "order_state_record_fingerprint",
        )
        parsed_at = datetime.fromisoformat(self.occurred_at)
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError("terminal order-state occurred_at must be timezone-aware")
        integer_fields = (
            self.quantity_shares,
            self.filled_quantity_shares,
            self.remaining_quantity_shares,
            self.fill_sequence,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in integer_fields
        ):
            raise ValueError("terminal order-state quantities must be integers")
        if self.side is not LocalPaperSide.BUY or self.status != "FILLED":
            raise ValueError("terminal completion evidence requires a FILLED BUY order")
        if self.quantity_shares <= 0 or self.fill_sequence <= 0:
            raise ValueError("terminal completion evidence must be positive")
        if (
            self.filled_quantity_shares != self.quantity_shares
            or self.remaining_quantity_shares != 0
        ):
            raise ValueError("terminal completion evidence is not fully filled")

    @property
    def digest_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "journal_sequence": self.journal_sequence,
            "order_state_record_id": self.order_state_record_id,
            "order_state_record_fingerprint": self.order_state_record_fingerprint,
            "occurred_at": self.occurred_at,
            "session_id": self.session_id,
            "order_id": self.order_id,
            "command_idempotency_key": self.command_idempotency_key,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity_shares": self.quantity_shares,
            "filled_quantity_shares": self.filled_quantity_shares,
            "remaining_quantity_shares": self.remaining_quantity_shares,
            "fill_sequence": self.fill_sequence,
            "status": self.status,
        }


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
    fill_records: tuple[PaperFillRecordProvenance, ...] = ()
    session_id: str | None = None
    symbol: str | None = None
    side: LocalPaperSide | None = None
    terminal_evidence: PaperFillTerminalEvidence | None = None

    def __post_init__(self) -> None:
        if self.version not in _ACTIVATION_PREFIXES:
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
        if (
            isinstance(self.quantity_shares, bool)
            or not isinstance(self.quantity_shares, int)
            or self.quantity_shares <= 0
        ):
            raise ValueError("quantity_shares must be positive")
        if self.version == PAPER_FILL_THESIS_ACTIVATION_VERSION:
            if self.fill_records or any(
                value is not None
                for value in (
                    self.session_id,
                    self.symbol,
                    self.side,
                    self.terminal_evidence,
                )
            ):
                raise ValueError("legacy fill provenance cannot carry aggregate lineage")
        else:
            if not self.fill_records:
                raise ValueError("aggregate fill provenance requires record lineage")
            if self.quantity_shares != sum(
                record.quantity_shares for record in self.fill_records
            ):
                raise ValueError("aggregate fill quantity does not match lineage")
            if not self.fill_record_id.startswith(
                f"local-paper-fill-aggregate:{self.order_id}:"
            ):
                raise ValueError("aggregate fill record identity is not canonical")
            if not self.session_id or not self.symbol:
                raise ValueError("aggregate fill session and symbol are required")
            if self.side is not LocalPaperSide.BUY:
                raise ValueError("aggregate Thesis provenance requires BUY side")
            if self.terminal_evidence is None:
                raise ValueError("aggregate fill provenance requires terminal evidence")
            terminal = self.terminal_evidence
            expected_terminal_values = {
                "session_id": self.session_id,
                "order_id": self.order_id,
                "command_idempotency_key": self.command_idempotency_key,
                "symbol": self.symbol,
                "side": self.side,
                "quantity_shares": self.quantity_shares,
                "filled_quantity_shares": self.quantity_shares,
                "remaining_quantity_shares": 0,
                "fill_sequence": len(self.fill_records),
            }
            if any(
                getattr(terminal, field_name) != value
                for field_name, value in expected_terminal_values.items()
            ):
                raise ValueError(
                    "aggregate provenance conflicts with terminal evidence"
                )

    @property
    def digest(self) -> str:
        payload: dict[str, object] = {
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
        if self.fill_records:
            assert self.terminal_evidence is not None
            payload["aggregation_version"] = PAPER_FILL_AGGREGATION_VERSION
            payload["session_id"] = self.session_id
            payload["symbol"] = self.symbol
            payload["side"] = self.side.value if self.side is not None else None
            payload["fill_records"] = [
                record.digest_payload for record in self.fill_records
            ]
            payload["terminal_evidence"] = self.terminal_evidence.digest_payload
        return _digest(payload)


@dataclass(frozen=True)
class PaperFillThesisActivation:
    version: str
    activation_id: str
    input_digest: str
    thesis: TradeThesis
    provenance: PaperFillProvenance

    def __post_init__(self) -> None:
        if self.version not in _ACTIVATION_PREFIXES:
            raise ValueError("unsupported paper fill Thesis activation version")
        if self.provenance.version != self.version:
            raise ValueError("activation and provenance versions do not match")
        _require_digest(self.input_digest, "input_digest")
        if self.activation_id != f"{_ACTIVATION_PREFIXES[self.version]}{self.input_digest}":
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
        fill_record: JournalRecord | Sequence[JournalRecord],
        *,
        terminal_evidence: PaperFillTerminalEvidence | None = None,
    ) -> PaperFillThesisActivation:
        if not isinstance(fill_record, JournalRecord):
            records = tuple(fill_record)
            if not records:
                raise ValueError("Thesis activation requires a local-paper fill")
            if not all(isinstance(record, JournalRecord) for record in records):
                raise TypeError("fill records must be JournalRecord values")
            if len(records) == 1 and records[0].kind == LOCAL_PAPER_FILL_KIND:
                return self._activate_legacy(draft, records[0])
            return self._activate_aggregate(draft, records, terminal_evidence)
        if fill_record.kind in _AGGREGATE_FILL_KINDS:
            return self._activate_aggregate(
                draft,
                (fill_record,),
                terminal_evidence,
            )
        return self._activate_legacy(draft, fill_record)

    def _activate_legacy(
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

    def _activate_aggregate(
        self,
        draft: TradeThesisDraft,
        fill_records: tuple[JournalRecord, ...],
        terminal_evidence: PaperFillTerminalEvidence | None,
    ) -> PaperFillThesisActivation:
        if terminal_evidence is None:
            raise ValueError(
                "settings-bound Thesis activation requires terminal completion evidence"
            )
        with localcontext(_AGGREGATE_DECIMAL_CONTEXT):
            return self._activate_aggregate_in_context(
                draft,
                fill_records,
                terminal_evidence,
            )

    def _activate_aggregate_in_context(
        self,
        draft: TradeThesisDraft,
        fill_records: tuple[JournalRecord, ...],
        terminal_evidence: PaperFillTerminalEvidence,
    ) -> PaperFillThesisActivation:
        ordered_records = self._ordered_aggregate_records(fill_records)
        fills: list[LocalPaperFill] = []
        lineages: list[PaperFillRecordProvenance] = []
        common: dict[str, object] | None = None
        cumulative_gross = Decimal("0")
        cumulative_commission = Decimal("0")
        cumulative_tax = Decimal("0")
        for fill_sequence, record in enumerate(ordered_records, start=1):
            if record.session_id != draft.session_id:
                raise ValueError("paper fill session does not match Thesis draft")
            if record.occurred_at < draft.created_at.value:
                raise ValueError("paper fill cannot predate thesis draft")
            self._require_canonical_aggregate_payload(record)
            fill = LocalPaperFill.from_record(record)
            if fill.side is not LocalPaperSide.BUY:
                raise ValueError("Thesis activation requires a BUY fill")
            if fill.symbol != draft.symbol:
                raise ValueError("paper fill symbol does not match Thesis draft")
            expected_record_id = (
                f"local-paper-fill:{fill.order_id}:{record.occurred_at.isoformat()}"
            )
            if record.record_id != expected_record_id:
                raise ValueError("paper fill record identity is not canonical")
            expected_idempotency_key = (
                fill.order_id
                if fill_sequence == 1
                else f"{fill.order_id}:{fill_sequence}"
            )
            if record.idempotency_scope != (
                f"{draft.session_id}:legacy_simulation_fill"
            ):
                raise ValueError("paper fill idempotency scope is not canonical")
            if record.idempotency_key != expected_idempotency_key:
                raise ValueError("paper fill idempotency does not match fill sequence")

            payload = record.payload
            required_provenance = {
                "fill_source",
                "provider_identity",
                "execution_authority",
                "command_id",
                "command_idempotency_key",
                "fill_sequence",
                "settings_digest",
            }
            if not required_provenance.issubset(payload):
                raise ValueError("paper fill provenance is incomplete")
            try:
                fill_source = PaperFillSource(str(payload["fill_source"]))
            except ValueError as error:
                raise ValueError(
                    "Thesis activation requires paper simulation provenance"
                ) from error
            if payload["execution_authority"] is not False:
                raise ValueError("paper fill cannot carry execution authority")
            provider_identity = str(payload["provider_identity"]).strip()
            command_id = str(payload["command_id"]).strip()
            command_idempotency_key = str(
                payload["command_idempotency_key"]
            ).strip()
            if not provider_identity or not command_id:
                raise ValueError("paper fill provenance is incomplete")
            if command_idempotency_key != paper_thesis_entry_idempotency_key(draft):
                raise ValueError("paper fill does not correlate to Thesis draft")

            descriptor = (
                str(payload["instrument_descriptor_digest"])
                if record.kind == LOCAL_PAPER_FILL_V3_KIND
                else None
            )
            record_common = {
                "fill_kind": record.kind,
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "name": fill.name,
                "side": fill.side.value,
                "fill_source": fill_source.value,
                "provider_identity": provider_identity,
                "execution_authority": False,
                "command_id": command_id,
                "command_idempotency_key": command_idempotency_key,
                "settings_digest": str(payload["settings_digest"]),
                "fee_policy_version": payload.get("fee_policy_version"),
                "rounding_policy_version": payload.get("rounding_policy_version"),
                "slippage_policy_version": payload.get("slippage_policy_version"),
                "price_tick_policy_version": payload.get(
                    "price_tick_policy_version"
                ),
                "instrument_descriptor_digest": descriptor,
            }
            if common is None:
                common = record_common
            elif common != record_common:
                raise PaperFillAggregationConflictError(
                    "conflicting local-paper fill provenance or schema"
                )

            cumulative_gross += fill.fill_price * fill.quantity_shares
            cumulative_commission += fill.commission
            cumulative_tax += fill.tax
            if Decimal(str(payload["cumulative_order_commission"])) != (
                cumulative_commission
            ):
                raise PaperFillAggregationConflictError(
                    "conflicting cumulative fill commission lineage"
                )
            if record.kind == LOCAL_PAPER_FILL_V3_KIND and (
                Decimal(str(payload["cumulative_order_gross"])) != cumulative_gross
                or Decimal(str(payload["cumulative_order_tax"])) != cumulative_tax
            ):
                raise PaperFillAggregationConflictError(
                    "conflicting cumulative fill monetary lineage"
                )
            fills.append(fill)
            lineages.append(
                PaperFillRecordProvenance(
                    fill_kind=record.kind,
                    fill_sequence=fill_sequence,
                    fill_record_id=record.record_id,
                    fill_record_fingerprint=record.fingerprint,
                    occurred_at=record.occurred_at.isoformat(),
                    quantity_shares=fill.quantity_shares,
                    fill_price=canonical_decimal_string(fill.fill_price),
                )
            )

        assert common is not None
        quantity_shares = sum(fill.quantity_shares for fill in fills)
        self._require_terminal_evidence(
            draft=draft,
            common=common,
            quantity_shares=quantity_shares,
            fill_count=len(lineages),
            filled_at=ordered_records[-1].occurred_at,
            terminal_evidence=terminal_evidence,
        )
        entry_reference_price = cumulative_gross / Decimal(quantity_shares)
        aggregate_payload = {
            "aggregation_version": PAPER_FILL_AGGREGATION_VERSION,
            "session_id": draft.session_id,
            "order_id": common["order_id"],
            "command_id": common["command_id"],
            "command_idempotency_key": common["command_idempotency_key"],
            "quantity_shares": quantity_shares,
            "gross_amount": canonical_decimal_string(cumulative_gross),
            "entry_reference_price": canonical_decimal_string(
                entry_reference_price
            ),
            "filled_at": ordered_records[-1].occurred_at.isoformat(),
            "fill_records": [lineage.digest_payload for lineage in lineages],
            "terminal_evidence": terminal_evidence.digest_payload,
        }
        aggregate_fingerprint = _digest(aggregate_payload)
        aggregate_record_id = (
            f"local-paper-fill-aggregate:{common['order_id']}:"
            f"{aggregate_fingerprint}"
        )
        provenance = PaperFillProvenance(
            version=PAPER_FILL_THESIS_AGGREGATION_VERSION,
            fill_source=PaperFillSource(str(common["fill_source"])),
            provider_identity=str(common["provider_identity"]),
            execution_authority=False,
            fill_record_id=aggregate_record_id,
            fill_record_fingerprint=aggregate_fingerprint,
            command_id=str(common["command_id"]),
            command_idempotency_key=str(common["command_idempotency_key"]),
            order_id=str(common["order_id"]),
            quantity_shares=quantity_shares,
            fill_records=tuple(lineages),
            session_id=draft.session_id,
            symbol=draft.symbol,
            side=LocalPaperSide.BUY,
            terminal_evidence=terminal_evidence,
        )
        thesis = TradeThesis(
            thesis_id=draft.thesis_id,
            trade_id=build_trade_id(draft.session_id, aggregate_record_id),
            draft=draft,
            opening_order_id=provenance.order_id,
            opening_fill_id=aggregate_record_id,
            entry_reference_price=entry_reference_price,
            filled_at=TradeTimestamp(
                role=TimestampRole.FILL,
                value=ordered_records[-1].occurred_at.astimezone(TAIPEI),
                source=TimestampSource.SIMULATION_CLOCK,
                source_identity=aggregate_record_id,
            ),
        )
        input_digest = _digest(
            {
                "version": PAPER_FILL_THESIS_AGGREGATION_VERSION,
                "thesis_id": draft.thesis_id,
                "trade_id": thesis.trade_id,
                "provenance_digest": provenance.digest,
            }
        )
        return PaperFillThesisActivation(
            version=PAPER_FILL_THESIS_AGGREGATION_VERSION,
            activation_id=f"paper_fill_thesis_v2_{input_digest}",
            input_digest=input_digest,
            thesis=thesis,
            provenance=provenance,
        )

    @staticmethod
    def _require_terminal_evidence(
        *,
        draft: TradeThesisDraft,
        common: dict[str, object],
        quantity_shares: int,
        fill_count: int,
        filled_at: datetime,
        terminal_evidence: PaperFillTerminalEvidence,
    ) -> None:
        expected_values = {
            "session_id": draft.session_id,
            "order_id": common["order_id"],
            "command_idempotency_key": common["command_idempotency_key"],
            "symbol": draft.symbol,
            "side": LocalPaperSide.BUY,
            "quantity_shares": quantity_shares,
            "filled_quantity_shares": quantity_shares,
            "remaining_quantity_shares": 0,
            "fill_sequence": fill_count,
            "status": "FILLED",
        }
        if any(
            getattr(terminal_evidence, field_name) != value
            for field_name, value in expected_values.items()
        ):
            raise PaperFillAggregationConflictError(
                "conflicting terminal local-paper order state"
            )
        terminal_at = datetime.fromisoformat(terminal_evidence.occurred_at)
        if terminal_at < filled_at:
            raise PaperFillAggregationConflictError(
                "terminal local-paper order state predates final fill"
            )

    @staticmethod
    def _require_canonical_aggregate_payload(record: JournalRecord) -> None:
        payload = record.payload
        string_fields = _AGGREGATE_COMMON_STRING_FIELDS | (
            _AGGREGATE_V3_STRING_FIELDS
            if record.kind == LOCAL_PAPER_FILL_V3_KIND
            else _AGGREGATE_V2_STRING_FIELDS
        )
        if any(
            not isinstance(payload.get(field_name), str)
            or not str(payload[field_name]).strip()
            for field_name in string_fields
        ):
            raise ValueError(
                "settings-bound fill monetary/provenance fields must be "
                "canonical strings"
            )
        quantity = payload.get("quantity_shares")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("quantity_shares must be an integer")

    @staticmethod
    def _ordered_aggregate_records(
        records: tuple[JournalRecord, ...],
    ) -> tuple[JournalRecord, ...]:
        by_sequence: dict[int, JournalRecord] = {}
        fill_kind: str | None = None
        for record in records:
            if record.kind not in _AGGREGATE_FILL_KINDS:
                raise PaperFillAggregationConflictError(
                    "conflicting local-paper fill schema versions"
                )
            if fill_kind is None:
                fill_kind = record.kind
            elif record.kind != fill_kind:
                raise PaperFillAggregationConflictError(
                    "conflicting local-paper fill schema versions"
                )
            sequence = record.payload.get("fill_sequence")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence <= 0
            ):
                raise ValueError("fill_sequence must be positive")
            existing = by_sequence.get(sequence)
            if existing is not None:
                if (
                    existing.record_id == record.record_id
                    and existing.fingerprint == record.fingerprint
                ):
                    continue
                raise PaperFillAggregationConflictError(
                    "conflicting duplicate local-paper fill sequence"
                )
            by_sequence[sequence] = record
        ordered = tuple(by_sequence[sequence] for sequence in sorted(by_sequence))
        if tuple(sorted(by_sequence)) != tuple(range(1, len(ordered) + 1)):
            raise PaperFillAggregationConflictError(
                "conflicting or incomplete local-paper fill sequence"
            )
        if any(
            current.occurred_at <= previous.occurred_at
            for previous, current in zip(ordered, ordered[1:])
        ):
            raise PaperFillAggregationConflictError(
                "conflicting local-paper fill chronology"
            )
        return ordered
