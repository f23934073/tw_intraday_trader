"""As-of intraday feature evaluation with fail-closed data semantics."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from features.models import (
    FeatureEngineConfig,
    FeatureEvaluationContext,
    FeatureStatus,
    FeatureValue,
    IntradayFeatureSnapshot,
    RequestedFeatureProjection,
)
from features.ema import (
    EMA_SESSION_BAR_CAPACITY,
    EmaBar,
    EmaCrossoverFeatureValue,
    evaluate_ema_cross_up,
)
from features.opening_range import (
    OPENING_RANGE_SESSION_BAR_CAPACITY,
    OpeningRangeBar,
    OpeningRangeFeatureValue,
    evaluate_opening_range_high,
)
from features.rolling import (
    RollingBar,
    RollingFeatureValue,
    evaluate_completed_bars,
    required_bar_capacity,
)
from features.specifications import FeatureRequestSpec, FeatureSpecificationRegistry
from market_data.events import TickEvent
from market_data.health import DataHealthState
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStatus, OrderBookStore


class FeatureEngine:
    requested_feature_adapter_identity = (
        "feature-engine.completed-kbar-request-projection-v1"
    )

    def __init__(
        self,
        *,
        references: InstrumentReferenceStore,
        bars: IntradayBarStore,
        books: OrderBookStore,
        config: FeatureEngineConfig = FeatureEngineConfig(),
    ) -> None:
        self._references = references
        self._bars = bars
        self._books = books
        self._config = config

    def evaluate(
        self,
        current_tick: TickEvent,
        context: FeatureEvaluationContext,
    ) -> IntradayFeatureSnapshot:
        self._validate_evaluation(current_tick, context)
        ticks = self._eligible_ticks(current_tick)
        if not any(item.event_id == current_tick.event_id for item in ticks):
            raise ValueError("current tick must be applied before feature evaluation")

        price = self._valid(current_tick.price, current_tick)
        vwap = (
            self._valid(current_tick.average_price, current_tick)
            if current_tick.average_price is not None
            else self._missing("average_price_missing", current_tick)
        )
        prior_ticks = [
            item
            for item in ticks
            if self._event_key(item) < self._event_key(current_tick)
        ]
        previous_high = self._previous_high(prior_ticks)
        price_above_vwap = self._compare(
            price,
            vwap,
            lambda left, right: left > right,
            "price_or_vwap_unavailable",
        )
        breakout = self._compare(
            price,
            previous_high,
            lambda left, right: left > right,
            "price_or_previous_high_unavailable",
        )

        target = current_tick.event_time - self._config.price_lookback
        comparison_tick = self._tick_at_or_before(ticks, target)
        return_2m = self._return_feature(current_tick, comparison_tick, target)
        distance_to_limit = self._distance_to_limit(current_tick)
        volume_2m, baseline_2m, complete_windows, volume_acceleration = (
            self._volume_features(current_tick, ticks, context)
        )
        volume_vs_previous = self._volume_vs_previous(
            current_tick,
            ticks,
            context,
            volume_2m,
        )
        current_ratio, previous_ratio, external_rising = self._external_features(
            current_tick,
            comparison_tick,
            context,
        )
        bid_depth, ask_depth, bid_ask_ratio, book_imbalance = self._book_features(
            current_tick
        )
        opening_value, opening_mode = self._opening_feature(current_tick, context)

        required = {
            "price": price,
            "vwap": vwap,
            "previous_intraday_high": previous_high,
            "price_above_vwap": price_above_vwap,
            "breakout": breakout,
            "return_2m": return_2m,
            "distance_to_limit": distance_to_limit,
            "volume_2m": volume_2m,
            "baseline_2m": baseline_2m,
            "volume_acceleration_2m": volume_acceleration,
        }
        block_reasons = [
            f"{name}:{feature.status.value}:{feature.reason}"
            for name, feature in required.items()
            if not feature.is_valid
        ]
        if context.data_health.state is not DataHealthState.HEALTHY:
            block_reasons.append(f"data_health:{context.data_health.state.value}")
        if context.data_health.as_of < current_tick.received_at:
            block_reasons.append("data_health:STALE_BEFORE_CURRENT_EVENT")
        block_reasons.extend(self._event_block_reasons(current_tick))

        return IntradayFeatureSnapshot(
            symbol=current_tick.symbol,
            as_of=current_tick.event_time,
            current_event_id=current_tick.event_id,
            feature_version=self._config.version,
            data_health=context.data_health.state,
            required_inputs_valid=not block_reasons,
            block_reasons=tuple(block_reasons),
            price=price,
            vwap=vwap,
            previous_intraday_high=previous_high,
            price_above_vwap=price_above_vwap,
            breakout=breakout,
            return_2m=return_2m,
            distance_to_limit=distance_to_limit,
            volume_2m=volume_2m,
            baseline_2m=baseline_2m,
            baseline_complete_windows=complete_windows,
            volume_acceleration_2m=volume_acceleration,
            volume_vs_previous_2m=volume_vs_previous,
            external_ratio_session=current_ratio,
            external_ratio_session_2m_ago=previous_ratio,
            external_ratio_rising=external_rising,
            bid_depth_5=bid_depth,
            ask_depth_5=ask_depth,
            bid_ask_ratio_5=bid_ask_ratio,
            book_imbalance_5=book_imbalance,
            opening_volume_context=opening_value,
            opening_volume_context_mode=opening_mode,
        )

    def evaluate_requests(
        self,
        current_tick: TickEvent,
        requests: tuple[FeatureRequestSpec, ...],
    ) -> tuple[RequestedFeatureProjection, ...]:
        if current_tick.session_date != self._bars.session_date:
            raise ValueError("tick session does not match bar store")
        applied_tick = self._bars.latest_tick_at_or_before(
            current_tick.symbol,
            current_tick.event_time,
        )
        if applied_tick is None or applied_tick.event_id != current_tick.event_id:
            raise ValueError(
                "current tick must be applied before requested feature evaluation"
            )
        registry = FeatureSpecificationRegistry()
        registry.validate_requests(requests)
        request_digests = tuple(item.request_digest for item in requests)
        if len(request_digests) != len(set(request_digests)):
            raise ValueError("Local Paper Feature Requests 不可重複")

        completed_through = (
            current_tick.event_time.replace(second=0, microsecond=0)
            - timedelta(minutes=1)
        )
        source_bars = self._bars.bars(
            current_tick.symbol,
            through=completed_through,
        )
        projections: list[RequestedFeatureProjection] = []
        for request in requests:
            specification = registry.get(request.feature_id)
            if specification.cadence != "COMPLETED_KBAR_1M":
                raise ValueError(
                    f"Local Paper request cadence 不支援：{specification.cadence}"
                )
            if request.feature_id == "opening_range_high_v1":
                capacity = OPENING_RANGE_SESSION_BAR_CAPACITY
                bars = tuple(
                    OpeningRangeBar(
                        timestamp=item.minute,
                        high=item.high,
                        low=item.low,
                    )
                    for item in source_bars[-capacity:]
                )
                result = evaluate_opening_range_high(
                    request.parameters,
                    bars,
                )
            elif request.feature_id == "ema_cross_up_v1":
                capacity = EMA_SESSION_BAR_CAPACITY
                bars = tuple(
                    EmaBar(
                        timestamp=item.minute,
                        close=item.close,
                    )
                    for item in source_bars[-capacity:]
                )
                result = evaluate_ema_cross_up(
                    request.parameters,
                    bars,
                )
            else:
                capacity = required_bar_capacity(
                    request.feature_id,
                    request.parameters,
                )
                bars = tuple(
                    RollingBar(
                        timestamp=item.minute,
                        close=item.close,
                        volume=item.volume_lots,
                    )
                    for item in source_bars[-capacity:]
                )
                result = evaluate_completed_bars(
                    request.feature_id,
                    request.parameters,
                    bars,
                )
            projections.append(
                self._requested_projection(
                    current_tick=current_tick,
                    request=request,
                    specification=specification,
                    result=result,
                    source_as_of=(
                        bars[-1].timestamp if bars else completed_through
                    ),
                )
            )
        return tuple(projections)

    def _requested_projection(
        self,
        *,
        current_tick: TickEvent,
        request: FeatureRequestSpec,
        specification,
        result: (
            RollingFeatureValue
            | OpeningRangeFeatureValue
            | EmaCrossoverFeatureValue
        ),
        source_as_of: datetime,
    ) -> RequestedFeatureProjection:
        value = FeatureValue(
            value=result.value,
            status=(
                FeatureStatus.VALID
                if result.value is not None
                else FeatureStatus.MISSING
            ),
            source_as_of=source_as_of,
            reason=result.missing_reason,
        )
        return RequestedFeatureProjection(
            feature_id=request.feature_id,
            adapter_identity=self.requested_feature_adapter_identity,
            request_digest=request.request_digest,
            parameter_digest=request.parameter_digest,
            specification_digest=specification.specification_digest,
            implementation_digest=specification.implementation_digest,
            parameters=request.parameters,
            state_key=request.state_key(
                adapter_identity=self.requested_feature_adapter_identity,
                cadence=specification.cadence,
                symbol=current_tick.symbol,
                session=current_tick.session_date.isoformat(),
            ),
            value=value,
            evidence=result.evidence,
        )

    def _validate_evaluation(
        self,
        current_tick: TickEvent,
        context: FeatureEvaluationContext,
    ) -> None:
        session_date = current_tick.session_date
        if session_date != self._bars.session_date:
            raise ValueError("tick session does not match bar store")
        if session_date != self._books.session_date:
            raise ValueError("tick session does not match book store")
        if session_date != self._references.session_date:
            raise ValueError("tick session does not match reference store")
        if session_date != context.data_health.session_date:
            raise ValueError("tick session does not match DataHealth")
        if (
            context.tick_coverage_started_at is not None
            and context.tick_coverage_started_at > current_tick.event_time
        ):
            raise ValueError("tick coverage cannot start after current event")

    def _eligible_ticks(self, current_tick: TickEvent) -> tuple[TickEvent, ...]:
        current_key = self._event_key(current_tick)
        return tuple(
            item
            for item in self._bars.ticks(
                current_tick.symbol,
                through=current_tick.event_time,
            )
            if self._event_key(item) <= current_key
        )

    @staticmethod
    def _event_key(event: TickEvent) -> tuple[datetime, int]:
        return event.event_time, event.ingress_sequence

    def _previous_high(self, ticks: list[TickEvent]) -> FeatureValue:
        if not ticks:
            return self._missing("no_tick_strictly_before_current")
        selected = max(ticks, key=lambda item: item.intraday_high)
        return self._valid(selected.intraday_high, selected)

    def _tick_at_or_before(
        self,
        ticks: tuple[TickEvent, ...],
        target: datetime,
    ) -> TickEvent | None:
        selected = None
        for event in reversed(ticks):
            if event.event_time <= target:
                selected = event
                break
        if selected is None:
            return None
        if target - selected.event_time > self._config.price_lookback_tolerance:
            return None
        return selected

    def _return_feature(
        self,
        current: TickEvent,
        comparison: TickEvent | None,
        target: datetime,
    ) -> FeatureValue:
        if comparison is None:
            return FeatureValue(
                value=None,
                status=FeatureStatus.MISSING,
                source_as_of=target,
                reason="no_price_at_or_before_target_within_tolerance",
            )
        return FeatureValue(
            value=current.price / comparison.price - Decimal("1"),
            status=FeatureStatus.VALID,
            source_as_of=current.event_time,
            source_event_ids=(comparison.event_id, current.event_id),
        )

    def _distance_to_limit(self, current: TickEvent) -> FeatureValue:
        reference = self._references.get(current.symbol)
        if reference is None:
            return self._missing("instrument_reference_missing", current)
        if not reference.eligible_for_limit_up_momentum:
            return self._missing("current_session_limit_up_price_unavailable", current)
        assert reference.limit_up_price is not None
        return self._valid(
            reference.limit_up_price / current.price - Decimal("1"),
            current,
        )

    def _volume_features(
        self,
        current: TickEvent,
        ticks: tuple[TickEvent, ...],
        context: FeatureEvaluationContext,
    ) -> tuple[FeatureValue, FeatureValue, int, FeatureValue]:
        window = self._config.volume_window
        current_start = current.event_time - window
        volume_2m = self._window_volume(
            ticks,
            start=current_start,
            end=current.event_time,
            coverage_started_at=context.tick_coverage_started_at,
            context=context,
        )

        complete_values: list[Decimal] = []
        source_ids: list[str] = []
        for offset in range(1, self._config.baseline_window_count + 1):
            end = current.event_time - window * offset
            start = end - window
            feature = self._window_volume(
                ticks,
                start=start,
                end=end,
                coverage_started_at=context.tick_coverage_started_at,
                context=context,
            )
            if feature.is_valid:
                assert isinstance(feature.value, int)
                complete_values.append(Decimal(feature.value))
                source_ids.extend(feature.source_event_ids)

        complete_count = len(complete_values)
        if complete_count < self._config.minimum_complete_baseline_windows:
            baseline = FeatureValue(
                value=None,
                status=FeatureStatus.MISSING,
                source_as_of=current.event_time,
                reason=(
                    "insufficient_complete_baseline_windows:"
                    f"{complete_count}/{self._config.baseline_window_count}"
                ),
                source_event_ids=tuple(source_ids),
            )
        else:
            baseline = FeatureValue(
                value=self._median(complete_values),
                status=FeatureStatus.VALID,
                source_as_of=current.event_time,
                source_event_ids=tuple(source_ids),
            )

        if not volume_2m.is_valid:
            acceleration = self._copy_unavailable(
                volume_2m,
                "current_volume_window_unavailable",
            )
        elif not baseline.is_valid:
            acceleration = self._copy_unavailable(
                baseline,
                "baseline_volume_unavailable",
            )
        elif baseline.value == 0:
            acceleration = self._missing(
                "baseline_volume_zero",
                source_as_of=current.event_time,
            )
        else:
            assert isinstance(volume_2m.value, int)
            assert isinstance(baseline.value, Decimal)
            acceleration = FeatureValue(
                value=Decimal(volume_2m.value) / baseline.value,
                status=FeatureStatus.VALID,
                source_as_of=current.event_time,
                source_event_ids=(
                    *volume_2m.source_event_ids,
                    *baseline.source_event_ids,
                ),
            )
        return volume_2m, baseline, complete_count, acceleration

    def _volume_vs_previous(
        self,
        current: TickEvent,
        ticks: tuple[TickEvent, ...],
        context: FeatureEvaluationContext,
        volume_2m: FeatureValue,
    ) -> FeatureValue:
        end = current.event_time - self._config.volume_window
        start = end - self._config.volume_window
        previous = self._window_volume(
            ticks,
            start=start,
            end=end,
            coverage_started_at=context.tick_coverage_started_at,
            context=context,
        )
        if not volume_2m.is_valid:
            return self._copy_unavailable(
                volume_2m,
                "current_volume_window_unavailable",
            )
        if not previous.is_valid:
            return self._copy_unavailable(
                previous,
                "previous_volume_window_unavailable",
            )
        if previous.value == 0:
            return self._missing(
                "previous_volume_window_zero",
                source_as_of=current.event_time,
            )
        assert isinstance(volume_2m.value, int)
        assert isinstance(previous.value, int)
        return FeatureValue(
            value=Decimal(volume_2m.value) / Decimal(previous.value),
            status=FeatureStatus.VALID,
            source_as_of=current.event_time,
            source_event_ids=(
                *volume_2m.source_event_ids,
                *previous.source_event_ids,
            ),
        )

    def _window_volume(
        self,
        ticks: tuple[TickEvent, ...],
        *,
        start: datetime,
        end: datetime,
        coverage_started_at: datetime | None,
        context: FeatureEvaluationContext,
    ) -> FeatureValue:
        if context.data_health.state is not DataHealthState.HEALTHY:
            return self._missing(
                f"data_health_{context.data_health.state.value.lower()}",
                source_as_of=end,
            )
        if context.data_health.gap_count:
            return self._missing("cumulative_volume_gap", source_as_of=end)
        if coverage_started_at is None or coverage_started_at > start:
            return self._missing(
                "tick_coverage_does_not_span_window",
                source_as_of=end,
            )
        events = [item for item in ticks if start < item.event_time <= end]
        return FeatureValue(
            value=sum(item.tick_volume_lots for item in events),
            status=FeatureStatus.VALID,
            source_as_of=end,
            source_event_ids=tuple(item.event_id for item in events),
        )

    def _external_features(
        self,
        current: TickEvent,
        comparison: TickEvent | None,
        context: FeatureEvaluationContext,
    ) -> tuple[FeatureValue, FeatureValue, FeatureValue]:
        if not context.aggressor_mapping_verified:
            unavailable = FeatureValue(
                value=None,
                status=FeatureStatus.UNVERIFIED,
                source_as_of=current.event_time,
                reason="aggressor_side_mapping_not_verified",
            )
            return unavailable, unavailable, unavailable
        current_ratio = self._external_ratio(current)
        previous_ratio = (
            self._external_ratio(comparison)
            if comparison is not None
            else self._missing(
                "external_ratio_comparison_tick_unavailable",
                source_as_of=current.event_time - self._config.price_lookback,
            )
        )
        rising = self._compare(
            current_ratio,
            previous_ratio,
            lambda left, right: left > right,
            "external_ratio_or_comparison_unavailable",
        )
        return current_ratio, previous_ratio, rising

    def _external_ratio(self, event: TickEvent) -> FeatureValue:
        buy = event.buy_aggressor_total_lots
        sell = event.sell_aggressor_total_lots
        if buy is None or sell is None:
            return self._missing("aggressor_cumulative_totals_missing", event)
        denominator = buy + sell
        if denominator == 0:
            return self._missing("aggressor_cumulative_total_zero", event)
        return self._valid(Decimal(buy) / Decimal(denominator), event)

    def _book_features(
        self,
        current: TickEvent,
    ) -> tuple[FeatureValue, FeatureValue, FeatureValue, FeatureValue]:
        snapshot = self._books.at_or_before(
            current.symbol,
            as_of=current.event_time,
            max_age=self._config.order_book_max_age,
        )
        if snapshot.event is None:
            missing = FeatureValue(
                value=None,
                status=FeatureStatus.MISSING,
                source_as_of=current.event_time,
                reason=snapshot.reason or "order_book_missing",
            )
            return missing, missing, missing, missing

        event = snapshot.event
        bid = sum(event.bid_volume_lots[:5])
        ask = sum(event.ask_volume_lots[:5])
        status = (
            FeatureStatus.VALID
            if snapshot.status is OrderBookStatus.VALID
            else FeatureStatus.STALE
        )
        reason = snapshot.reason if status is not FeatureStatus.VALID else None
        bid_value = FeatureValue(
            value=bid,
            status=status,
            source_as_of=event.event_time,
            reason=reason,
            source_event_ids=(event.event_id,),
        )
        ask_value = FeatureValue(
            value=ask,
            status=status,
            source_as_of=event.event_time,
            reason=reason,
            source_event_ids=(event.event_id,),
        )
        if status is not FeatureStatus.VALID:
            unavailable = FeatureValue(
                value=None,
                status=status,
                source_as_of=event.event_time,
                reason=reason,
                source_event_ids=(event.event_id,),
            )
            return bid_value, ask_value, unavailable, unavailable

        ratio = (
            self._missing(
                "ask_depth_zero",
                source_as_of=event.event_time,
                source_event_ids=(event.event_id,),
            )
            if ask == 0
            else FeatureValue(
                value=Decimal(bid) / Decimal(ask),
                status=FeatureStatus.VALID,
                source_as_of=event.event_time,
                source_event_ids=(event.event_id,),
            )
        )
        total = bid + ask
        imbalance = (
            self._missing(
                "total_book_depth_zero",
                source_as_of=event.event_time,
                source_event_ids=(event.event_id,),
            )
            if total == 0
            else FeatureValue(
                value=Decimal(bid - ask) / Decimal(total),
                status=FeatureStatus.VALID,
                source_as_of=event.event_time,
                source_event_ids=(event.event_id,),
            )
        )
        return bid_value, ask_value, ratio, imbalance

    def _opening_feature(
        self,
        current: TickEvent,
        context: FeatureEvaluationContext,
    ) -> tuple[FeatureValue, str | None]:
        opening = context.opening_volume_context
        if opening is None:
            return self._missing("opening_volume_context_not_supplied", current), None
        if (
            opening.value.source_as_of is not None
            and opening.value.source_as_of > current.event_time
        ):
            return (
                self._missing(
                    "opening_volume_context_uses_future_data",
                    source_as_of=opening.value.source_as_of,
                ),
                opening.mode,
            )
        return opening.value, opening.mode

    @staticmethod
    def _event_block_reasons(current: TickEvent) -> tuple[str, ...]:
        reasons = []
        if current.suspended:
            reasons.append("current_tick:suspended")
        if current.simulated_trade:
            reasons.append("current_tick:simulated_trade")
        if current.intraday_odd:
            reasons.append("current_tick:intraday_odd")
        return tuple(reasons)

    @staticmethod
    def _median(values: list[Decimal]) -> Decimal:
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / Decimal("2")

    @staticmethod
    def _valid(value: Decimal | int | bool, event: TickEvent) -> FeatureValue:
        return FeatureValue(
            value=value,
            status=FeatureStatus.VALID,
            source_as_of=event.event_time,
            source_event_ids=(event.event_id,),
        )

    @staticmethod
    def _missing(
        reason: str,
        event: TickEvent | None = None,
        *,
        source_as_of: datetime | None = None,
        source_event_ids: tuple[str, ...] = (),
    ) -> FeatureValue:
        return FeatureValue(
            value=None,
            status=FeatureStatus.MISSING,
            source_as_of=(event.event_time if event is not None else source_as_of),
            reason=reason,
            source_event_ids=(
                (event.event_id,) if event is not None else source_event_ids
            ),
        )

    @staticmethod
    def _copy_unavailable(feature: FeatureValue, reason: str) -> FeatureValue:
        return FeatureValue(
            value=None,
            status=feature.status,
            source_as_of=feature.source_as_of,
            reason=f"{reason}:{feature.reason}",
            source_event_ids=feature.source_event_ids,
        )

    @staticmethod
    def _compare(
        left: FeatureValue,
        right: FeatureValue,
        predicate: Callable[[Decimal | int, Decimal | int], bool],
        reason: str,
    ) -> FeatureValue:
        if not left.is_valid:
            return FeatureEngine._copy_unavailable(left, reason)
        if not right.is_valid:
            return FeatureEngine._copy_unavailable(right, reason)
        assert isinstance(left.value, (Decimal, int))
        assert isinstance(right.value, (Decimal, int))
        return FeatureValue(
            value=predicate(left.value, right.value),
            status=FeatureStatus.VALID,
            source_as_of=left.source_as_of,
            source_event_ids=(
                *left.source_event_ids,
                *right.source_event_ids,
            ),
        )
