"""09:00-09:10 Opening Momentum evaluator."""

from __future__ import annotations

from config.momentum import OpeningMomentumHypothesisConfig
from features.models import FeatureStatus, IntradayFeatureSnapshot
from market_data.health import DataHealthState
from signals.evidence import (
    detail_for_feature,
    external_ratio_detail,
    score_details,
)
from signals.models import (
    MomentumSignal,
    SignalEvaluationStatus,
    SignalResult,
)


class OpeningMomentumSignal:
    def __init__(self, config: OpeningMomentumHypothesisConfig) -> None:
        self._config = config
        self._weights = {item.rule: item.points for item in config.weights}

    def evaluate(self, snapshot: IntradayFeatureSnapshot) -> SignalResult:
        details = (
            detail_for_feature(
                rule="price_above_vwap",
                feature=snapshot.price_above_vwap,
                points=self._weight("price_above_vwap"),
                threshold="price > vwap",
                predicate=lambda value: value is True,
            ),
            detail_for_feature(
                rule="breakout",
                feature=snapshot.breakout,
                points=self._weight("breakout"),
                threshold="price > strict previous intraday high",
                predicate=lambda value: value is True,
            ),
            detail_for_feature(
                rule="return_2m",
                feature=snapshot.return_2m,
                points=self._weight("return_2m"),
                threshold=self._config.min_return_2m,
                predicate=lambda value: value >= self._config.min_return_2m,
            ),
            detail_for_feature(
                rule="distance_to_limit",
                feature=snapshot.distance_to_limit,
                points=self._weight("distance_to_limit"),
                threshold=self._config.max_distance_to_limit,
                predicate=lambda value: value <= self._config.max_distance_to_limit,
            ),
            detail_for_feature(
                rule="opening_volume_context",
                feature=snapshot.opening_volume_context,
                points=self._weight("opening_volume_context"),
                threshold=self._config.min_opening_volume_context,
                predicate=(
                    lambda value: value >= self._config.min_opening_volume_context
                ),
            ),
            external_ratio_detail(
                current=snapshot.external_ratio_session,
                previous=snapshot.external_ratio_session_2m_ago,
                rising=snapshot.external_ratio_rising,
                points=self._weight("external_ratio_rising"),
                threshold=self._config.min_external_ratio,
            ),
        )
        score, passed_count, coverage = score_details(details)
        block_reasons = self._required_block_reasons(snapshot)
        triggered = (
            not block_reasons
            and score >= self._config.trigger_evidence_score
            and snapshot.price_above_vwap.value is True
            and snapshot.breakout.value is True
        )
        primary, components = self._component_signals(details, triggered)
        status = (
            SignalEvaluationStatus.INSUFFICIENT_DATA
            if block_reasons
            else (
                SignalEvaluationStatus.TRIGGERED
                if triggered
                else SignalEvaluationStatus.NOT_TRIGGERED
            )
        )
        if not block_reasons and not triggered:
            if score < self._config.trigger_evidence_score:
                block_reasons.append("evidence_score_below_threshold")
            if snapshot.price_above_vwap.value is not True:
                block_reasons.append("price_above_vwap_regime_guard_failed")
            if snapshot.breakout.value is not True:
                block_reasons.append("breakout_regime_guard_failed")
        return SignalResult(
            symbol=snapshot.symbol,
            as_of=snapshot.as_of,
            config_version=self._config.family.version,
            feature_version=snapshot.feature_version,
            signal_family=self._config.family.signal_family,
            signal=primary,
            triggered_signals=components,
            momentum_acceleration_confirmed=(
                self._config.family.confirms_acceleration(primary)
            ),
            evidence_score=score,
            evidence_max_score=self._config.evidence_max_score,
            passed_rule_count=passed_count,
            total_rule_count=len(details),
            coverage=coverage,
            data_health=snapshot.data_health.value,
            evaluation_status=status,
            details=details,
            block_reasons=tuple(block_reasons),
        )

    def _required_block_reasons(
        self,
        snapshot: IntradayFeatureSnapshot,
    ) -> list[str]:
        required = {
            "price": snapshot.price,
            "vwap": snapshot.vwap,
            "previous_intraday_high": snapshot.previous_intraday_high,
            "price_above_vwap": snapshot.price_above_vwap,
            "breakout": snapshot.breakout,
            "return_2m": snapshot.return_2m,
            "distance_to_limit": snapshot.distance_to_limit,
            "opening_volume_context": snapshot.opening_volume_context,
        }
        reasons = [
            f"{name}:{value.status.value}:{value.reason}"
            for name, value in required.items()
            if value.status is not FeatureStatus.VALID
        ]
        if not self._config.runtime_ready:
            reasons.append("opening_volume_context_mode_unconfigured")
        elif (
            snapshot.opening_volume_context_mode
            != self._config.opening_volume_context_mode
        ):
            reasons.append("opening_volume_context_mode_mismatch")
        if snapshot.data_health is not DataHealthState.HEALTHY:
            reasons.append(f"data_health:{snapshot.data_health.value}")
        reasons.extend(
            item
            for item in snapshot.block_reasons
            if item.startswith("current_tick:") or item.startswith("data_health:")
        )
        return reasons

    @staticmethod
    def _component_signals(details, triggered: bool):
        by_rule = {item.rule: item for item in details}
        components = []
        if by_rule["breakout"].passed:
            components.append(MomentumSignal.BREAKOUT)
        if by_rule["opening_volume_context"].passed:
            components.append(MomentumSignal.VOLUME_ACCELERATION)
        if (
            by_rule["return_2m"].passed
            and by_rule["opening_volume_context"].passed
        ):
            components.append(MomentumSignal.MOMENTUM_ACCELERATION)
        if triggered:
            components.append(MomentumSignal.OPENING_MOMENTUM)
        primary = components[-1] if components else MomentumSignal.NONE
        return primary, tuple(components)

    def _weight(self, rule: str) -> int:
        try:
            return self._weights[rule]
        except KeyError as error:
            raise ValueError(f"missing evidence weight: {rule}") from error
