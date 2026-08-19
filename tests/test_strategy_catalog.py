"""Contracts for the unified, versioned strategy catalog."""

from pathlib import Path
from tempfile import TemporaryDirectory

import dashboard.server as server
from backtest.application import BacktestApplicationService
from backtest.sqlite_repository import SQLiteBacktestRepository
from backtest.strategies import StrategyRegistry
from market_data.provider import MockProvider
from strategy_catalog.domain import SessionPhase, StrategyDefinition, StrategyRole, StrategySide
from strategy_catalog.service import StrategyCatalogService


def test_strategy_definition_derives_legacy_side_and_round_trips_flexible_parameters() -> None:
    definition = StrategyDefinition(
        strategy_id="custom_logic",
        display_name_zh_tw="自訂邏輯",
        version="v1",
        side=StrategySide.ENTRY,
        session_phase=SessionPhase.PRE_MARKET,
        parameters={"operator": "AND", "rules": [{"field": "gap", "gte": 0.02}]},
    )

    assert definition.role is StrategyRole.ENTRY
    assert definition.side is StrategySide.ENTRY
    assert StrategyDefinition.from_dict(definition.to_dict()).to_dict() == definition.to_dict()
    assert len(definition.definition_digest) == 64


def test_catalog_bootstraps_all_strategy_families_and_filters_by_phase() -> None:
    with TemporaryDirectory() as directory:
        repository = SQLiteBacktestRepository(Path(directory) / "strategy.sqlite3")
        catalog = StrategyCatalogService(repository, StrategyRegistry())

        all_strategies = catalog.list()
        premarket = catalog.list(session_phase="PRE_MARKET")
        entries = catalog.list(role="ENTRY")
        executable = catalog.backtest_strategies()

        assert len(all_strategies) >= 14
        assert any(item["strategy_id"] == "premarket_gap_watchlist_v1" for item in premarket)
        gap_watchlist = next(item for item in premarket if item["strategy_id"] == "premarket_gap_watchlist_v1")
        taifex_context = next(item for item in premarket if item["strategy_id"] == "taifex_overnight_context_v0")
        assert gap_watchlist["status"] == "DRAFT"
        assert taifex_context["status"] == "EXPERIMENTAL"
        assert taifex_context["role"] == "SIGNAL"
        assert taifex_context["parameters"]["observation_only"] is True
        assert taifex_context["parameters"]["affects_decisions"] is False
        assert "direction" not in taifex_context["parameters"]
        assert {item["side"] for item in entries} == {"ENTRY"}
        assert {item["side"] for item in executable} == {"ENTRY", "EXIT"}
        assert all(item["backtest_executable"] for item in executable)
        golden_cross = next(
            item for item in executable
            if item["strategy_id"] == "sma_20_60_golden_cross_entry_v1"
        )
        death_cross = next(
            item for item in executable
            if item["strategy_id"] == "sma_20_60_death_cross_exit_v1"
        )
        assert golden_cross["status"] == death_cross["status"] == "EXPERIMENTAL"
        assert golden_cross["required_capabilities"] == ["OHLCV", "KBAR_DAILY"]
        assert death_cross["parameters"]["execution_horizon"] == "DAILY_NEXT_BAR"
        hypothesis = next(item for item in entries if item["strategy_id"] == "momentum_entry_hypothesis_v0")
        assert hypothesis["backtest_executable"] is False
        assert "尚未部署" in hypothesis["backtest_unavailable_reason"]
        repository.close()


def test_database_strategy_version_is_immutable_and_idempotent() -> None:
    with TemporaryDirectory() as directory:
        repository = SQLiteBacktestRepository(Path(directory) / "strategy.sqlite3")
        catalog = StrategyCatalogService(repository, StrategyRegistry())
        payload = {
            "strategy_id": "custom_database_logic",
            "display_name_zh_tw": "資料庫自訂邏輯",
            "version": "v1",
            "role": "CANDIDATE",
            "session_phase": "PRE_MARKET",
            "status": "DRAFT",
            "parameters": {"tree": {"operator": "OR", "children": ["a", "b"]}},
        }

        assert catalog.save(payload)[1] is True
        assert catalog.save(payload)[1] is False
        try:
            catalog.save({**payload, "parameters": {"tree": {"operator": "AND"}}})
        except ValueError as error:
            assert "請建立新版本" in str(error)
        else:
            raise AssertionError("same strategy version must reject a changed definition")
        repository.close()
        reopened = SQLiteBacktestRepository(Path(directory) / "strategy.sqlite3")
        persisted = reopened.list_strategy_definitions()
        assert any(item["strategy_id"] == "custom_database_logic" for item in persisted)
        reopened.close()


def test_strategy_catalog_api_lists_and_saves_draft(monkeypatch) -> None:
    with TemporaryDirectory() as directory:
        repository = SQLiteBacktestRepository(Path(directory) / "strategy.sqlite3")
        service = BacktestApplicationService(MockProvider(), repository=repository, workers=1)
        monkeypatch.setattr(server, "_backtest_service", service)
        try:
            response = server.strategy_definitions(role="CANDIDATE", session_phase="PRE_MARKET")
            assert response["strategies"]
            assert all(item["role"] == "CANDIDATE" for item in response["strategies"])
            assert all(item["backtest_executable"] is False for item in response["strategies"])
            saved = server.save_strategy_definition(
                server.StrategyDefinitionRequest(
                    strategy_id="api_draft_logic",
                    display_name_zh_tw="API 草稿邏輯",
                    version="v1",
                    role="CANDIDATE",
                    session_phase="PRE_MARKET",
                    parameters={"rules": ["gap", "volume"]},
                )
            )
            assert saved["created"] is True
            assert saved["strategy"]["source"] == "DATABASE"
        finally:
            service.close()
            monkeypatch.setattr(server, "_backtest_service", None)
