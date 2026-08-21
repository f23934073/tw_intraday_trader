"""Pure capacity planning for CandidatePool shadow data admission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from candidate.models import CandidateSource
from candidate.pool import CandidatePoolDecision, CandidatePoolEntry
from config.momentum import SubscriptionCapacityConfig


class ShadowAdmissionMode(StrEnum):
    SHADOW = "SHADOW"


class ShadowAdmissionError(RuntimeError):
    """CandidatePool state cannot satisfy a reviewed shadow invariant."""


@dataclass(frozen=True)
class InstitutionalShadowAdmissionPolicy:
    version: str
    capacity: SubscriptionCapacityConfig
    max_institutional_candidates: int

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("shadow admission policy version must not be empty")
        if self.capacity.max_symbols is None:
            raise ValueError(
                "shadow admission requires reviewed provider headroom and mode"
            )
        if (
            isinstance(self.max_institutional_candidates, bool)
            or self.max_institutional_candidates < 0
        ):
            raise ValueError("max_institutional_candidates must be non-negative")

    @property
    def max_symbols(self) -> int:
        value = self.capacity.max_symbols
        assert value is not None
        return value


@dataclass(frozen=True)
class InstitutionalShadowAdmissionMetrics:
    pool_entry_count: int
    protected_count: int
    base_selected_count: int
    base_capacity_rejected_count: int
    institutional_proposed_count: int
    institutional_overlap_count: int
    institutional_admitted_count: int
    institutional_budget_rejected_count: int
    institutional_capacity_rejected_count: int
    selected_symbol_count: int


@dataclass(frozen=True)
class InstitutionalShadowAdmissionDecision:
    mode: ShadowAdmissionMode
    subscription_allowed: bool
    execution_allowed: bool
    evaluated_at: datetime
    policy_version: str
    pool_entry_count: int
    max_symbols: int
    max_institutional_candidates: int
    protected_symbols: tuple[str, ...]
    base_selected_symbols: tuple[str, ...]
    base_capacity_rejected_symbols: tuple[str, ...]
    institutional_proposed_symbols: tuple[str, ...]
    institutional_overlap_symbols: tuple[str, ...]
    institutional_admitted_symbols: tuple[str, ...]
    institutional_budget_rejected_symbols: tuple[str, ...]
    institutional_capacity_rejected_symbols: tuple[str, ...]
    selected_symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.mode is not ShadowAdmissionMode.SHADOW:
            raise ValueError("institutional admission mode must remain SHADOW")
        if self.subscription_allowed or self.execution_allowed:
            raise ValueError("shadow admission cannot authorize side effects")

    @property
    def metrics(self) -> InstitutionalShadowAdmissionMetrics:
        return InstitutionalShadowAdmissionMetrics(
            pool_entry_count=self.pool_entry_count,
            protected_count=len(self.protected_symbols),
            base_selected_count=len(self.base_selected_symbols),
            base_capacity_rejected_count=len(self.base_capacity_rejected_symbols),
            institutional_proposed_count=len(self.institutional_proposed_symbols),
            institutional_overlap_count=len(self.institutional_overlap_symbols),
            institutional_admitted_count=len(self.institutional_admitted_symbols),
            institutional_budget_rejected_count=len(
                self.institutional_budget_rejected_symbols
            ),
            institutional_capacity_rejected_count=len(
                self.institutional_capacity_rejected_symbols
            ),
            selected_symbol_count=len(self.selected_symbols),
        )

    @property
    def digest(self) -> str:
        payload = {
            "mode": self.mode.value,
            "subscription_allowed": self.subscription_allowed,
            "execution_allowed": self.execution_allowed,
            "evaluated_at": self.evaluated_at.isoformat(),
            "policy_version": self.policy_version,
            "pool_entry_count": self.pool_entry_count,
            "max_symbols": self.max_symbols,
            "max_institutional_candidates": self.max_institutional_candidates,
            "protected_symbols": list(self.protected_symbols),
            "base_selected_symbols": list(self.base_selected_symbols),
            "base_capacity_rejected_symbols": list(self.base_capacity_rejected_symbols),
            "institutional_proposed_symbols": list(self.institutional_proposed_symbols),
            "institutional_overlap_symbols": list(self.institutional_overlap_symbols),
            "institutional_admitted_symbols": list(self.institutional_admitted_symbols),
            "institutional_budget_rejected_symbols": list(
                self.institutional_budget_rejected_symbols
            ),
            "institutional_capacity_rejected_symbols": list(
                self.institutional_capacity_rejected_symbols
            ),
            "selected_symbols": list(self.selected_symbols),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class InstitutionalCandidateShadowAdmission:
    """Select residual CandidatePool capacity without causing provider actions."""

    def __init__(self, policy: InstitutionalShadowAdmissionPolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        pool_decision: CandidatePoolDecision,
    ) -> InstitutionalShadowAdmissionDecision:
        entries = tuple(entry for entry in pool_decision.entries if entry.admitted)
        protected = tuple(
            sorted(
                (entry for entry in entries if entry.protected),
                key=CandidatePoolEntry.selection_key,
            )
        )
        if len(protected) > self.policy.max_symbols:
            raise ShadowAdmissionError(
                f"{len(protected)} protected symbols exceed reviewed capacity "
                f"{self.policy.max_symbols}"
            )

        institutional_source = CandidateSource.PREVIOUS_SESSION_WATCHLIST
        base_entries = tuple(
            entry
            for entry in entries
            if any(source is not institutional_source for source in entry.sources)
        )
        protected_symbols = {entry.symbol for entry in protected}
        base_unprotected = sorted(
            (entry for entry in base_entries if entry.symbol not in protected_symbols),
            key=CandidatePoolEntry.selection_key,
        )
        selected_base = list(protected)
        selected_base.extend(
            base_unprotected[: self.policy.max_symbols - len(selected_base)]
        )
        selected_base_symbols = {entry.symbol for entry in selected_base}
        rejected_base = tuple(
            entry.symbol
            for entry in base_unprotected
            if entry.symbol not in selected_base_symbols
        )

        institutional_entries = tuple(
            sorted(
                (entry for entry in entries if institutional_source in entry.sources),
                key=CandidatePoolEntry.selection_key,
            )
        )
        overlap = tuple(
            entry.symbol
            for entry in institutional_entries
            if entry.symbol in selected_base_symbols
        )
        pure_institutional = tuple(
            entry
            for entry in institutional_entries
            if len(entry.sources) == 1 and entry.symbol not in selected_base_symbols
        )
        within_budget = pure_institutional[: self.policy.max_institutional_candidates]
        budget_rejected = pure_institutional[self.policy.max_institutional_candidates :]
        remaining_capacity = self.policy.max_symbols - len(selected_base)
        admitted_pure = within_budget[:remaining_capacity]
        capacity_rejected = within_budget[remaining_capacity:]
        mixed_capacity_rejected = tuple(
            entry
            for entry in institutional_entries
            if len(entry.sources) > 1 and entry.symbol not in selected_base_symbols
        )

        selected_symbols = tuple(
            entry.symbol for entry in selected_base + list(admitted_pure)
        )
        if len(selected_symbols) > self.policy.max_symbols:
            raise AssertionError("shadow admission capacity invariant violated")

        return InstitutionalShadowAdmissionDecision(
            mode=ShadowAdmissionMode.SHADOW,
            subscription_allowed=False,
            execution_allowed=False,
            evaluated_at=pool_decision.evaluated_at,
            policy_version=self.policy.version,
            pool_entry_count=len(entries),
            max_symbols=self.policy.max_symbols,
            max_institutional_candidates=self.policy.max_institutional_candidates,
            protected_symbols=tuple(entry.symbol for entry in protected),
            base_selected_symbols=tuple(entry.symbol for entry in selected_base),
            base_capacity_rejected_symbols=rejected_base,
            institutional_proposed_symbols=tuple(
                entry.symbol for entry in institutional_entries
            ),
            institutional_overlap_symbols=overlap,
            institutional_admitted_symbols=tuple(
                entry.symbol for entry in admitted_pure
            ),
            institutional_budget_rejected_symbols=tuple(
                entry.symbol for entry in budget_rejected
            ),
            institutional_capacity_rejected_symbols=tuple(
                entry.symbol for entry in mixed_capacity_rejected + capacity_rejected
            ),
            selected_symbols=selected_symbols,
        )
