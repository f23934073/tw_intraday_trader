"""
Candidate 資料模型。

Candidate 只保存 symbol，不保存 StockData 快照。
最新行情統一從 MarketDataStore 取得。

這樣無論 Candidate 是何時產生的，
評分時拿到的永遠是當下最新價格，不會評分舊資料。
"""

from dataclasses import dataclass, field
from enum import StrEnum


class CandidateSource(StrEnum):
    """
    Candidate 的資料來源。

    使用 StrEnum 避免字串拼寫錯誤（"MANUAL" vs "manual" vs "Manual"）。
    未來擴充直接加此處，不影響既有邏輯。
    """

    AUTO = "AUTO"
    SCANNER = "SCANNER"
    MANUAL = "MANUAL"
    POSITION = "POSITION"       # 未來：持倉股票自動進候選池
    NEWS = "NEWS"               # 未來：新聞訊號
    USER_STRATEGY = "USER_STRATEGY"  # 未來：使用者自訂策略


@dataclass
class Candidate:
    """
    代表一支進入候選觀察池的股票。

    Candidate 不等於買入訊號。
    只代表：這檔股票值得進一步監控與評分。

    sources 可以同時包含多個來源，例如：
        {AUTO, MANUAL} → 系統自動選到，且使用者也在觀察
        這比「MANUAL 覆蓋 AUTO」保留更多資訊。
    """

    symbol: str

    sources: set[CandidateSource] = field(default_factory=set)
    """
    這個 Candidate 的所有來源。
    可同時存在多個（AUTO + MANUAL 代表系統選到且使用者也在看）。
    """

    matched_rules: list[str] = field(default_factory=list)
    """符合的 Candidate Rule 名稱列表（AUTO 來源才有值）。"""
