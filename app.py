"""
app.py — Orchestration Layer

台股盤中即時選股與交易決策系統 MVP

執行方式：
    python app.py

功能：
    1. 從 Market Data Provider 取得全市場資料，寫入 MarketDataStore
    2. Candidate Engine 掃描 MarketDataStore 的最新行情
    3. 合併手動觀察清單（AUTO + MANUAL 可同時存在）
    4. 對 Candidate Pool 計算買入評分（評分時從 Store 取最新資料）
    5. 監控持倉，提供 HOLD / EXIT 決策

此檔案只負責串接各模組，不放 business logic。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv

from candidate.engine import CandidateEngine
from candidate.models import Candidate, CandidateSource
from candidate.rules import GapUpRule, HighVolumeRule
from config import settings
from market_data.models import StockData
from market_data.provider import MarketDataProvider, MockProvider
from market_data.store import MarketDataStore
from position.exit_rules import ExitRule, StopLossRule, TakeProfitRule
from position.manager import PositionManager
from position.models import Position
from scoring.engine import BuyScoreEngine
from scoring.models import BuyScoreResult
from scoring.rules import AboveVWAPRule, GapScoreRule

load_dotenv()


@dataclass
class CandidateEvaluation:
    """Candidate 與其最新行情、買入評分的同一輪掃描結果。"""

    candidate: Candidate
    stock: StockData
    score_result: BuyScoreResult


@dataclass
class PositionEvaluation:
    """持倉與其最新行情、損益、出場規則結果。"""

    position: Position
    stock: StockData
    pnl_pct: float
    pnl_amount: float
    triggered_exit_rules: list[str]


@dataclass
class ScanResult:
    """供終端機與 Web 儀表板共用的單次市場掃描結果。"""

    generated_at: datetime
    provider_name: str
    loaded_symbols: int
    candidates: list[CandidateEvaluation]
    missing_candidate_symbols: list[str]
    positions: list[PositionEvaluation]
    missing_position_symbols: list[str]


# ---------------------------------------------------------------------------
# Provider 建立
# ---------------------------------------------------------------------------


def build_provider() -> MarketDataProvider:
    """依照 config.settings.PROVIDER 或環境變數選擇資料來源。"""
    provider_name = os.environ.get("PROVIDER", settings.PROVIDER)

    if provider_name == "shioaji":
        from market_data.provider import ShioajiProvider
        return ShioajiProvider()

    return MockProvider()


# ---------------------------------------------------------------------------
# Manual Watchlist 載入
# ---------------------------------------------------------------------------


def load_manual_candidates(
    symbols: set[str],
) -> list[Candidate]:
    """
    從 config.MANUAL_WATCHLIST 載入使用者手動加入的股票。

    回傳的 Candidate 只有 symbol，不帶 StockData。
    是否存在市場資料由後續從 MarketDataStore 取得時判斷。

    規則：
    - 手動加入的股票一定進 Candidate Pool
    - 不可被 Candidate Engine 自動移除
    """
    return [
        Candidate(
            symbol=symbol,
            sources={CandidateSource.MANUAL},
        )
        for symbol in symbols
    ]


# ---------------------------------------------------------------------------
# Candidate Pool 合併（支援 AUTO + MANUAL 同時存在）
# ---------------------------------------------------------------------------


def merge_candidates(
    auto: list[Candidate],
    manual: list[Candidate],
) -> list[Candidate]:
    """
    合併 Auto 與 Manual Candidate。

    合併規則：
    - AUTO + MANUAL 可以同時存在於同一個 Candidate
    - 若 symbol 同時在 AUTO 和 MANUAL：
        sources = {AUTO, MANUAL}，matched_rules 保留 AUTO 的結果
    - 若只在 MANUAL：
        sources = {MANUAL}
    - 若只在 AUTO：
        sources = {AUTO}

    這樣「系統自動選到且使用者也在觀察」的股票資訊不會丟失。
    """
    merged: dict[str, Candidate] = {}

    # 先加入 AUTO candidates
    for c in auto:
        merged[c.symbol] = c

    # 再合併 MANUAL
    for c in manual:
        if c.symbol in merged:
            # 已在 AUTO 池中 → 加入 MANUAL source，不覆蓋 matched_rules
            merged[c.symbol].sources.add(CandidateSource.MANUAL)
        else:
            # 只在 MANUAL → 直接加入
            merged[c.symbol] = c

    return list(merged.values())


# ---------------------------------------------------------------------------
# Terminal 顯示函式
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 52
DIVIDER = "-" * 52

# source icon 組合
_SOURCE_ICONS = {
    frozenset({CandidateSource.AUTO, CandidateSource.MANUAL}): "🔥👀",
    frozenset({CandidateSource.AUTO}): "🔥  ",
    frozenset({CandidateSource.MANUAL}): "  👀",
}


def _source_icon(sources: set[CandidateSource]) -> str:
    return _SOURCE_ICONS.get(frozenset(sources), "   ")


def print_header(timestamp: str) -> None:
    print()
    print(SEPARATOR)
    print(f"  {timestamp}  MARKET SCAN")
    print(SEPARATOR)


def print_candidate(
    candidate: Candidate,
    score_result: BuyScoreResult,
    stock: StockData,
) -> None:
    icon = _source_icon(candidate.sources)
    source_labels = " + ".join(sorted(s.value for s in candidate.sources))

    print()
    print(f"  {icon}  {stock.symbol} {stock.name}")
    print(f"      Source        : {source_labels}")
    print(f"      Current Price : {stock.price:.2f}")

    if candidate.matched_rules:
        print(f"      Matched Rules : {', '.join(candidate.matched_rules)}")

    print()
    print(f"      Buy Score : {score_result.total_score}")
    print()
    for detail in score_result.details:
        marker = "+" if detail.score > 0 else " "
        print(f"        {detail.rule:<18} {marker}{detail.score:>3} / {detail.max_score}")

    print()
    print(DIVIDER)


def print_position(
    evaluation: PositionEvaluation,
) -> None:
    position = evaluation.position
    stock = evaluation.stock
    pnl_sign = "+" if evaluation.pnl_pct >= 0 else ""

    decision = (
        f"🚨 EXIT  ({', '.join(evaluation.triggered_exit_rules)})"
        if evaluation.triggered_exit_rules
        else "✅ HOLD"
    )

    print()
    print(f"  💰  {position.symbol} {stock.name}")
    print(f"      Entry    : {position.entry_price:.2f}")
    print(f"      Current  : {stock.price:.2f}")
    print(f"      Quantity : {position.quantity:,}")
    print()
    print(
        f"      PnL      : {pnl_sign}{evaluation.pnl_pct:.2f}%"
        f"  ({pnl_sign}{evaluation.pnl_amount:,.0f})"
    )
    print()
    print(f"      Decision : {decision}")
    print()
    print(DIVIDER)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_scan(market: MarketDataProvider | None = None) -> ScanResult:
    """執行一次完整掃描，回傳供不同呈現介面共用的決策結果。"""
    market = market or build_provider()
    store = MarketDataStore()

    candidate_engine = CandidateEngine(
        rules=[
            GapUpRule(),
            HighVolumeRule(),
        ]
    )

    score_engine = BuyScoreEngine(
        rules=[
            GapScoreRule(),
            AboveVWAPRule(),
        ]
    )

    exit_rules: list[ExitRule] = [
        StopLossRule(),
        TakeProfitRule(),
    ]

    position_manager = PositionManager()

    # ---- 預設示範持倉（第一版手動輸入，未來改為互動式或 DB）----
    position_manager.add(Position(symbol="2317", entry_price=205.0, quantity=1000))

    # ---- 取得市場資料，寫入 MarketDataStore ----
    for stock in market.get_market_stocks():
        store.update(stock)

    # ---- Candidate Engine 掃描（從 Store 取最新資料）----
    auto_candidates = candidate_engine.scan(store.get_all())

    # ---- 手動觀察清單（只有 symbol，不帶快照）----
    manual_candidates = load_manual_candidates(settings.MANUAL_WATCHLIST)

    # ---- 合併 Candidate Pool（AUTO + MANUAL 可同時存在）----
    candidates = merge_candidates(auto_candidates, manual_candidates)

    candidate_evaluations: list[CandidateEvaluation] = []
    missing_candidate_symbols: list[str] = []

    for candidate in candidates:
        stock = store.get(candidate.symbol)
        if stock is None:
            missing_candidate_symbols.append(candidate.symbol)
            continue

        score_result = score_engine.calculate(stock)
        if score_result.total_score >= settings.MIN_DISPLAY_SCORE:
            candidate_evaluations.append(
                CandidateEvaluation(
                    candidate=candidate,
                    stock=stock,
                    score_result=score_result,
                )
            )

    position_evaluations: list[PositionEvaluation] = []
    missing_position_symbols: list[str] = []

    for position in position_manager.get_all():
        stock = store.get(position.symbol)
        if stock is None:
            missing_position_symbols.append(position.symbol)
            continue

        pnl_pct = (stock.price - position.entry_price) / position.entry_price * 100
        pnl_amount = (stock.price - position.entry_price) * position.quantity
        triggered_exit_rules = [
            rule.name
            for rule in exit_rules
            if rule.should_exit(position, stock)
        ]
        position_evaluations.append(
            PositionEvaluation(
                position=position,
                stock=stock,
                pnl_pct=pnl_pct,
                pnl_amount=pnl_amount,
                triggered_exit_rules=triggered_exit_rules,
            )
        )

    return ScanResult(
        generated_at=datetime.now(),
        provider_name=type(market).__name__,
        loaded_symbols=len(store),
        candidates=candidate_evaluations,
        missing_candidate_symbols=missing_candidate_symbols,
        positions=position_evaluations,
        missing_position_symbols=missing_position_symbols,
    )


def main() -> None:
    result = run_scan()
    print_header(result.generated_at.strftime("%H:%M:%S"))

    if result.candidates:
        for evaluation in result.candidates:
            print_candidate(
                evaluation.candidate,
                evaluation.score_result,
                evaluation.stock,
            )
    else:
        print()
        print("  (No candidates found)")
        print()
        print(DIVIDER)

    for symbol in result.missing_candidate_symbols:
        print(f"\n  ⚠️  {symbol}: 市場資料中找不到此 Candidate")

    print()
    print("  POSITIONS")

    if result.positions:
        for evaluation in result.positions:
            print_position(evaluation)
    else:
        print()
        print("  (No positions)")
        print()
        print(DIVIDER)

    for symbol in result.missing_position_symbols:
        print(f"\n  ⚠️  {symbol}: 市場資料中找不到此持倉股票")

    print()


if __name__ == "__main__":
    main()
