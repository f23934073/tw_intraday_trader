"""Pure formula, partition, and trade-scope validation for institutional data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from institutional_data.domain import (
    InstitutionalFlowDaily,
    InstitutionalPartitionManifest,
    ScopeCompatibility,
    ScopeCompatibilityDecision,
    TradeScope,
)
from institutional_data.serialization import flow_rows_sha256


class ValidationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN_COMPONENT = "UNKNOWN_COMPONENT"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    symbol: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    status: ValidationStatus
    symbol: str | None = None
    field: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    checks: tuple[ValidationCheck, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.issues


def validate_flow_row(row: InstitutionalFlowDaily) -> ValidationReport:
    issues: list[ValidationIssue] = []
    checks: list[ValidationCheck] = []
    for component, buy, sell, net in (
        (
            "foreign_ex_dealer",
            row.foreign_ex_dealer_buy_shares,
            row.foreign_ex_dealer_sell_shares,
            row.foreign_ex_dealer_net_shares,
        ),
        (
            "foreign_dealer",
            row.foreign_dealer_buy_shares,
            row.foreign_dealer_sell_shares,
            row.foreign_dealer_net_shares,
        ),
        (
            "investment_trust",
            row.investment_trust_buy_shares,
            row.investment_trust_sell_shares,
            row.investment_trust_net_shares,
        ),
        (
            "dealer_proprietary",
            row.dealer_proprietary_buy_shares,
            row.dealer_proprietary_sell_shares,
            row.dealer_proprietary_net_shares,
        ),
        (
            "dealer_hedge",
            row.dealer_hedge_buy_shares,
            row.dealer_hedge_sell_shares,
            row.dealer_hedge_net_shares,
        ),
        (
            "dealer_total",
            row.dealer_total_buy_shares,
            row.dealer_total_sell_shares,
            row.dealer_total_net_shares,
        ),
    ):
        field = f"{component}_net_shares"
        if buy is None or sell is None or net is None:
            checks.append(
                ValidationCheck(
                    name=f"{component}_validation",
                    status=ValidationStatus.UNKNOWN_COMPONENT,
                    symbol=row.symbol,
                    field=field,
                    reason_code="COMPONENT_NOT_PUBLISHED",
                )
            )
        elif buy - sell != net:
            checks.append(
                ValidationCheck(
                    name=f"{component}_validation",
                    status=ValidationStatus.FAIL,
                    symbol=row.symbol,
                    field=field,
                    reason_code="COMPONENT_NET_MISMATCH",
                )
            )
            issues.append(
                ValidationIssue(
                    code="COMPONENT_NET_MISMATCH",
                    message=f"{component} net must equal buy minus sell",
                    symbol=row.symbol,
                    field=field,
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name=f"{component}_validation",
                    status=ValidationStatus.PASS,
                    symbol=row.symbol,
                    field=field,
                )
            )

    if (
        row.dealer_proprietary_buy_shares is not None
        and row.dealer_hedge_buy_shares is not None
    ):
        mismatched_fields: list[str] = []
        for field_name, actual, expected in (
            (
                "dealer_total_buy_shares",
                row.dealer_total_buy_shares,
                row.dealer_proprietary_buy_shares + row.dealer_hedge_buy_shares,
            ),
            (
                "dealer_total_sell_shares",
                row.dealer_total_sell_shares,
                row.dealer_proprietary_sell_shares + row.dealer_hedge_sell_shares,
            ),
            (
                "dealer_total_net_shares",
                row.dealer_total_net_shares,
                row.dealer_proprietary_net_shares + row.dealer_hedge_net_shares,
            ),
        ):
            if actual != expected:
                mismatched_fields.append(field_name)
                issues.append(
                    ValidationIssue(
                        code="DEALER_TOTAL_MISMATCH",
                        message="dealer total must equal proprietary plus hedge",
                        symbol=row.symbol,
                        field=field_name,
                    )
                )
        checks.append(
            ValidationCheck(
                name="dealer_component_reconciliation",
                status=(
                    ValidationStatus.FAIL
                    if mismatched_fields
                    else ValidationStatus.PASS
                ),
                symbol=row.symbol,
                reason_code=("DEALER_TOTAL_MISMATCH" if mismatched_fields else None),
            )
        )
    else:
        checks.append(
            ValidationCheck(
                name="dealer_component_reconciliation",
                status=ValidationStatus.NOT_APPLICABLE,
                symbol=row.symbol,
                reason_code="DEALER_COMPONENTS_UNAVAILABLE",
            )
        )

    expected_total = (
        row.foreign_ex_dealer_net_shares
        + row.investment_trust_net_shares
        + row.dealer_total_net_shares
    )
    if row.published_total_net_shares != expected_total:
        checks.append(
            ValidationCheck(
                name="published_total_validation",
                status=ValidationStatus.FAIL,
                symbol=row.symbol,
                field="published_total_net_shares",
                reason_code="PUBLISHED_TOTAL_MISMATCH",
            )
        )
        issues.append(
            ValidationIssue(
                code="PUBLISHED_TOTAL_MISMATCH",
                message="published total must equal foreign ex-dealer plus trust plus dealer total",
                symbol=row.symbol,
                field="published_total_net_shares",
            )
        )
    else:
        checks.append(
            ValidationCheck(
                name="published_total_validation",
                status=ValidationStatus.PASS,
                symbol=row.symbol,
                field="published_total_net_shares",
            )
        )
    return ValidationReport(tuple(issues), tuple(checks))


def validate_partition(
    manifest: InstitutionalPartitionManifest,
    rows: tuple[InstitutionalFlowDaily, ...],
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    checks: list[ValidationCheck] = []
    if not rows:
        issues.append(
            ValidationIssue(
                code="EMPTY_PARTITION",
                message="validated partition must contain at least one row",
            )
        )

    symbol_counts = Counter(row.symbol for row in rows)
    for symbol, count in sorted(symbol_counts.items()):
        if count > 1:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_SYMBOL",
                    message="partition contains duplicate symbol rows",
                    symbol=symbol,
                )
            )

    for row in rows:
        row_report = validate_flow_row(row)
        issues.extend(row_report.issues)
        checks.extend(row_report.checks)
        for code, field_name, actual, expected in (
            (
                "PARTITION_ID_MISMATCH",
                "partition_id",
                row.partition_id,
                manifest.partition_id,
            ),
            ("MARKET_MISMATCH", "market", row.market, manifest.market),
            (
                "SESSION_DATE_MISMATCH",
                "session_date",
                row.session_date,
                manifest.session_date,
            ),
            (
                "TRADE_SCOPE_MISMATCH",
                "trade_scope_id",
                row.trade_scope_id,
                manifest.trade_scope_id,
            ),
            (
                "CORRECTION_POLICY_MISMATCH",
                "correction_policy",
                row.correction_policy,
                manifest.correction_policy,
            ),
            (
                "RAW_ARTIFACT_MISMATCH",
                "raw_artifact_id",
                row.raw_artifact_id,
                manifest.raw_artifact_id,
            ),
            ("RAW_DIGEST_MISMATCH", "raw_sha256", row.raw_sha256, manifest.raw_sha256),
            (
                "RETRIEVED_AT_MISMATCH",
                "retrieved_at",
                row.retrieved_at,
                manifest.retrieved_at,
            ),
            (
                "FIRST_OBSERVED_AT_MISMATCH",
                "first_observed_at",
                row.first_observed_at,
                manifest.first_observed_at,
            ),
            (
                "USABLE_SESSION_MISMATCH",
                "usable_from_session",
                row.usable_from_session,
                manifest.usable_from_session,
            ),
        ):
            if actual != expected:
                issues.append(
                    ValidationIssue(
                        code=code,
                        message=f"row {field_name} does not match partition manifest",
                        symbol=row.symbol,
                        field=field_name,
                    )
                )

    if manifest.normalized_row_count != len(rows):
        issues.append(
            ValidationIssue(
                code="NORMALIZED_ROW_COUNT_MISMATCH",
                message="normalized row count does not match partition rows",
                field="normalized_row_count",
            )
        )
    if manifest.source_row_count < len(rows):
        issues.append(
            ValidationIssue(
                code="SOURCE_ROW_COUNT_UNDERRUN",
                message="source row count cannot be less than normalized rows",
                field="source_row_count",
            )
        )
    if manifest.normalized_sha256 != flow_rows_sha256(rows):
        issues.append(
            ValidationIssue(
                code="NORMALIZED_DIGEST_MISMATCH",
                message="normalized rows digest does not match manifest",
                field="normalized_sha256",
            )
        )
    return ValidationReport(tuple(issues), tuple(checks))


def assess_trade_scope_compatibility(
    numerator: TradeScope | None,
    denominator: TradeScope | None,
) -> ScopeCompatibilityDecision:
    if numerator is None or denominator is None:
        return ScopeCompatibilityDecision(
            status=ScopeCompatibility.UNKNOWN,
            numerator_scope_id=numerator.scope_id if numerator is not None else None,
            denominator_scope_id=(
                denominator.scope_id if denominator is not None else None
            ),
            reason_codes=("MISSING_SCOPE",),
        )

    reasons: list[str] = []
    if numerator.included_categories != denominator.included_categories:
        reasons.append("TRADE_CATEGORY_MISMATCH")
    if numerator.correction_policy != denominator.correction_policy:
        reasons.append("CORRECTION_POLICY_MISMATCH")
    return ScopeCompatibilityDecision(
        status=(
            ScopeCompatibility.SCOPE_INCOMPATIBLE
            if reasons
            else ScopeCompatibility.COMPATIBLE
        ),
        numerator_scope_id=numerator.scope_id,
        denominator_scope_id=denominator.scope_id,
        reason_codes=tuple(reasons),
    )
