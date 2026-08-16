"""Buy Score 資料模型。"""

from dataclasses import dataclass, field


@dataclass
class ScoreDetail:
    """單一評分 Rule 的明細。"""

    rule: str
    score: int
    max_score: int


@dataclass
class BuyScoreResult:
    """
    單一股票的完整買入評分結果。

    必須保留 details，讓使用者可以看到「為什麼是這個分數」。
    不能只回傳一個數字。
    """

    symbol: str
    total_score: int
    details: list[ScoreDetail] = field(default_factory=list)
