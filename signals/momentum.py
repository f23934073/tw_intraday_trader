"""Post-warm-up Limit-Up Momentum evaluator and family time router."""

from __future__ import annotations

from datetime import time

from config.momentum import (
    LIMIT_UP_MOMENTUM_HYPOTHESIS_V0,
    OPENING_MOMENTUM_HYPOTHESIS_V0,
    LimitUpMomentumHypothesisConfig,
    OpeningMomentumHypothesisConfig,
)
from features.models import IntradayFeatureSnapshot
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
from signals.opening_momentum import OpeningMomentumSignal


class LimitUpMomentumSignal:
    def __init__(self, config: LimitUpMomentumHypothesisConfig) -> None:
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
                rule="volume_acceleration_2m",
                feature=snapshot.volume_acceleration_2m,
                points=self._weight("volume_acceleration_2m"),
                threshold=self._config.min_volume_acceleration_2m,
                predicate=(
                    lambda value: value
                    >= self._config.min_volume_acceleration_2m
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
        block_reasons = list(snapshot.block_reasons)
        triggered = (
            snapshot.required_inputs_valid
            and score >= self._config.trigger_evidence_score
            and snapshot.price_above_vwap.value is True
            and snapshot.breakout.value is True
        )
        primary, components = self._component_signals(details, triggered)
        status = (
            SignalEvaluationStatus.INSUFFICIENT_DATA
            if not snapshot.required_inputs_valid
            else (
                SignalEvaluationStatus.TRIGGERED
                if triggered
                else SignalEvaluationStatus.NOT_TRIGGERED
            )
        )
        if snapshot.required_inputs_valid and not triggered:
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

    @staticmethod
    def _component_signals(details, triggered: bool):
        by_rule = {item.rule: item for item in details}
        components = []
        if by_rule["breakout"].passed:
            components.append(MomentumSignal.BREAKOUT)
        if by_rule["volume_acceleration_2m"].passed:
            components.append(MomentumSignal.VOLUME_ACCELERATION)
        if (
            by_rule["return_2m"].passed
            and by_rule["volume_acceleration_2m"].passed
        ):
            components.append(MomentumSignal.MOMENTUM_ACCELERATION)
        if triggered:
            components.append(MomentumSignal.LIMIT_UP_MOMENTUM)
        primary = components[-1] if components else MomentumSignal.NONE
        return primary, tuple(components)

    def _weight(self, rule: str) -> int:
        try:
            return self._weights[rule]
        except KeyError as error:
            raise ValueError(f"missing evidence weight: {rule}") from error


class MomentumSignalEngine:
    """Route by exchange event time; 09:10:00 belongs to Limit-Up family."""

    def __init__(
        self,
        *,
        opening_config: OpeningMomentumHypothesisConfig = (
            OPENING_MOMENTUM_HYPOTHESIS_V0
        ),
        limit_up_config: LimitUpMomentumHypothesisConfig = (
            LIMIT_UP_MOMENTUM_HYPOTHESIS_V0
        ),
    ) -> None:
        self._opening = OpeningMomentumSignal(opening_config)
        self._limit_up = LimitUpMomentumSignal(limit_up_config)
        self._opening_config = opening_config

    def evaluate(self, snapshot: IntradayFeatureSnapshot) -> SignalResult:
        event_time = snapshot.as_of.timetz().replace(tzinfo=None)
        if event_time < time(9, 0):
            return SignalResult(
                symbol=snapshot.symbol,
                as_of=snapshot.as_of,
                config_version=self._opening_config.family.version,
                feature_version=snapshot.feature_version,
                signal_family=self._opening_config.family.signal_family,
                signal=MomentumSignal.NONE,
                triggered_signals=(),
                momentum_acceleration_confirmed=False,
                evidence_score=0,
                evidence_max_score=self._opening_config.evidence_max_score,
                passed_rule_count=0,
                total_rule_count=len(self._opening_config.weights),
                coverage=0.0,
                data_health=snapshot.data_health.value,
                evaluation_status=SignalEvaluationStatus.OUTSIDE_WINDOW,
                block_reasons=("before_regular_session",),
            )
        if event_time < time(9, 10):
            return self._opening.evaluate(snapshot)
        return self._limit_up.evaluate(snapshot)
