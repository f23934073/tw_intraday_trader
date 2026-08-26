"""Ports for the R5 revision-2 bounded context.

The domain remains independent of persistence. G2 adds a PostgreSQL repository
port, while HTTP, Dashboard, providers, brokers, and Local Paper remain outside
the authorized slice.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .domain import LedgerBuild, ObservedBar, OrderDerivationBuild


@dataclass(frozen=True)
class BaselinePreflightEvidence:
    identity: dict[str, Any]
    dataset_manifest: dict[str, Any]
    ledger: LedgerBuild
    order_derivation: OrderDerivationBuild


class BaselineSignalEvidencePort(Protocol):
    def load_preflight_evidence(
        self, baseline_run_id: str
    ) -> BaselinePreflightEvidence: ...


class OrderedDatasetPort(Protocol):
    def iter_observed_bars(self) -> Iterable[ObservedBar]: ...


class ExternalCallAuditPort(Protocol):
    def snapshot(self) -> Mapping[str, int]: ...


class ReplayArtifactStorePort(Protocol):
    def publish_ledger(
        self,
        *,
        manifest: Mapping[str, object],
        ledger_rows: Iterable[Mapping[str, object]],
        order_rows: Iterable[Mapping[str, object]],
    ) -> Path: ...

    def publish_match_plan(
        self,
        *,
        manifest: Mapping[str, object],
        match_rows: Iterable[Mapping[str, object]],
    ) -> Path: ...

    def load_ledger(self, manifest_digest: str) -> Any: ...

    def load_match_plan(self, manifest_digest: str) -> Any: ...

    def publish_result(
        self,
        *,
        manifest: Mapping[str, object],
        episode_rows: Iterable[Mapping[str, object]],
        modeled_entry_rows: Iterable[Mapping[str, object]],
        modeled_exit_rows: Iterable[Mapping[str, object]],
    ) -> Path: ...

    def load_result(self, manifest_digest: str) -> Any: ...


class SignalReplayRepositoryPort(Protocol):
    def replay_create_operation(
        self,
        *,
        baseline_run_id: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None: ...

    def create_replay(
        self,
        *,
        replay_id: str,
        baseline_run_id: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        request_digest: str,
        ledger_manifest: Mapping[str, Any],
        match_manifest: Mapping[str, Any],
        ledger_rows: Iterable[Mapping[str, Any]],
        order_rows: Iterable[Mapping[str, Any]],
    ) -> tuple[dict[str, Any], bool]: ...

    def get_replay(self, replay_id: str) -> dict[str, Any]: ...

    def transition_replay_status(
        self,
        replay_id: str,
        *,
        expected_statuses: tuple[str, ...],
        status: str,
        progress: str | None,
        progress_message: str,
        error_message: str | None = None,
    ) -> tuple[dict[str, Any], bool]: ...

    def publish_result(
        self,
        replay_id: str,
        *,
        ledger_rows: Iterable[Mapping[str, Any]],
        order_rows: Iterable[Mapping[str, Any]],
        match_rows: Iterable[Mapping[str, Any]],
        result_manifest: Mapping[str, Any],
        episode_rows: Iterable[Mapping[str, Any]],
        modeled_entry_rows: Iterable[Mapping[str, Any]],
        modeled_exit_rows: Iterable[Mapping[str, Any]],
        postflight: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def get_accepted_result(
        self,
        replay_id: str,
        *,
        ledger_rows: Iterable[Mapping[str, Any]],
        order_rows: Iterable[Mapping[str, Any]],
        match_rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]: ...
