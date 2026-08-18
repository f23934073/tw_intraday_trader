"""Application service for the unified strategy catalog."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from strategy_catalog.domain import (
    SessionPhase,
    StrategyDefinition,
    StrategyRole,
    StrategySource,
    StrategyStatus,
)


class StrategyCatalogRepository(Protocol):
    def upsert_strategy_definition(self, definition: Mapping[str, Any]) -> bool:
        """Persist once; return True when a new immutable version was created."""

    def list_strategy_definitions(
        self,
        *,
        role: str | None = None,
        session_phase: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        ...


_BUILTIN_BINDINGS = {
    "backtest.legacy_gap_volume_vwap_entry_v1",
    "backtest.momentum_breakout_entry_v1",
    "backtest.stop_loss_exit_v1",
    "backtest.take_profit_exit_v1",
    "backtest.end_of_day_exit_v1",
    "candidate.gap_up",
    "candidate.high_volume",
    "candidate.relative_volume",
    "candidate.premarket_gap_up",
    "scoring.gap_score",
    "scoring.above_vwap",
    "signals.opening_momentum",
    "signals.limit_up_momentum",
    "signals.momentum_entry",
}


def _catalog_definition(
    *,
    strategy_id: str,
    display_name_zh_tw: str,
    version: str,
    role: StrategyRole,
    session_phase: SessionPhase,
    description_zh_tw: str,
    execution_binding: str,
    parameters: Mapping[str, Any],
    required_capabilities: tuple[str, ...] = ("OHLCV",),
    tags: tuple[str, ...] = (),
    status: StrategyStatus = StrategyStatus.ACTIVE,
    code_identity: str = "catalog-metadata-v1",
) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=strategy_id,
        display_name_zh_tw=display_name_zh_tw,
        version=version,
        role=role,
        session_phase=session_phase,
        status=status,
        description_zh_tw=description_zh_tw,
        execution_binding=execution_binding,
        required_capabilities=required_capabilities,
        parameters=parameters,
        tags=tags,
        code_identity=code_identity,
        source=StrategySource.CODE,
    )


def builtin_definitions(registry: Any) -> tuple[StrategyDefinition, ...]:
    """Return code-owned definitions, including non-backtest strategy families."""

    definitions = list(registry.definitions())
    definitions.extend(
        [
            _catalog_definition(
                strategy_id="premarket_gap_watchlist_v1",
                display_name_zh_tw="盤前跳空觀察名單策略",
                version="v1",
                role=StrategyRole.CANDIDATE,
                session_phase=SessionPhase.PRE_MARKET,
                status=StrategyStatus.DRAFT,
                description_zh_tw="以盤前試撮、前一日收盤與可取得的盤前量價資料建立觀察名單。",
                execution_binding="candidate.premarket_gap_up",
                required_capabilities=("PREOPEN_INDICATIVE", "OHLCV"),
                parameters={"gap_up_min_pct": "0.02", "gap_up_max_pct": "0.04", "cutoff": "08:50"},
                tags=("盤前", "觀察名單"),
            ),
            _catalog_definition(
                strategy_id="gap_up_candidate_v1",
                display_name_zh_tw="開盤跳空候選策略",
                version="v1",
                role=StrategyRole.CANDIDATE,
                session_phase=SessionPhase.OPENING,
                description_zh_tw="開盤後以當日開盤價相對前收的跳空幅度加入候選池。",
                execution_binding="candidate.gap_up",
                parameters={"gap_up_min_pct": "0.02", "gap_up_max_pct": "0.04"},
                tags=("候選", "跳空"),
            ),
            _catalog_definition(
                strategy_id="high_volume_candidate_v1",
                display_name_zh_tw="盤中高成交量候選策略",
                version="v1",
                role=StrategyRole.CANDIDATE,
                session_phase=SessionPhase.INTRADAY,
                description_zh_tw="盤中累積成交量達門檻時加入候選池；不直接代表買入。",
                execution_binding="candidate.high_volume",
                parameters={"min_cumulative_volume": 100_000},
                tags=("候選", "量能"),
            ),
            _catalog_definition(
                strategy_id="relative_volume_candidate_v1",
                display_name_zh_tw="相對成交量候選策略",
                version="v1",
                role=StrategyRole.CANDIDATE,
                session_phase=SessionPhase.INTRADAY,
                status=StrategyStatus.EXPERIMENTAL,
                description_zh_tw="以歷史同時段量能基準比較盤中相對成交量。",
                execution_binding="candidate.relative_volume",
                parameters={"relative_volume_min": "1.50", "min_history_bars": 20},
                tags=("候選", "量能", "實驗中"),
            ),
            _catalog_definition(
                strategy_id="gap_score_v1",
                display_name_zh_tw="跳空評分規則",
                version="v1",
                role=StrategyRole.SCORE,
                session_phase=SessionPhase.OPENING,
                description_zh_tw="將跳空幅度轉換成買入評分的一個組成項。",
                execution_binding="scoring.gap_score",
                parameters={"min_gap_pct": "0.02", "max_gap_pct": "0.04", "points": 20},
                tags=("評分", "買入證據"),
            ),
            _catalog_definition(
                strategy_id="above_vwap_v1",
                display_name_zh_tw="站上 VWAP 評分規則",
                version="v1",
                role=StrategyRole.SCORE,
                session_phase=SessionPhase.INTRADAY,
                description_zh_tw="收盤價高於當日 VWAP 時提供買入評分。",
                execution_binding="scoring.above_vwap",
                parameters={"points": 20, "strictly_above": True},
                tags=("評分", "VWAP"),
            ),
            _catalog_definition(
                strategy_id="opening_momentum_hypothesis_v0",
                display_name_zh_tw="開盤動能假說",
                version="v0",
                role=StrategyRole.SIGNAL,
                session_phase=SessionPhase.OPENING,
                status=StrategyStatus.EXPERIMENTAL,
                description_zh_tw="開盤前幾分鐘的價格、VWAP、突破與量能證據集合；目前是訊號研究，不直接下單。",
                execution_binding="signals.opening_momentum",
                required_capabilities=("TICK", "BIDASK", "OHLCV"),
                parameters={"return_min_pct": "0.015", "distance_to_limit_max_pct": "3.0", "evidence_score": 70},
                tags=("盤中", "動能", "研究中"),
                code_identity="opening-momentum-hypothesis-v0",
            ),
            _catalog_definition(
                strategy_id="limit_up_momentum_hypothesis_v0",
                display_name_zh_tw="漲停加速動能假說",
                version="v0",
                role=StrategyRole.SIGNAL,
                session_phase=SessionPhase.INTRADAY,
                status=StrategyStatus.EXPERIMENTAL,
                description_zh_tw="以漲停距離、短線報酬、突破與委買委賣證據追蹤動能 episode。",
                execution_binding="signals.limit_up_momentum",
                required_capabilities=("TICK", "BIDASK", "OHLCV"),
                parameters={"return_2m_min_pct": "0.20", "distance_to_limit_max_pct": "1.0", "evidence_score": 70},
                tags=("盤中", "漲停", "研究中"),
                code_identity="limit-up-momentum-hypothesis-v0",
            ),
            _catalog_definition(
                strategy_id="momentum_entry_hypothesis_v0",
                display_name_zh_tw="動能買入假說",
                version="v0",
                role=StrategyRole.ENTRY,
                session_phase=SessionPhase.INTRADAY,
                status=StrategyStatus.EXPERIMENTAL,
                description_zh_tw="以 Momentum projection 作為候選買入條件；仍需通過 RiskGate，未授權真實下單。",
                execution_binding="signals.momentum_entry",
                required_capabilities=("TICK", "BIDASK", "OHLCV"),
                parameters={"risk_gate_required": True, "real_money": False},
                tags=("盤中", "買入", "研究中", "RiskGate"),
                code_identity="momentum-entry-hypothesis-v0",
            ),
        ]
    )
    return tuple(sorted(definitions, key=lambda item: (item.role.value, item.session_phase.value, item.strategy_id, item.version)))


class StrategyCatalogService:
    """Coordinates code-owned bootstrap and database-owned catalog versions."""

    def __init__(self, repository: StrategyCatalogRepository, registry: Any) -> None:
        self._repository = repository
        self._registry = registry
        self.bootstrap()

    def bootstrap(self) -> None:
        for definition in builtin_definitions(self._registry):
            self._repository.upsert_strategy_definition(self._record(definition))

    def list(
        self,
        *,
        role: str | None = None,
        session_phase: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self._repository.list_strategy_definitions(
            role=self._normalize_filter(role),
            session_phase=self._normalize_filter(session_phase),
            status=self._normalize_filter(status),
        )
        return [self._with_backtest_execution_status(record) for record in records]

    def backtest_strategies(self, side: str | None = None) -> list[dict[str, Any]]:
        """Return catalog definitions that exactly match deployed backtest code.

        Catalog rows are metadata, not executable programs.  A row is selectable
        only when its immutable definition matches a server-side registry entry.
        """

        normalized = self._normalize_filter(side)
        if normalized is not None and normalized not in {StrategyRole.ENTRY.value, StrategyRole.EXIT.value}:
            raise ValueError("回測策略方向必須是 ENTRY 或 EXIT")
        catalog_by_version = {
            str(record["version_id"]): record
            for record in self.list(role=normalized)
        }
        return [
            catalog_by_version[definition.version_id]
            for definition in self._registry.definitions()
            if (normalized is None or definition.side.value == normalized)
            and definition.version_id in catalog_by_version
            and catalog_by_version[definition.version_id]["backtest_executable"]
        ]

    def save(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        data = dict(payload)
        data["source"] = StrategySource.DATABASE.value
        definition = StrategyDefinition.from_dict(data)
        if definition.status in {StrategyStatus.ACTIVE, StrategyStatus.EXPERIMENTAL}:
            if definition.execution_binding not in _BUILTIN_BINDINGS:
                raise ValueError("ACTIVE/EXPERIMENTAL 策略必須使用已部署的 execution_binding；新邏輯請先存為 DRAFT")
        created = self._repository.upsert_strategy_definition(self._record(definition))
        return self._public(definition), created

    @staticmethod
    def _normalize_filter(value: str | None) -> str | None:
        return value.strip().upper() if value and value.strip() else None

    def _with_backtest_execution_status(self, record: Mapping[str, Any]) -> dict[str, Any]:
        public = dict(record)
        runtime_definitions = {
            definition.version_id: definition
            for definition in self._registry.definitions()
        }
        runtime = runtime_definitions.get(str(public.get("version_id") or ""))
        role = str(public.get("role") or "")
        if role not in {StrategyRole.ENTRY.value, StrategyRole.EXIT.value}:
            reason = "此策略是候選、評分或訊號 metadata，不直接建立回測委託"
        elif runtime is None:
            reason = "尚未部署對應的歷史回測執行程式"
        elif str(public.get("execution_binding") or "") != runtime.execution_binding:
            reason = "策略目錄與伺服器 execution binding 不一致"
        elif str(public.get("definition_digest") or "") != runtime.definition_digest:
            reason = "策略目錄版本與伺服器執行版本不一致"
        else:
            reason = ""
        public["backtest_executable"] = not reason
        public["backtest_unavailable_reason"] = reason or None
        return public

    @staticmethod
    def _record(definition: StrategyDefinition) -> dict[str, Any]:
        return {
            **definition.to_dict(),
            "version_id": definition.version_id,
            "definition_digest": definition.definition_digest,
        }

    @staticmethod
    def _public(definition: StrategyDefinition) -> dict[str, Any]:
        return StrategyCatalogService._record(definition)
