"""Validated price and institutional evidence bundles for factor research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from institutional_data.domain import (
    InstitutionalFlowDaily,
    InstitutionalMarket,
    InstitutionalPartitionManifest,
    PartitionStatus,
)
from institutional_data.serialization import (
    canonical_json,
    flow_rows_sha256,
    serialize_partition_manifest,
    sha256_text,
)
from watchlist.reference_data import EquityMarket


PRICE_ROWS_SCHEMA_VERSION = "daily_adjusted_close_rows_v1"
INSTITUTIONAL_BUNDLE_SCHEMA_VERSION = "institutional_research_bundle_v0"


class ResearchInputError(ValueError):
    """Research evidence is missing, inconsistent, or not digest-pinned."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


@dataclass(frozen=True)
class DailyAdjustedClose:
    market: EquityMarket
    symbol: str
    session_date: date
    adjusted_close: Decimal
    source_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", EquityMarket(self.market))
        object.__setattr__(self, "symbol", _non_empty(self.symbol, "symbol").upper())
        if not isinstance(self.adjusted_close, Decimal):
            object.__setattr__(
                self, "adjusted_close", Decimal(str(self.adjusted_close))
            )
        if not self.adjusted_close.is_finite() or self.adjusted_close <= 0:
            raise ValueError("adjusted_close must be a finite positive Decimal")
        _require_sha256(self.source_digest, "source_digest")


def serialize_price_rows(rows: tuple[DailyAdjustedClose, ...]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: (row.market.value, row.symbol, row.session_date),
    )
    return canonical_json(
        {
            "schema_version": PRICE_ROWS_SCHEMA_VERSION,
            "rows": [
                {
                    "market": row.market,
                    "symbol": row.symbol,
                    "session_date": row.session_date,
                    "adjusted_close": row.adjusted_close,
                    "source_digest": row.source_digest,
                }
                for row in ordered
            ],
        }
    )


def price_rows_sha256(rows: tuple[DailyAdjustedClose, ...]) -> str:
    return sha256_text(serialize_price_rows(rows))


@dataclass(frozen=True)
class PriceResearchInput:
    dataset_id: str
    dataset_digest: str
    rows: tuple[DailyAdjustedClose, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dataset_id",
            _non_empty(self.dataset_id, "dataset_id"),
        )
        _require_sha256(self.dataset_digest, "dataset_digest")
        ordered = tuple(
            sorted(
                self.rows,
                key=lambda row: (row.market.value, row.symbol, row.session_date),
            )
        )
        identities = [(row.market, row.symbol, row.session_date) for row in ordered]
        if len(identities) != len(set(identities)):
            raise ResearchInputError(
                "DUPLICATE_PRICE_ROW",
                "daily adjusted-close rows must be unique",
            )
        if price_rows_sha256(ordered) != self.dataset_digest:
            raise ResearchInputError(
                "PRICE_DIGEST_MISMATCH",
                "price rows differ from the pinned dataset digest",
            )
        object.__setattr__(self, "rows", ordered)


def institutional_bundle_sha256(
    rows: tuple[InstitutionalFlowDaily, ...],
    manifests: tuple[InstitutionalPartitionManifest, ...],
) -> str:
    partition_digests = [
        sha256_text(serialize_partition_manifest(manifest))
        for manifest in sorted(
            manifests,
            key=lambda manifest: (
                manifest.market.value,
                manifest.session_date,
                manifest.partition_id,
            ),
        )
    ]
    return sha256_text(
        canonical_json(
            {
                "schema_version": INSTITUTIONAL_BUNDLE_SCHEMA_VERSION,
                "flow_rows_digest": flow_rows_sha256(rows),
                "partition_manifest_digests": partition_digests,
            }
        )
    )


@dataclass(frozen=True)
class InstitutionalResearchInput:
    dataset_id: str
    dataset_digest: str
    rows: tuple[InstitutionalFlowDaily, ...]
    manifests: tuple[InstitutionalPartitionManifest, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dataset_id",
            _non_empty(self.dataset_id, "dataset_id"),
        )
        _require_sha256(self.dataset_digest, "dataset_digest")
        ordered_rows = tuple(
            sorted(
                self.rows,
                key=lambda row: (
                    row.market.value,
                    row.session_date,
                    row.symbol,
                    row.partition_id,
                ),
            )
        )
        ordered_manifests = tuple(
            sorted(
                self.manifests,
                key=lambda manifest: (
                    manifest.market.value,
                    manifest.session_date,
                    manifest.partition_id,
                ),
            )
        )
        self._validate(ordered_rows, ordered_manifests)
        if institutional_bundle_sha256(ordered_rows, ordered_manifests) != (
            self.dataset_digest
        ):
            raise ResearchInputError(
                "INSTITUTIONAL_DIGEST_MISMATCH",
                "institutional rows/manifests differ from the pinned dataset digest",
            )
        object.__setattr__(self, "rows", ordered_rows)
        object.__setattr__(self, "manifests", ordered_manifests)

    @staticmethod
    def _validate(
        rows: tuple[InstitutionalFlowDaily, ...],
        manifests: tuple[InstitutionalPartitionManifest, ...],
    ) -> None:
        if not rows or not manifests:
            raise ResearchInputError(
                "INSTITUTIONAL_INPUT_EMPTY",
                "institutional research input must contain rows and manifests",
            )
        by_partition: dict[str, list[InstitutionalFlowDaily]] = {}
        row_identities: set[tuple[InstitutionalMarket, str, date]] = set()
        for row in rows:
            identity = (row.market, row.symbol, row.session_date)
            if identity in row_identities:
                raise ResearchInputError(
                    "DUPLICATE_INSTITUTIONAL_ROW",
                    "institutional rows must be unique by market/symbol/session",
                )
            row_identities.add(identity)
            by_partition.setdefault(row.partition_id, []).append(row)

        manifest_keys: set[tuple[InstitutionalMarket, date]] = set()
        manifest_ids: set[str] = set()
        for manifest in manifests:
            if manifest.status is not PartitionStatus.VALIDATED:
                raise ResearchInputError(
                    "INSTITUTIONAL_PARTITION_NOT_VALIDATED",
                    f"partition {manifest.partition_id} is not validated",
                )
            key = (manifest.market, manifest.session_date)
            if key in manifest_keys or manifest.partition_id in manifest_ids:
                raise ResearchInputError(
                    "DUPLICATE_INSTITUTIONAL_PARTITION",
                    "one validated partition is required per market/session",
                )
            manifest_keys.add(key)
            manifest_ids.add(manifest.partition_id)
            partition_rows = tuple(by_partition.get(manifest.partition_id, ()))
            if not partition_rows:
                raise ResearchInputError(
                    "INSTITUTIONAL_PARTITION_ROWS_MISSING",
                    f"partition {manifest.partition_id} has no rows",
                )
            if manifest.normalized_row_count != len(partition_rows):
                raise ResearchInputError(
                    "INSTITUTIONAL_PARTITION_ROW_COUNT_MISMATCH",
                    f"partition {manifest.partition_id} row count differs",
                )
            if flow_rows_sha256(partition_rows) != manifest.normalized_sha256:
                raise ResearchInputError(
                    "INSTITUTIONAL_PARTITION_DIGEST_MISMATCH",
                    f"partition {manifest.partition_id} normalized digest differs",
                )
            if any(
                row.market is not manifest.market
                or row.session_date != manifest.session_date
                or row.trade_scope_id != manifest.trade_scope_id
                or row.correction_policy is not manifest.correction_policy
                or row.raw_artifact_id != manifest.raw_artifact_id
                or row.raw_sha256 != manifest.raw_sha256
                or row.retrieved_at != manifest.retrieved_at
                or row.first_observed_at != manifest.first_observed_at
                or row.usable_from_session != manifest.usable_from_session
                for row in partition_rows
            ):
                raise ResearchInputError(
                    "INSTITUTIONAL_PARTITION_IDENTITY_MISMATCH",
                    f"partition {manifest.partition_id} row identity differs",
                )
        if set(by_partition) != manifest_ids:
            raise ResearchInputError(
                "INSTITUTIONAL_MANIFEST_SET_MISMATCH",
                "every row partition must have one validated manifest",
            )

    @property
    def scope_eligible(self) -> bool:
        scope_contracts_by_market: dict[
            InstitutionalMarket, set[tuple[str, object]]
        ] = {}
        for manifest in self.manifests:
            scope_contracts_by_market.setdefault(manifest.market, set()).add(
                (manifest.trade_scope_id, manifest.correction_policy)
            )
        return all(
            len(scope_contracts) == 1
            for scope_contracts in scope_contracts_by_market.values()
        )

    @property
    def sessions_by_market(self) -> dict[InstitutionalMarket, tuple[date, ...]]:
        result: dict[InstitutionalMarket, list[date]] = {}
        for manifest in self.manifests:
            result.setdefault(manifest.market, []).append(manifest.session_date)
        return {
            market: tuple(sorted(set(sessions))) for market, sessions in result.items()
        }

    @property
    def target_sessions_by_market(self) -> dict[InstitutionalMarket, tuple[date, ...]]:
        result: dict[InstitutionalMarket, list[date]] = {}
        for manifest in self.manifests:
            result.setdefault(manifest.market, []).append(manifest.usable_from_session)
        if any(len(sessions) != len(set(sessions)) for sessions in result.values()):
            raise ResearchInputError(
                "DUPLICATE_INSTITUTIONAL_TARGET_SESSION",
                "validated partitions must map to unique target sessions per market",
            )
        return {market: tuple(sorted(sessions)) for market, sessions in result.items()}
