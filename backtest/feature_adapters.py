"""Completed 1-minute Kbar adapter for shared Feature Specifications."""

from __future__ import annotations

from backtest.features import CompletedKbarFeatureState
from features.specifications import (
    FeatureRequestSpec,
    FeatureSpecificationRegistry,
    NormalizedFeatureSnapshot,
)
from strategy_catalog.parameter_schema import canonical_digest


class CompletedOneMinuteKbarFeatureAdapter:
    identity = "backtest.completed-kbar-1m-feature-adapter-v1"

    def __init__(self, requests: tuple[FeatureRequestSpec, ...] = ()) -> None:
        feature_ids = tuple(item.feature_id for item in requests)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("單一策略不可重複要求相同 Feature ID")
        registry = FeatureSpecificationRegistry()
        registry.validate_requests(requests)
        self._requests = requests
        self._specifications = {
            item.feature_id: registry.get(item.feature_id) for item in requests
        }
        self._state = CompletedKbarFeatureState()

    def reset(self) -> None:
        self._state.reset()

    @property
    def active_session(self) -> str | None:
        return self._state.active_session

    @property
    def active_state_count(self) -> int:
        return self._state.active_state_count

    def begin_session(self, session: str) -> None:
        self._state.begin_session(session)

    def normalize(self, context) -> NormalizedFeatureSnapshot:
        session = (
            context.resolved_session_date.isoformat()
            if context.resolved_session_date is not None
            else context.bar.timestamp.date().isoformat()
        )
        self.begin_session(session)
        values = {
            "vwap_session_v1": str(context.vwap),
            "previous_intraday_high_v1": (
                str(context.session_high_before)
                if context.session_high_before is not None
                else None
            ),
        }
        missing_reasons: dict[str, str] = {}
        request_digests: dict[str, str] = {}
        state_keys: dict[str, str] = {}
        rolling_evidence: dict[str, object] = {}
        for request in self._requests:
            request_digests[request.feature_id] = request.request_digest
            if request.feature_id in {"vwap_session_v1", "previous_intraday_high_v1"}:
                continue
            specification = self._specifications[request.feature_id]
            state_key = request.state_key(
                adapter_identity=self.identity,
                cadence=specification.cadence,
                symbol=context.symbol,
                session=session,
            )
            feature = self._state.apply(
                state_key=state_key,
                feature_id=request.feature_id,
                parameters=request.parameters,
                bar=context.bar,
            )
            values[request.feature_id] = (
                str(feature.value) if feature.value is not None else None
            )
            state_keys[request.feature_id] = state_key
            rolling_evidence[request.feature_id] = dict(feature.evidence)
            if feature.missing_reason is not None:
                missing_reasons[request.feature_id] = feature.missing_reason

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
            "request_digests": request_digests,
            "state_keys": state_keys,
            "rolling_evidence": rolling_evidence,
        }
        return NormalizedFeatureSnapshot(
            symbol=context.symbol,
            session=session,
            as_of=context.bar.timestamp,
            adapter_identity=self.identity,
            values=values,
            input_digest=canonical_digest(input_document),
            missing_reasons=missing_reasons,
            request_digests=request_digests,
            state_keys=state_keys,
        )
