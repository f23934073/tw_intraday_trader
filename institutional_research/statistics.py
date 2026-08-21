"""Small Decimal-only statistics used by institutional diagnostics."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext


ZERO = Decimal(0)
ONE = Decimal(1)


def mean(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    return sum(values, start=ZERO) / Decimal(len(values))


def nearest_rank(values: tuple[Decimal, ...], percentile: Decimal) -> Decimal | None:
    """Return the deterministic nearest-rank percentile for 0 <= p <= 1."""

    if not values:
        return None
    if not ZERO <= percentile <= ONE:
        raise ValueError("percentile must be between zero and one")
    ordered = sorted(values)
    if percentile == ZERO:
        return ordered[0]
    rank = int(
        (percentile * Decimal(len(ordered))).to_integral_value(rounding="ROUND_CEILING")
    )
    return ordered[rank - 1]


def average_ranks(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    """Return one-based average ranks, preserving input order."""

    if not values:
        return ()
    positions: dict[Decimal, list[int]] = defaultdict(list)
    for index, value in enumerate(values):
        positions[value].append(index)

    result = [ZERO] * len(values)
    next_rank = 1
    for value in sorted(positions):
        indexes = positions[value]
        last_rank = next_rank + len(indexes) - 1
        rank = Decimal(next_rank + last_rank) / Decimal(2)
        for index in indexes:
            result[index] = rank
        next_rank = last_rank + 1
    return tuple(result)


def percentile_ranks(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    """Map average ranks to inclusive [0, 1] percentiles."""

    if len(values) < 2:
        return ()
    denominator = Decimal(len(values) - 1)
    return tuple((rank - ONE) / denominator for rank in average_ranks(values))


def pearson(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> Decimal | None:
    if len(left) != len(right):
        raise ValueError("pearson inputs must have the same length")
    if len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    assert left_mean is not None and right_mean is not None
    numerator = sum(
        (
            (left_value - left_mean) * (right_value - right_mean)
            for left_value, right_value in zip(left, right, strict=True)
        ),
        start=ZERO,
    )
    left_squared = sum(
        ((value - left_mean) ** 2 for value in left),
        start=ZERO,
    )
    right_squared = sum(
        ((value - right_mean) ** 2 for value in right),
        start=ZERO,
    )
    if left_squared == ZERO or right_squared == ZERO:
        return None
    with localcontext() as context:
        context.prec = 36
        return numerator / (left_squared * right_squared).sqrt()


def spearman(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> Decimal | None:
    if len(left) != len(right):
        raise ValueError("spearman inputs must have the same length")
    return pearson(average_ranks(left), average_ranks(right))


def sample_standard_deviation(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    average = mean(values)
    assert average is not None
    variance = sum(
        ((value - average) ** 2 for value in values),
        start=ZERO,
    ) / Decimal(len(values) - 1)
    with localcontext() as context:
        context.prec = 36
        return variance.sqrt()
