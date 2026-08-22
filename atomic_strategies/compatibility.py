"""Narrow runtime-specific compatibility for immutable strategy versions."""

from __future__ import annotations

from atomic_strategies.protocol import AtomicStrategy
from strategy_catalog.parameter_schema import canonical_digest


def backtest_compatible_template_digests(
    strategy: AtomicStrategy,
) -> frozenset[str]:
    """Allow an additive Local Paper binding without rewriting old backtests.

    Only strategies that explicitly opt in may replay a Version whose Template
    document is identical except that it predates LOCAL_PAPER_TICK_BIDASK.
    Local Paper admission remains strict and does not use this compatibility.
    """

    template = strategy.template
    digests = {template.template_digest}
    if not getattr(strategy, "allow_legacy_backtest_only_template", False):
        return frozenset(digests)
    backtest_binding = template.runtime_bindings.get("BACKTEST_KBAR_1M")
    if not backtest_binding:
        raise ValueError("legacy Backtest compatibility requires BACKTEST_KBAR_1M")
    legacy_document = template.template_document
    legacy_document["runtime_bindings"] = {
        "BACKTEST_KBAR_1M": backtest_binding,
    }
    digests.add(canonical_digest(legacy_document))
    return frozenset(digests)
