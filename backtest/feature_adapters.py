"""Completed 1-minute Kbar adapter for shared Feature Specifications."""

from __future__ import annotations

from features.specifications import NormalizedFeatureSnapshot
from strategy_catalog.parameter_schema import canonical_digest


class CompletedOneMinuteKbarFeatureAdapter:
    identity = "backtest.completed-kbar-1m-feature-adapter-v1"

    def normalize(self, context) -> NormalizedFeatureSnapshot:
        session = (
            context.resolved_session_date.isoformat()
            if context.resolved_session_date is not None
            else context.bar.timestamp.date().isoformat()
        )
        input_document = {
            "symbol": context.symbol,
            "event_at": context.bar.timestamp.isoformat(),
            "close": str(context.bar.close),
            "vwap": str(context.vwap),
            "session_high_before": (
                str(context.session_high_before)
                if context.session_high_before is not None
                else None
            ),
            "cumulative_volume": context.cumulative_volume,
            "bars_seen": context.bars_seen,
        }
        return NormalizedFeatureSnapshot(
            symbol=context.symbol,
            session=session,
            as_of=context.bar.timestamp,
            adapter_identity=self.identity,
            values={
                "vwap_session_v1": str(context.vwap),
                "previous_intraday_high_v1": (
                    str(context.session_high_before)
                    if context.session_high_before is not None
                    else None
                ),
            },
            input_digest=canonical_digest(input_document),
        )
