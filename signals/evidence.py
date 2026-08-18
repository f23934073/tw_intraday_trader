"""Shared Evidence Score helpers for versioned Momentum signal families."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from features.models import FeatureStatus, FeatureValue
from signals.models import EvidenceStatus, SignalDetail


def detail_for_feature(
    *,
    rule: str,
    feature: FeatureValue,
    points: int,
    threshold: str | Decimal,
    predicate: Callable[[Decimal | int | bool | str], bool],
) -> SignalDetail:
    status = EvidenceStatus(feature.status.value)
    if feature.status is not FeatureStatus.VALID:
        return SignalDetail(
            rule=rule,
            status=status,
            passed=None,
            points_awarded=0,
            points_possible=points,
            observed_value=feature.value,
            threshold=threshold,
            source_as_of=feature.source_as_of,
            missing_reason=feature.reason,
        )
    assert feature.value is not None
    passed = predicate(feature.value)
    return SignalDetail(
        rule=rule,
        status=EvidenceStatus.VALID,
        passed=passed,
        points_awarded=points if passed else 0,
        points_possible=points,
        observed_value=feature.value,
        threshold=threshold,
        source_as_of=feature.source_as_of,
    )


def external_ratio_detail(
    *,
    current: FeatureValue,
    previous: FeatureValue,
    rising: FeatureValue,
    points: int,
    threshold: Decimal,
) -> SignalDetail:
    unavailable = next(
        (
            item
            for item in (current, previous, rising)
            if item.status is not FeatureStatus.VALID
        ),
        None,
    )
    if unavailable is not None:
        return SignalDetail(
            rule="external_ratio_rising",
            status=EvidenceStatus(unavailable.status.value),
            passed=None,
            points_awarded=0,
            points_possible=points,
            observed_value=current.value,
            threshold=f">={threshold} and rising",
            source_as_of=unavailable.source_as_of,
            missing_reason=unavailable.reason,
        )
    assert isinstance(current.value, Decimal)
    assert isinstance(previous.value, Decimal)
    passed = current.value >= threshold and rising.value is True
    observed = f"{current.value}>{previous.value}"
    return SignalDetail(
        rule="external_ratio_rising",
        status=EvidenceStatus.VALID,
        passed=passed,
        points_awarded=points if passed else 0,
        points_possible=points,
        observed_value=observed,
        threshold=f">={threshold} and rising",
        source_as_of=current.source_as_of,
    )


def score_details(details: tuple[SignalDetail, ...]) -> tuple[int, int, float]:
    score = sum(item.points_awarded for item in details)
    passed_count = sum(item.passed is True for item in details)
    valid_count = sum(item.status is EvidenceStatus.VALID for item in details)
    coverage = valid_count / len(details) if details else 0.0
    return score, passed_count, coverage
