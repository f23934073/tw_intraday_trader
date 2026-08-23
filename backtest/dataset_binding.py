"""PostgreSQL-only immutable Dataset binding contracts."""

from __future__ import annotations

import re
from typing import Any, Mapping

from backtest.dataset import DatasetManifest
from backtest.domain import digest


ATOMIC_BACKTEST_DEFAULT = "ATOMIC_BACKTEST_DEFAULT"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DatasetRegistrationConflict(ValueError):
    """An immutable Dataset ID already exists with different evidence."""


class DatasetBindingConflict(ValueError):
    """Base class for fail-closed binding conflicts."""


class DatasetBindingIdempotencyConflict(DatasetBindingConflict):
    """The same durable activation key was reused for another request."""


class DatasetBindingRevisionConflict(DatasetBindingConflict):
    """The caller's expected binding revision is stale."""


class DatasetBindingIntegrityError(DatasetBindingConflict):
    """The binding, Dataset row, or durable result has drifted."""


class AtomicBacktestBindingUnavailable(DatasetBindingConflict):
    """The required default binding does not exist or cannot be used."""


class AtomicBacktestBindingChanged(DatasetBindingConflict):
    """The browser precondition no longer matches the locked binding head."""


def canonical_registration_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact canonical manifest or reject unknown/drifted fields."""

    parsed = DatasetManifest.from_dict(manifest)
    canonical = parsed.to_dict()
    if dict(manifest) != canonical:
        raise ValueError("Dataset manifest schema or digest is not canonical")
    for field in ("bars_sha256", "manifest_digest"):
        require_sha256(str(canonical.get(field) or ""), field)
    if not str(canonical["dataset_id"]).strip():
        raise ValueError("Dataset ID must not be empty")
    return canonical


def activation_request(
    *,
    binding_name: str,
    dataset_id: str,
    dataset_digest: str,
    plan_identity_digest: str,
    expected_revision: int,
    actor_id: str,
    change_note: str,
) -> dict[str, Any]:
    binding_name = require_text(binding_name, "binding name")
    dataset_id = require_text(dataset_id, "Dataset ID")
    actor_id = require_text(actor_id, "actor")
    change_note = require_text(change_note, "change note")
    require_sha256(dataset_digest, "Dataset digest")
    require_sha256(plan_identity_digest, "plan identity digest")
    if expected_revision < 0:
        raise ValueError("expected binding revision must be non-negative")
    return {
        "actor_id": actor_id,
        "binding_name": binding_name,
        "change_note": change_note,
        "dataset_digest": dataset_digest,
        "dataset_id": dataset_id,
        "expected_revision": expected_revision,
        "plan_identity_digest": plan_identity_digest,
    }


def activation_request_digest(**values: Any) -> str:
    return digest(activation_request(**values))


def require_sha256(value: str, label: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def require_text(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized
