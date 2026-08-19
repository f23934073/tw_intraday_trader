"""Separate TAIFEX reconciliation artifact service."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from premarket.artifacts import (
    PremarketArtifactRepository,
    create_raw_source_artifact,
    sha256_digest,
)
from premarket.models import (
    ReconciliationObservation,
    ReconciliationStatus,
    TaifexNightContextArtifact,
    TaifexNightReconciliationArtifact,
)


class ReconciliationService:
    def __init__(self, artifacts: PremarketArtifactRepository) -> None:
        self._artifacts = artifacts

    def reconcile(
        self,
        context: TaifexNightContextArtifact,
        observation: ReconciliationObservation,
    ) -> TaifexNightReconciliationArtifact:
        if observation.taifex_trading_date != context.trading_date:
            raise ValueError("reconciliation trading date does not match context trading date")
        resolved_code = context.contract_identity.resolved_contract_code
        if resolved_code is None:
            raise ValueError("reconciliation requires a resolved context contract code")
        if observation.contract_code != resolved_code:
            raise ValueError("reconciliation contract code does not match resolved context contract code")
        if observation.taifex_delivery_month is not None:
            context_delivery_month = context.contract_identity.delivery_month
            if context_delivery_month != observation.taifex_delivery_month:
                raise ValueError(
                    "reconciliation delivery month does not match context contract identity"
                )
        if observation.raw_source_json is not None:
            self._artifacts.save_raw(
                create_raw_source_artifact(
                    source=observation.source,
                    captured_at=observation.reconciled_at,
                    payload_json=observation.raw_source_json,
                )
            )
        available = {
            "open": (context.open, observation.taifex_open),
            "high": (context.high, observation.taifex_high),
            "low": (context.low, observation.taifex_low),
            "close": (context.close, observation.taifex_close),
            "volume": (
                Decimal(context.volume),
                Decimal(observation.taifex_volume)
                if observation.taifex_volume is not None
                else None,
            ),
        }
        comparable = {name: available[name] for name in observation.comparable_fields}
        field_deltas = tuple(
            (name, actual - expected)
            for name, (expected, actual) in comparable.items()
            if actual is not None
        )
        supplied = sum(actual is not None for _, actual in comparable.values())
        mismatches = tuple(name for name, delta in field_deltas if delta != 0)
        limitations = observation.comparison_limitations
        if supplied == 0:
            status = ReconciliationStatus.UNAVAILABLE
            reasons = ("NO_COMPARABLE_TAIFEX_FIELDS", *limitations)
        elif mismatches:
            status = ReconciliationStatus.MISMATCHED
            reasons = (
                *(f"{name.upper()}_MISMATCH" for name in mismatches),
                *limitations,
            )
        elif supplied < len(comparable):
            status = ReconciliationStatus.PARTIAL
            reasons = ("PARTIAL_TAIFEX_FIELDS", *limitations)
        elif limitations:
            status = ReconciliationStatus.PARTIAL
            reasons = limitations
        elif set(comparable) == set(available):
            status = ReconciliationStatus.MATCHED
            reasons = ()
        else:
            status = ReconciliationStatus.PARTIAL
            reasons = ("PARTIAL_TAIFEX_FIELDS",)
        body = {
            "schema_version": "taifex_night_reconciliation_v0",
            "context_artifact_id": context.artifact_id,
            "context_digest": context.context_digest,
            "source": observation.source,
            "raw_source_digest": observation.raw_source_digest,
            "taifex_trading_date": observation.taifex_trading_date,
            "contract_code": observation.contract_code,
            "taifex_settlement_price": observation.taifex_settlement_price,
            "taifex_open": observation.taifex_open,
            "taifex_high": observation.taifex_high,
            "taifex_low": observation.taifex_low,
            "taifex_close": observation.taifex_close,
            "taifex_volume": observation.taifex_volume,
            "taifex_delivery_month": observation.taifex_delivery_month,
            "taifex_volume_basis": observation.taifex_volume_basis,
            "comparable_fields": observation.comparable_fields,
            "comparison_limitations": observation.comparison_limitations,
            "field_deltas": field_deltas,
            "status": status,
            "reasons": reasons,
            "reconciled_at": observation.reconciled_at,
        }
        digest = sha256_digest(body)
        artifact = TaifexNightReconciliationArtifact(
            reconciliation_id=f"taifex-reconciliation-{digest[:16]}",
            reconciliation_digest=digest,
            **body,
        )
        self._artifacts.save_reconciliation(artifact)
        return artifact

    @staticmethod
    def project_summary(
        context: TaifexNightContextArtifact | str,
        reconciliation: TaifexNightReconciliationArtifact | None,
    ) -> dict[str, Any]:
        context_digest = (
            context.context_digest
            if isinstance(context, TaifexNightContextArtifact)
            else context
        )
        if reconciliation is None:
            return {
                "status": "PENDING",
                "artifact_id": None,
                "context_digest": context_digest,
                "settlement_change_pct": None,
                "reasons": [],
            }
        if reconciliation.context_digest != context_digest:
            raise ValueError("reconciliation context digest does not match projection context digest")
        settlement_change_pct = None
        if (
            isinstance(context, TaifexNightContextArtifact)
            and reconciliation.taifex_settlement_price is not None
        ):
            settlement_change_pct = float(
                (
                    context.close
                    / reconciliation.taifex_settlement_price
                    - Decimal("1")
                )
                * Decimal("100")
            )
        return {
            "status": reconciliation.status.value,
            "artifact_id": reconciliation.reconciliation_id,
            "context_digest": reconciliation.context_digest,
            "settlement_change_pct": settlement_change_pct,
            "reasons": list(reconciliation.reasons),
        }
