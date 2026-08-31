"""Server-owned StatusEnvelope read model (task170 R1 / task144 B1).

Every dashboard surface that needs to answer "why am I blocked, what can I still
do, where is the evidence" consumes one envelope shape produced here. The module
is pure: it only *projects* existing authorities (backtest capabilities, the
selected Dataset's research-truth readiness, the Local Paper controller, quote
ingress, the kill switch, the No-Overnight controller). It owns no state, never
touches a provider / broker / database, and never upgrades a status the
authority did not assert. Missing, invalid, or failed projections are rendered
as ``UNAVAILABLE`` (never as ``0``, empty, ready, or green).

Copy for reason codes and advisories lives here on purpose: the browser only
renders what the server hands it (task147 §6.1, task150 §1.1), so there is no
second string source in the frontend.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from zoneinfo import ZoneInfo

STATUS_ENVELOPE_SCHEMA: Final = "status_envelope.v1"
STATUS_ENVELOPE_SET_SCHEMA: Final = "status_envelope_set.v1"
STATUS_ENVELOPE_UNAVAILABLE_CODE: Final = "STATUS_ENVELOPE_UNAVAILABLE"

TAIPEI: Final = ZoneInfo("Asia/Taipei")

SUBJECTS: Final[tuple[str, ...]] = (
    "backtest_platform",
    "formal_dataset",
    "strategy_qualification",
    "local_paper_runtime",
    "quote_ingress",
    "kill_switch",
    "no_overnight",
    "market_shadow",
)

AUTHORITY_CLASSES: Final = frozenset({"EXISTING", "PROPOSED_REQUIRED"})

MOBILE_READ_ONLY_POLICY: Final[Mapping[str, object]] = {
    "mode": "READ_ONLY_MONITOR",
    "max_width_css_px": 700,
    "reason_code": "MOBILE_READ_ONLY_MONITOR",
}
MOBILE_READ_ONLY_POLICY_KEYS: Final = frozenset(MOBILE_READ_ONLY_POLICY)

# Display-state grammar (task147 §2.2). LOADING and STALE are client display
# states and therefore never appear in a server envelope.
DISPLAY_STATES: Final[Mapping[str, tuple[str, str, str, str]]] = {
    # state: (glyph, label, a11y token, live region)
    "READY": ("✓", "已就緒", "A-INFO", "polite"),
    "EMPTY": ("○", "尚無資料", "A-INFO", "polite"),
    "RUNNING": ("◌", "執行中", "A-INFO", "polite"),
    "DEGRADED": ("△", "部分功能受限", "A-WARN", "polite"),
    "BLOCKED": ("!", "已阻擋", "A-BLOCK", "assertive"),
    "CRITICAL": ("‼", "立即處理", "A-CRIT", "assertive"),
    "UNAVAILABLE": ("⚠", "狀態不可用", "A-BLOCK", "assertive"),
    "NOT_EVALUATED": ("？", "尚未評估", "A-WARN", "polite"),
    "TERMINAL_FAILED": ("×", "失敗", "A-BLOCK", "assertive"),
    "TERMINAL_SUCCESS": ("✓", "完成", "A-INFO", "polite"),
    "TERMINAL_CANCELLED": ("—", "已取消", "A-INFO", "polite"),
}

# Per-entity subjects (task147 P0-A S11–S24) served by the entity routes.
ENTITY_SUBJECTS: Final[tuple[str, ...]] = ("backtest_run", "cost_snapshot", "backtest_comparison")

# States that must never be produced from an unknown / missing projection.
POSITIVE_STATES: Final = frozenset({"READY", "EMPTY", "RUNNING"})

ENVELOPE_KEYS: Final = frozenset(
    {
        "schema_version",
        "subject",
        "authority",
        "status",
        "status_glyph",
        "status_label",
        "authority_status",
        "revision",
        "digest",
        "as_of",
        "reason_codes",
        "reasons",
        "advisory",
        "allowed_actions",
        "blocked_actions",
        "identity",
        "a11y",
        "live_region",
        "client_policy",
    }
)
REASON_KEYS: Final = frozenset({"code", "known", "title", "impact", "next_step", "a11y"})
ADVISORY_KEYS: Final = frozenset({"code", "text", "a11y"})
BLOCKED_ACTION_KEYS: Final = frozenset({"action", "reason_code"})
SET_KEYS: Final = frozenset({"schema_version", "as_of", "envelopes"})

# ---------------------------------------------------------------------------
# Server-owned copy (task150 Catalog A/B/C, task147 S06-A / S33-A).
# code -> (title, impact, next_step, a11y)
# ---------------------------------------------------------------------------
_L = tuple[str, str, str, str]
_REASON_CATALOG_BASE: Final[Mapping[str, _L]] = {
    # Catalog A — Formal Dataset 17 exact reason codes
    "CURRENT_SNAPSHOT_UNIVERSE": (
        "股票池只有目前快照",
        "股票池不是 date-effective，Formal 已停止。",
        "查看 PIT 股票池來源決策；不得用今天名單回填過去。",
        "A-BLOCK",
    ),
    "MANIFEST_NOT_RESEARCH_ELIGIBLE": (
        "資料集只供探索",
        "Manifest 標示探索用途，Formal 已停止。",
        "查看新 immutable Dataset 計畫；不提供 toggle 或 edit。",
        "A-BLOCK",
    ),
    "MANIFEST_ISSUES_PRESENT": (
        "資料集仍有已知問題",
        "已知 issues 尚未清除，Formal 已停止。",
        "展開 issues 並找 evidence owner；issues 缺失時顯示 unknown，不顯示 0。",
        "A-BLOCK",
    ),
    "MISSING_UNIVERSE_CONTRACT": (
        "缺少歷史股票池契約",
        "歷史股票池證據缺失。",
        "查看股票池來源與 coverage 決策；不從 symbols 清單合成 contract。",
        "A-BLOCK",
    ),
    "MISSING_LISTING_CONTRACT": (
        "缺少上市下市時間軸",
        "上市、下市或轉板時間軸缺失。",
        "查看 listing source 決策；不以 current metadata 補值。",
        "A-BLOCK",
    ),
    "MISSING_SESSION_CONTRACT": (
        "缺少每檔交易時段契約",
        "交易時段證據缺失。",
        "查看 session evidence；不由 Kbar 時間猜 halt/session authority。",
        "A-BLOCK",
    ),
    "MISSING_CALENDAR_CONTRACT": (
        "缺少交易日曆契約",
        "交易日曆證據缺失。",
        "查看 calendar evidence；不以資料有無推斷交易日。",
        "A-BLOCK",
    ),
    "MISSING_CLOSING_AUCTION_EVENT_CONTRACT": (
        "缺少 13:30 收盤撮合證據",
        "收盤競價證據缺失，Formal 已停止。",
        "查看 closing-auction source；13:30 Kbar 不可當 auction-only。",
        "A-BLOCK",
    ),
    "MISSING_CORPORATE_ACTION_CONTRACT": (
        "缺少除權息等公司行動",
        "公司行動時間點證據缺失。",
        "查看除權息／分割來源；不由價格跳空猜 corporate action。",
        "A-BLOCK",
    ),
    "MISSING_REFERENCE_PRICE_CONTRACT": (
        "缺少每日參考價",
        "每日參考價證據缺失。",
        "查看 reference-price source；不以昨日 close 代替 authority。",
        "A-BLOCK",
    ),
    "MISSING_PRICE_LIMIT_CONTRACT": (
        "缺少漲跌幅與例外規則",
        "漲跌幅制度證據缺失。",
        "查看 price-limit source；不固定套 ±10%。",
        "A-BLOCK",
    ),
    "MISSING_SPECIAL_REGIME_CONTRACT": (
        "特殊處置分類不完整",
        "特殊市場制度分類缺失。",
        "查看注意／處置／全額交割等來源；unknown regime 不得歸 normal。",
        "A-BLOCK",
    ),
    "MISSING_COMPLETENESS_CONTRACT": (
        "資料完整性尚未封存",
        "完整性稽核缺失，Formal 已停止。",
        "查看 completeness audit；bar count 大不等於完整。",
        "A-BLOCK",
    ),
    "MISSING_EXECUTION_CALIBRATION_CONTRACT": (
        "缺少可成交比例校準",
        "成交容量校準缺失。",
        "查看 calibration evidence；不使用 plan-only 5% 當證據。",
        "A-BLOCK",
    ),
    "MISSING_SLIPPAGE_CALIBRATION_CONTRACT": (
        "缺少滑價校準",
        "滑價校準缺失，Formal 已停止。",
        "查看 calibration evidence；不補固定 bps。",
        "A-BLOCK",
    ),
    "INVALID_VOLUME_CONTRACT": (
        "成交量單位契約不合法",
        "volume contract 驗證失敗。",
        "查看 exact invalid contract/digest；COMMON_LOTS 字串本身不等於 verified snapshot。",
        "A-BLOCK",
    ),
    "INVALID_AMOUNT_CONTRACT": (
        "成交金額語意不合法",
        "amount contract 驗證失敗。",
        "查看 amount source 決策；不把 proxy 標成 TWD turnover。",
        "A-BLOCK",
    ),
    # Catalog B — cost snapshot readiness reasons
    "MISSING_SLIPPAGE_CALIBRATION": (
        "成本證據缺件",
        "Formal 成本無法驗證，計算已停止。",
        "查看 sealed cost snapshot；不補固定滑價。",
        "A-BLOCK",
    ),
    "UNKNOWN_SLIPPAGE_POLICY": (
        "滑價設定無法解讀",
        "成本政策未知，Formal 已停止。",
        "修正新 policy snapshot 並重新封存；不由 client 清洗字串。",
        "A-BLOCK",
    ),
    "UNKNOWN_SLIPPAGE_CALIBRATION": (
        "滑價校準身分無法驗證",
        "滑價校準 digest 無效。",
        "查看 calibration artifact；不略過 digest。",
        "A-BLOCK",
    ),
    # Readiness statuses (task147 S05–S08)
    "PLATFORM_NOT_READY": (
        "回測平台未啟用",
        "不能建立任何 Run。",
        "查看回測服務設定。",
        "A-BLOCK",
    ),
    "DATA_NOT_READY": (
        "Formal Dataset 未就緒",
        "不能建立 Formal Run；探索 Run 永久標示探索資料。",
        "查看原因與資料決策；無 bypass。",
        "A-BLOCK",
    ),
    "NO_QUALIFYING_STRATEGY": (
        "尚無符合 promotion review 的策略",
        "不等於策略無價值，也不等於 lifecycle retired。",
        "建立／查看 qualification evidence；不提供手動 override。",
        "A-WARN",
    ),
    # Local Paper controller states (task147 S25–S31)
    "KILLED": (
        "Kill switch 已停止自動策略",
        "不會產生新的本機模擬意圖；持倉不等於已平。",
        "查看 kill switch 原因與 revision；解除後仍需人工重新啟動。",
        "A-CRIT",
    ),
    "ERROR": (
        "自動策略發生錯誤",
        "自動策略已停止；既有持倉與委託另列。",
        "查看 last_error；重新啟動需人工明確操作。",
        "A-BLOCK",
    ),
    "RECOVERY_REQUIRED": (
        "Journal 需要復原",
        "所有變更操作暫停；查詢與 recovery 仍可用。",
        "走 approved recovery；ACK/reset/bypass 不是修復。",
        "A-CRIT",
    ),
    # Quote ingress (task147 S28–S29)
    "STREAM_DEGRADED": (
        "行情待復原",
        "依 server gate 暫停新動作；HTTP fallback 不代表已恢復。",
        "查看行情詳情（stream_error、last quote、queue）。",
        "A-WARN",
    ),
    "STREAM_BLOCKED": (
        "行情 ingress 已阻擋",
        "所有新增 order/start 停用；查詢與對帳仍可讀。",
        "開啟行情事件詳情；新的 websocket 連線不會解除。",
        "A-CRIT",
    ),
    # Kill switch (task147 S30–S31)
    "KILL_SWITCH_ENGAGED": (
        "Kill switch 已啟用",
        "start/new intent 停用；不等於 positions flat。",
        "依權限查看／提出解除（需 expected revision）；成功後仍需人工啟動。",
        "A-CRIT",
    ),
    "KILL_SWITCH_RECOVERY_REQUIRED": (
        "Kill switch Journal 需復原",
        "start/intent/reset 全部停用；不可由操作員解除。",
        "匯出復原資訊／聯絡 owner。",
        "A-CRIT",
    ),
    # No-Overnight (task147 S32–S35, S33-A)
    "NO_OVERNIGHT_STATUS_UNAVAILABLE": (
        "收盤風控狀態不可用",
        "ACK/apply 停用；缺欄不可當 DISABLED/NORMAL/flat。",
        "重新讀取；保留最後有效資料。",
        "A-BLOCK",
    ),
    "NO_NEW_ENTRY": (
        "停止新進場",
        "不再建立新部位；查詢仍可用。",
        "查看 server allowed actions；不用 client 時鐘提前／延後 state。",
        "A-WARN",
    ),
    "CANCEL_ENTRY": (
        "取消尚未完成的進場委託",
        "request/ACK 不等於 CANCELLED。",
        "查看各 order 結果。",
        "A-WARN",
    ),
    "FLATTENING": (
        "正在降低日內曝險",
        "submitted 不等於 filled；不宣告 flat。",
        "查看 fills/residual/exposures。",
        "A-WARN",
    ),
    "AGGRESSIVE_EXIT": (
        "進入積極出場階段",
        "mutation 只依 server allowed action。",
        "查看 server actions 與流動性 blockers。",
        "A-WARN",
    ),
    "FINAL_RECONCILIATION": (
        "正在做最終對帳",
        "sequence coverage 全滿才可前進。",
        "查看 Journal/projection sequences。",
        "A-WARN",
    ),
    "OVERNIGHT_BREACH": (
        "收盤後未證明空倉",
        "隔夜違約已 latch；ACK 不解除 latch、不清 banner。",
        "依 exact revision 輸入確認語句；等待下一個已審核交易日。",
        "A-CRIT",
    ),
    "LIMIT_DOWN_NO_BID": (
        "跌停且沒有買盤",
        "出場受阻；fill=0。",
        "持續查詢／對帳；不用跌停價直接填滿。",
        "A-CRIT",
    ),
    "HALT": (
        "股票暫停交易",
        "停牌使出場暫停；不 submit。",
        "查看 halt/session evidence。",
        "A-BLOCK",
    ),
    "STALE_BOOK": (
        "委託簿資料過期",
        "出場動作受限；fresh Tick 不清此 reason。",
        "等新 book／reconcile。",
        "A-BLOCK",
    ),
    "NO_EXECUTABLE_LIQUIDITY": (
        "沒有可執行流動性",
        "zero volume → zero fill；對帳持續。",
        "查看 depth/limit/residual。",
        "A-BLOCK",
    ),
    "MISSING_AUCTION_EVENT": (
        "缺少 13:30 收盤競價事件",
        "auction-only action 停用。",
        "查看 closing-auction source。",
        "A-BLOCK",
    ),
    "ZERO_AUCTION_MATCHABLE_VOLUME": (
        "收盤競價可撮合量為零",
        "fill=0；不假設能在收盤價成交。",
        "查看 auction book／residual。",
        "A-BLOCK",
    ),
    "UNSUPPORTED_SESSION_REGIME": (
        "目前盤別制度不支援",
        "變更暫停；query/reconcile 仍可用。",
        "查看 regime evidence／聯絡 rule owner。",
        "A-BLOCK",
    ),
    "SUBMIT_UNKNOWN": (
        "出場委託結果未知",
        "後續委託暫停；零 duplicate command。",
        "人工 reconcile／recovery；禁止 successor submit。",
        "A-CRIT",
    ),
    "RESIDUAL_PARTIAL": (
        "部分成交殘餘量未解決",
        "requested = filled + residual；未解前不 confirmed flat。",
        "查看 residual 與後續 evidence。",
        "A-CRIT",
    ),
    "IDENTITY_MISMATCH": (
        "Journal 身分衝突",
        "所有變更關閉；永久不顯示 ACK。",
        "保留 evidence／聯絡管理員。",
        "A-CRIT",
    ),
    # Backtest Run lifecycle / comparison / cost (task147 S11–S24, task150 B05–B13)
    "RUN_FAILED": (
        "回測執行失敗",
        "舊 evidence 已保留；缺 result 不等於 0 績效。",
        "複製診斷／以新 Run 重試；不由 message 字串造 error code。",
        "A-BLOCK",
    ),
    "INVALID_CASH_ADMISSION_CONTROL": (
        "現金 admission control 無效",
        "Run 結果不可作正式 outcome；無 KPI。",
        "查看現金／成本設定與 control evidence；retry 依 server contract。",
        "A-BLOCK",
    ),
    "NOT_COMPARABLE": (
        "兩次 Run 不能直接比較",
        "outcome delta 已鎖住；不判定改善。",
        "查看完整 config_diff／重新選擇可比較 Runs。",
        "A-BLOCK",
    ),
    "NO_CLEAR_EVIDENCE": (
        "尚無明確改善證據",
        "兩 Run 可比，但差異不足以支持改善；不翻成失敗或「差不多」。",
        "查看 CI、trade diff、樣本。",
        "A-WARN",
    ),
    "COST_POLICY_SNAPSHOT_MISSING": (
        "未封存成本政策",
        "Formal 成本無法驗證；不補固定 bps。",
        "以新 Run 封存 cost policy snapshot。",
        "A-BLOCK",
    ),
    "REASON_CODES_REQUIRE_DATASET_SCOPE": (
        "尚未選定策略組合",
        "全域資料狀態只供資訊；未綁定 exact Strategy Set 時不得建立 Formal Backtest。",
        "先選擇策略組合版本，再讀取該 exact id 的 Dataset reason codes。",
        "A-BLOCK",
    ),
    # Market Shadow (PROPOSED_REQUIRED; task147 §5.7)
    "SHADOW_READ_MODEL_NOT_WIRED": (
        "Market Shadow 尚無產品 read model",
        "沒有 Dashboard route/API/canonical index；不得由瀏覽器掃檔或猜狀態。",
        "等待 canonical Shadow read model（B3）；本畫面只顯示 NOT_EVALUATED。",
        "A-WARN",
    ),
}

_UNAVAILABLE_LABEL: Final[_L] = (
    "狀態投影不可用",
    "不可解讀為 0、空、就緒或正常；保留最後有效資料，所有依 current state 的操作停用。",
    "重新讀取狀態（GET only）。",
    "A-BLOCK",
)
REASON_CATALOG: Final[Mapping[str, _L]] = {
    **{
        f"{subject.upper()}_STATUS_UNAVAILABLE": _UNAVAILABLE_LABEL
        for subject in SUBJECTS + ENTITY_SUBJECTS
    },
    **_REASON_CATALOG_BASE,
}

# Advisory copy (server-owned; task145 H3 / task147 S08, S25).
ADVISORY_CATALOG: Final[Mapping[str, tuple[str, str]]] = {
    "REASON_CODES_REQUIRE_DATASET_SCOPE": (
        "全域資料就緒只投影 status；選擇策略組合後才會投影所選 Dataset 的 exact reason codes。",
        "A-WARN",
    ),
    "QUALIFICATION_DISPLAY_ONLY": (
        "資格證據只供人工 promotion review，不會自動啟用、不改變 lifecycle。",
        "A-INFO",
    ),
    "EXECUTION_AUTHORITY_LOCAL_ONLY": (
        "只會產生本機紙上模擬意圖；不具 Shioaji 或券商下單權限。",
        "A-INFO",
    ),
    "LOCAL_PAPER_TAX_SLIPPAGE_NOT_SIMULATED": (
        "手續費以外的稅／滑價尚未模擬；Local Paper 的 net 目前不包含這兩項成本。",
        "A-WARN",
    ),
    "MOBILE_READ_ONLY_MONITOR": (
        "手機版是唯讀監看模式；高風險變更操作已停用，請改用桌面版。",
        "A-BLOCK",
    ),
    "STOPPED_IS_NOT_FLAT": (
        "未啟動不等於已平倉或無委託；既有持倉與委託另列。",
        "A-WARN",
    ),
    "RUN_PROGRESS_IS_SERVER_OWNED": (
        "進度與狀態由 server 投影；progress 0 不等於卡住，elapsed time 不代表失敗或過期。",
        "A-INFO",
    ),
    "RUN_ERROR_MESSAGE_NOT_PROVIDED": (
        "原因未提供；不歸因、不合成 error code。",
        "A-WARN",
    ),
    "COMPLETED_IS_NOT_QUALIFIED": (
        "回測完成不等於 qualified、approved 或 profitable。",
        "A-INFO",
    ),
    "LIKELY_IMPROVED_NOT_CAUSAL": (
        "較可能改善，不是因果保證；qualification 是另一個明確步驟，不觸發 lifecycle mutation。",
        "A-INFO",
    ),
}

# Conservative server-owned action allowlist (task147 Top10 CTA column).
_ACTION_RELOAD: Final = "reload_status"


def _label(code: str) -> dict[str, object]:
    known = code in REASON_CATALOG
    title, impact, next_step, a11y = REASON_CATALOG.get(code, (code, "", "", "A-BLOCK"))
    return {
        "code": code,
        "known": known,
        "title": title,
        "impact": impact,
        "next_step": next_step,
        "a11y": a11y,
    }


def _advisory(code: str) -> dict[str, object]:
    text, a11y = ADVISORY_CATALOG[code]
    return {"code": code, "text": text, "a11y": a11y}


_JS_SAFE_INTEGER: Final = 9_007_199_254_740_991
_SHA256_HEX_LENGTH: Final = 64


def _validate_unicode_scalar(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("signed strings must contain valid Unicode scalar values") from error


def _validate_signed_value(value: object) -> None:
    """Validate the exact cross-language StatusEnvelope signed-value domain."""

    if value is None or type(value) is bool:
        return
    if type(value) is str:
        _validate_unicode_scalar(value)
        return
    if type(value) is int:
        if not -_JS_SAFE_INTEGER <= value <= _JS_SAFE_INTEGER:
            raise ValueError("signed integer exceeds the JavaScript safe range")
        return
    if isinstance(value, list):
        for item in value:
            _validate_signed_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                type(key) is not str
                or not key
                or not key.isascii()
                or any(not (character.isalnum() or character == "_") for character in key)
            ):
                raise ValueError("signed object keys must be schema-defined ASCII identifiers")
            _validate_signed_value(item)
        return
    raise ValueError(
        "signed values only allow objects, arrays, Unicode strings, null, booleans, and safe integers"
    )


def canonical_json(value: object) -> str:
    _validate_signed_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_decimal_string(value: object) -> str:
    """Normalize an authority decimal before it enters the signed envelope."""

    if type(value) not in (int, float):
        raise TypeError("decimal measure must be an int or float")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("decimal measure must be finite")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("decimal measure is invalid") from error
    if not parsed.is_finite():
        raise ValueError("decimal measure must be finite")
    if parsed.is_zero():
        return "0"
    normalized = format(parsed, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _is_sha256_hex(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_nonempty_str(mapping: object, key: str) -> str:
    value = _require(mapping, key, str)
    if not value:
        raise ValueError(f"{key} must be non-empty")
    return value


def _require_sha256(mapping: object, key: str) -> str:
    value = _require_nonempty_str(mapping, key)
    if not _is_sha256_hex(value):
        raise ValueError(f"{key} must be lowercase SHA-256")
    return value


def envelope_digest(envelope: Mapping[str, Any]) -> str:
    """Digest of everything except ``digest`` and ``as_of`` so unchanged state is stable."""

    body = {key: value for key, value in envelope.items() if key not in {"digest", "as_of"}}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _iso(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=TAIPEI)
    return now.astimezone(TAIPEI).isoformat(timespec="seconds")


def _envelope(
    *,
    subject: str,
    status: str,
    now: datetime,
    authority: str = "EXISTING",
    authority_status: str | None,
    revision: int = 0,
    reason_codes: Sequence[str] = (),
    advisory: Sequence[str] = (),
    allowed_actions: Sequence[str] = (),
    blocked_actions: Sequence[tuple[str, str]] = (),
    identity: Mapping[str, object] | None = None,
    client_policy: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    if status not in DISPLAY_STATES:
        raise ValueError(f"unknown display state {status!r}")
    reasons = [_label(code) for code in reason_codes]
    # The strongest attached reason escalates the display state and live region;
    # nothing ever relaxes them (task147 §2.1 priority order).
    reason_tokens = {reason["a11y"] for reason in reasons}
    if "A-CRIT" in reason_tokens and status not in {"CRITICAL", "UNAVAILABLE"}:
        status = "CRITICAL"
    elif "A-BLOCK" in reason_tokens and status in POSITIVE_STATES:
        status = "BLOCKED"
    glyph, label, a11y, live_region = DISPLAY_STATES[status]
    if "A-CRIT" in reason_tokens:
        a11y, live_region = "A-CRIT", "assertive"
    envelope: dict[str, Any] = {
        "schema_version": STATUS_ENVELOPE_SCHEMA,
        "subject": subject,
        "authority": authority,
        "status": status,
        "status_glyph": glyph,
        "status_label": label,
        "authority_status": authority_status,
        "revision": revision,
        "as_of": _iso(now),
        "reason_codes": list(reason_codes),
        "reasons": reasons,
        "advisory": [_advisory(code) for code in advisory],
        "allowed_actions": list(allowed_actions),
        "blocked_actions": [
            {"action": action, "reason_code": reason} for action, reason in blocked_actions
        ],
        "identity": dict(identity or {}),
        "a11y": a11y,
        "live_region": live_region,
        "client_policy": dict(client_policy or {}),
    }
    envelope["digest"] = envelope_digest(envelope)
    return envelope


def unavailable_reason_code(subject: str) -> str:
    return f"{subject.upper()}_STATUS_UNAVAILABLE"


def unavailable_envelope(
    subject: str,
    *,
    now: datetime,
    reason_code: str | None = None,
    error_type: str | None = None,
    authority: str = "EXISTING",
) -> dict[str, Any]:
    """Fail-closed envelope: the authority exists but its projection could not be trusted."""

    return _envelope(
        subject=subject,
        status="UNAVAILABLE",
        now=now,
        authority=authority,
        authority_status=None,
        reason_codes=[reason_code or unavailable_reason_code(subject)],
        allowed_actions=[_ACTION_RELOAD],
        identity={"error_type": error_type},
    )


# ---------------------------------------------------------------------------
# Subject builders. Each receives the *existing* authoritative projection and
# raises on anything it cannot read exactly; the caller converts the raise into
# ``unavailable_envelope``.
# ---------------------------------------------------------------------------
def _require(mapping: object, key: str, expected: type | tuple[type, ...]) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise KeyError(key)
    value = mapping[key]
    if expected is int and isinstance(value, bool):
        raise TypeError(key)
    if not isinstance(value, expected):
        raise TypeError(key)
    return value


def _require_str_list(mapping: object, key: str) -> list[str]:
    values = _require(mapping, key, list)
    if any(type(item) is not str for item in values):
        raise TypeError(key)
    return list(values)


def _optional_str(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError(key)
    return value


def backtest_platform_envelope(readiness: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    platform = _require(readiness, "platform", Mapping)
    ready = _require(platform, "ready", bool)
    status = _require(platform, "status", str)
    if ready and status != "PLATFORM_READY":
        raise ValueError("platform readiness is inconsistent")
    if not ready and status != "PLATFORM_NOT_READY":
        raise ValueError("platform readiness is inconsistent")
    return _envelope(
        subject="backtest_platform",
        status="READY" if ready else "BLOCKED",
        now=now,
        authority_status=status,
        reason_codes=[] if ready else [status],
        allowed_actions=["open_backtest", "create_formal_backtest"] if ready else [_ACTION_RELOAD],
    )


def formal_dataset_envelope(
    readiness: Mapping[str, Any],
    *,
    now: datetime,
    selected_dataset: Mapping[str, Any] | None = None,
    strategy_set_version_id: str | None = None,
) -> dict[str, Any]:
    """Project Formal Dataset readiness (task147 S05/S06, S06-A).

    ``selected_dataset`` is the ``binding`` payload of
    ``GET /api/backtests/atomic-dataset``; when present its
    ``formal_research_readiness`` (exact reason codes + truth digest) is the
    authority. Otherwise the global ``readiness.data`` status is projected
    without codes and the envelope says so via advisory instead of inventing
    an empty checklist.
    """

    identity: dict[str, object] = {}
    advisory: list[str] = []
    if selected_dataset is not None:
        if not strategy_set_version_id:
            raise ValueError("selected dataset requires an exact strategy set version id")
        formal = _require(selected_dataset, "formal_research_readiness", Mapping)
        ready = _require(formal, "ready", bool)
        status = _require(formal, "status", str)
        codes = _require_str_list(formal, "reason_codes")
        identity["strategy_set_version_id"] = strategy_set_version_id
        identity["dataset_id"] = _optional_str(selected_dataset, "dataset_id")
        identity["manifest_digest"] = _optional_str(selected_dataset, "manifest_digest")
        identity["research_truth_snapshot_digest"] = _optional_str(
            formal, "research_truth_snapshot_digest"
        )
    else:
        data = _require(readiness, "data", Mapping)
        ready = _require(data, "ready", bool)
        status = _require(data, "status", str)
        codes = []
        advisory.append("REASON_CODES_REQUIRE_DATASET_SCOPE")
    if ready and (status != "DATA_READY" or codes):
        raise ValueError("data readiness is inconsistent")
    if not ready and status != "DATA_NOT_READY":
        raise ValueError("data readiness is inconsistent")
    if selected_dataset is not None and ready:
        if (
            not identity["dataset_id"]
            or not _is_sha256_hex(identity["manifest_digest"])
            or not _is_sha256_hex(identity["research_truth_snapshot_digest"])
        ):
            raise ValueError("ready selected dataset lacks exact provenance")
    if selected_dataset is not None and not ready and not codes:
        raise ValueError("blocked selected dataset requires exact reason codes")
    scoped = selected_dataset is not None
    reason_codes = list(codes) if scoped else ["REASON_CODES_REQUIRE_DATASET_SCOPE"]
    return _envelope(
        subject="formal_dataset",
        status="READY" if scoped and ready else "BLOCKED",
        now=now,
        authority_status=status,
        reason_codes=reason_codes,
        advisory=advisory,
        allowed_actions=["create_formal_backtest"] if scoped and ready else ["view_reasons"],
        blocked_actions=([] if scoped and ready else [("create_formal_backtest", reason_codes[0])]),
        identity=identity,
    )


def strategy_qualification_envelope(
    readiness: Mapping[str, Any], *, now: datetime
) -> dict[str, Any]:
    strategy = _require(readiness, "strategy", Mapping)
    ready = _require(strategy, "ready", bool)
    status = _require(strategy, "status", str)
    qualification_ids = _require_str_list(strategy, "qualification_ids")
    effect = _require(strategy, "effect", str)
    if effect != "DISPLAY_ONLY_NO_LIFECYCLE_MUTATION":
        raise ValueError("qualification effect is not display-only")
    if ready and (status != "STRATEGY_QUALIFIED" or not qualification_ids):
        raise ValueError("strategy readiness is inconsistent")
    if ready and (
        any(not item for item in qualification_ids)
        or len(set(qualification_ids)) != len(qualification_ids)
    ):
        raise ValueError("qualified strategy ids must be non-empty and unique")
    if not ready and (status != "NO_QUALIFYING_STRATEGY" or qualification_ids):
        raise ValueError("strategy readiness is inconsistent")
    return _envelope(
        subject="strategy_qualification",
        status="READY" if ready else "EMPTY",
        now=now,
        authority_status=status,
        reason_codes=[] if ready else [status],
        advisory=["QUALIFICATION_DISPLAY_ONLY"],
        allowed_actions=(["open_review_packet"] if ready else ["view_qualification_evidence"]),
        blocked_actions=[("start_local_paper", effect)],
        identity={
            "qualification_ids": ",".join(qualification_ids),
            "qualification_count": len(qualification_ids),
            "effect": effect,
        },
    )


_CONTROLLER_STATES: Final = frozenset(
    {"STOPPED", "RUNNING", "KILLED", "ERROR", "RECOVERY_REQUIRED"}
)


def local_paper_runtime_envelope(status: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Project the automated Local Paper controller (task147 S25/S26/S30/S31)."""

    if _require(status, "execution_authority", bool) is not False:
        raise ValueError("local paper execution authority must be false")
    if _require(status, "mode", str) != "LOCAL_PAPER_SIMULATION":
        raise ValueError("local paper mode is not local simulation")
    state = _require(status, "state", str)
    if state not in _CONTROLLER_STATES:
        raise ValueError(f"unknown controller state {state!r}")
    kill = _require(status, "kill_switch", Mapping)
    kill_revision = _require(kill, "revision", int)
    pipeline = status.get("pipeline")
    pipeline_snapshot_digest = (
        _optional_str(pipeline, "snapshot_digest") if isinstance(pipeline, Mapping) else None
    )
    run_id = _optional_str(status, "run_id")
    if state == "RUNNING" and (
        not run_id
        or not isinstance(pipeline, Mapping)
        or not _is_sha256_hex(pipeline_snapshot_digest)
    ):
        raise ValueError("running local paper lacks run/pipeline provenance")
    identity: dict[str, object] = {
        "run_id": run_id,
        "pipeline_snapshot_digest": pipeline_snapshot_digest,
        "decision": _optional_str(status, "decision"),
        "restart_behavior": _optional_str(status, "restart_behavior"),
        "last_checked_at": _optional_str(status, "last_checked_at"),
        "last_action_at": _optional_str(status, "last_action_at"),
        "last_error": _optional_str(status, "last_error"),
    }
    advisory = [
        "EXECUTION_AUTHORITY_LOCAL_ONLY",
        "LOCAL_PAPER_TAX_SLIPPAGE_NOT_SIMULATED",
        "MOBILE_READ_ONLY_MONITOR",
    ]
    display: str
    codes: list[str]
    allowed: list[str]
    if state == "RUNNING":
        display, codes, allowed = "RUNNING", [], ["stop_automated_strategy", "view_run"]
    elif state == "STOPPED":
        display, codes, allowed = "EMPTY", [], ["start_automated_strategy", "check_preflight"]
        advisory.append("STOPPED_IS_NOT_FLAT")
    elif state == "ERROR":
        display, codes, allowed = "TERMINAL_FAILED", ["ERROR"], ["view_error"]
    elif state == "KILLED":
        display, codes, allowed = "CRITICAL", ["KILLED"], ["view_kill_switch"]
    else:  # RECOVERY_REQUIRED
        display, codes, allowed = "CRITICAL", ["RECOVERY_REQUIRED"], ["export_recovery_info"]
    blocked = [] if state == "STOPPED" else [("start_automated_strategy", state)]
    return _envelope(
        subject="local_paper_runtime",
        status=display,
        now=now,
        authority_status=state,
        revision=kill_revision,
        reason_codes=codes,
        advisory=advisory,
        allowed_actions=allowed,
        blocked_actions=blocked,
        identity=identity,
        client_policy=MOBILE_READ_ONLY_POLICY,
    )


_STREAM_HEALTH: Final = frozenset({"HEALTHY", "DEGRADED", "BLOCKED"})


def quote_ingress_envelope(session: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    health = _require(session, "stream_health", str)
    if health not in _STREAM_HEALTH:
        raise ValueError(f"unknown stream health {health!r}")
    streaming = _require(session, "streaming", bool)
    identity = {
        "quote_mode": _optional_str(session, "quote_mode"),
        "streaming": streaming,
        "last_quote_received_at": _optional_str(session, "last_quote_received_at"),
        "stream_error": _optional_str(session, "stream_error"),
        "quote_queue_depth": _require(session, "quote_queue_depth", int),
        "quote_queue_capacity": _require(session, "quote_queue_capacity", int),
    }
    if health == "HEALTHY":
        display, codes = "READY", []
        allowed, blocked = ["submit_order", "cancel_order", "start_automated_strategy"], []
    elif health == "DEGRADED":
        display, codes = "DEGRADED", ["STREAM_DEGRADED"]
        allowed, blocked = (
            ["cancel_order", "view_stream_details"],
            [("submit_order", "STREAM_DEGRADED")],
        )
    else:
        display, codes = "CRITICAL", ["STREAM_BLOCKED"]
        allowed = ["cancel_order", "open_stream_events"]
        blocked = [
            ("submit_order", "STREAM_BLOCKED"),
            ("start_automated_strategy", "STREAM_BLOCKED"),
        ]
    return _envelope(
        subject="quote_ingress",
        status=display,
        now=now,
        authority_status=health,
        reason_codes=codes,
        allowed_actions=allowed,
        blocked_actions=blocked,
        identity=identity,
    )


_KILL_STATES: Final = frozenset({"DISENGAGED", "ENGAGED", "RECOVERY_REQUIRED"})


def kill_switch_envelope(status: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    control_state = _require(status, "control_state", str)
    if control_state not in _KILL_STATES:
        raise ValueError(f"unknown kill switch state {control_state!r}")
    engaged = _require(status, "engaged", bool)
    revision = _require(status, "revision", int)
    if revision < 0:
        raise ValueError("kill switch revision is negative")
    if engaged != (control_state != "DISENGAGED"):
        raise ValueError("kill switch projection is inconsistent")
    if _require(status, "execution_boundary", str) != "LOCAL_ONLY":
        raise ValueError("kill switch execution boundary is not local")
    identity = {
        "reason": _optional_str(status, "reason"),
        "engaged_at": _optional_str(status, "engaged_at"),
        "last_transition_at": _optional_str(status, "last_transition_at"),
        "durability": _require(status, "durability", str),
        "restart_safe": _require(status, "restart_safe", bool),
        "recovered": _require(status, "recovered", bool),
        "recovery_error": _optional_str(status, "recovery_error"),
    }
    if control_state == "DISENGAGED":
        display, codes = "READY", []
        allowed, blocked = ["start_automated_strategy", "engage_kill_switch"], []
    elif control_state == "ENGAGED":
        display, codes = "CRITICAL", ["KILL_SWITCH_ENGAGED"]
        allowed = ["view_kill_switch", "request_kill_switch_reset"]
        blocked = [("start_automated_strategy", "KILL_SWITCH_ENGAGED")]
    else:
        display, codes = "CRITICAL", ["KILL_SWITCH_RECOVERY_REQUIRED"]
        allowed = ["export_recovery_info"]
        blocked = [
            ("start_automated_strategy", "KILL_SWITCH_RECOVERY_REQUIRED"),
            ("request_kill_switch_reset", "KILL_SWITCH_RECOVERY_REQUIRED"),
        ]
    return _envelope(
        subject="kill_switch",
        status=display,
        now=now,
        authority_status=control_state,
        revision=revision,
        reason_codes=codes,
        allowed_actions=allowed,
        blocked_actions=blocked,
        identity=identity,
    )


_NO_OVERNIGHT_STATE_DISPLAY: Final[Mapping[str, str]] = {
    "NORMAL": "READY",
    "NO_NEW_ENTRY": "DEGRADED",
    "CANCEL_ENTRY": "DEGRADED",
    "FLATTENING": "DEGRADED",
    "AGGRESSIVE_EXIT": "DEGRADED",
    "FINAL_RECONCILIATION": "DEGRADED",
    "CONFIRMED_FLAT": "READY",
    "OVERNIGHT_BREACH": "CRITICAL",
}


def no_overnight_envelope(payload: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Project an already *validated* ``no_overnight_dashboard.v1`` payload (S32–S35)."""

    if _require(payload, "schema_version", str) != "no_overnight_dashboard.v1":
        raise ValueError("no-overnight envelope schema mismatch")
    status = _require(payload, "status", Mapping)
    state = _require(status, "state", str)
    if state not in _NO_OVERNIGHT_STATE_DISPLAY:
        raise ValueError(f"unknown no-overnight state {state!r}")
    mode = _require(status, "mode", str)
    revision = _require(status, "revision", int)
    breach_latched = _require(status, "breach_latched", bool)
    stable_reasons = _require_str_list(status, "stable_reasons")
    ack = _require(payload, "acknowledgement", Mapping)
    blockers = _require(payload, "apply_blockers", Mapping)
    identity_mismatch = _require(blockers, "identity_mismatch", bool)
    display = _NO_OVERNIGHT_STATE_DISPLAY[state]
    codes: list[str] = []
    if state not in {"NORMAL", "CONFIRMED_FLAT"}:
        codes.append(state)
    codes.extend(stable_reasons)
    if mode == "DISABLED":
        display = "EMPTY" if display == "READY" else display
    if identity_mismatch and "IDENTITY_MISMATCH" not in codes:
        codes.append("IDENTITY_MISMATCH")
    if any(code in {"IDENTITY_MISMATCH", "RECOVERY_REQUIRED", "SUBMIT_UNKNOWN"} for code in codes):
        display = "CRITICAL"
    if state == "CONFIRMED_FLAT" and (
        not _optional_str(status, "flat_proof_mode")
        or not _is_sha256_hex(_optional_str(status, "evidence_snapshot_digest"))
    ):
        raise ValueError("confirmed-flat state lacks strict evidence provenance")
    allowed = ["view_no_overnight_evidence"]
    if state == "NORMAL":
        allowed.extend(["start_automated_strategy", "submit_entry_order"])
    blocked: list[tuple[str, str]] = []
    ack_available = _require(ack, "available", bool)
    if breach_latched and ack_available and "IDENTITY_MISMATCH" not in codes:
        allowed.append("acknowledge_breach_by_revision")
    else:
        blocked.append(
            (
                "acknowledge_breach_by_revision",
                "IDENTITY_MISMATCH" if "IDENTITY_MISMATCH" in codes else state,
            )
        )
    if state != "NORMAL":
        blocked.append(("submit_entry_order", state))
    return _envelope(
        subject="no_overnight",
        status=display,
        now=now,
        authority_status=state,
        revision=revision,
        reason_codes=codes,
        allowed_actions=allowed,
        blocked_actions=blocked,
        identity={
            "mode": mode,
            "breach_latched": breach_latched,
            "flat_proof_mode": _optional_str(status, "flat_proof_mode"),
            "evidence_snapshot_digest": _optional_str(status, "evidence_snapshot_digest"),
            "acknowledged": _require(ack, "acknowledged", bool),
            "acknowledged_at": _optional_str(ack, "acknowledged_at"),
        },
    )


def market_shadow_envelope(*, now: datetime, error_type: str | None = None) -> dict[str, Any]:
    """Honest absence: there is no Shadow read model yet (task147 §5.7, task149 V01)."""

    return _envelope(
        subject="market_shadow",
        status="NOT_EVALUATED",
        now=now,
        authority="PROPOSED_REQUIRED",
        authority_status=None,
        reason_codes=["SHADOW_READ_MODEL_NOT_WIRED"],
        blocked_actions=[
            ("start_shadow_session", "SHADOW_READ_MODEL_NOT_WIRED"),
            ("enable_execution", "SHADOW_READ_MODEL_NOT_WIRED"),
        ],
        identity={"execution_enabled": False, **({"error_type": error_type} if error_type else {})},
    )


_RUN_STATES: Final = frozenset(
    {
        "QUEUED",
        "PREFLIGHT",
        "RUNNING",
        "CANCELLING",
        "CANCELLED",
        "FAILED",
        "CONTROL_POSTFLIGHT",
        "INVALID_CASH_ADMISSION_CONTROL",
        "COMPLETED",
    }
)


def backtest_run_envelope(run: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Project one persisted backtest Run (task147 S11–S19, task150 B11–B14)."""

    run_id = _require_nonempty_str(run, "run_id")
    state = _require(run, "status", str)
    if state not in _RUN_STATES:
        raise ValueError(f"unknown run status {state!r}")
    raw_progress = run.get("progress")
    progress = None if raw_progress is None else canonical_decimal_string(raw_progress)
    identity: dict[str, object] = {
        "run_id": run_id,
        "dataset_id": _optional_str(run, "dataset_id"),
        "dataset_digest": _optional_str(run, "dataset_digest"),
        "config_digest": _optional_str(run, "config_digest"),
        "result_digest": _optional_str(run, "result_digest"),
        "progress": progress,
        "progress_message": _optional_str(run, "progress_message"),
        "updated_at": _optional_str(run, "updated_at"),
        "error_message": _optional_str(run, "error_message"),
    }
    advisory = ["RUN_PROGRESS_IS_SERVER_OWNED"]
    codes: list[str] = []
    blocked: list[tuple[str, str]] = []
    if state in {"QUEUED", "PREFLIGHT", "RUNNING"}:
        display, allowed = "RUNNING", ["cancel_run"]
        blocked.append(("view_results", state))
    elif state == "CANCELLING":
        display, allowed = "RUNNING", ["view_run"]
        blocked.extend([("cancel_run", state), ("retry_run", state), ("view_results", state)])
    elif state == "CONTROL_POSTFLIGHT":
        display, allowed = "RUNNING", ["view_progress"]
        blocked.append(("view_results", state))
    elif state == "CANCELLED":
        display, allowed = "TERMINAL_CANCELLED", ["retry_run"]
        blocked.append(("view_results", state))
    elif state == "FAILED":
        display, allowed, codes = (
            "TERMINAL_FAILED",
            ["retry_run", "copy_diagnostics"],
            ["RUN_FAILED"],
        )
        if identity["error_message"] is None:
            advisory.append("RUN_ERROR_MESSAGE_NOT_PROVIDED")
        blocked.append(("view_results", state))
    elif state == "INVALID_CASH_ADMISSION_CONTROL":
        display, allowed, codes = "BLOCKED", ["view_cash_admission_control"], [state]
        blocked.extend([("retry_run", state), ("view_results", state)])
    else:  # COMPLETED
        if (
            not identity["dataset_id"]
            or not _is_sha256_hex(identity["dataset_digest"])
            or not _is_sha256_hex(identity["config_digest"])
            or not _is_sha256_hex(identity["result_digest"])
        ):
            raise ValueError("completed run lacks exact result provenance")
        display, allowed = (
            "TERMINAL_SUCCESS",
            [
                "view_results",
                "export_results",
                "compare_runs",
                "clone_run",
            ],
        )
        advisory.append("COMPLETED_IS_NOT_QUALIFIED")
        blocked.append(("start_local_paper", "COMPLETED_IS_NOT_APPROVAL"))
    return _envelope(
        subject="backtest_run",
        status=display,
        now=now,
        authority_status=state,
        reason_codes=codes,
        advisory=advisory,
        allowed_actions=allowed,
        blocked_actions=blocked,
        identity=identity,
    )


def cost_snapshot_envelope(snapshot: Mapping[str, Any] | None, *, now: datetime) -> dict[str, Any]:
    """Project a sealed ``cost_policy_snapshot`` (task147 S23/S24, task150 B08–B10).

    Readiness is decided by ``backtest.cost_policy_tw.cost_policy_readiness_reason``
    (the existing authority); this envelope only mirrors it.
    """

    from backtest.cost_policy_tw import cost_policy_readiness_reason

    if snapshot is None:
        return _envelope(
            subject="cost_snapshot",
            status="BLOCKED",
            now=now,
            authority_status=None,
            reason_codes=["COST_POLICY_SNAPSHOT_MISSING"],
            allowed_actions=["view_calibration_requirements"],
            blocked_actions=[("interpret_net_result", "COST_POLICY_SNAPSHOT_MISSING")],
        )
    if not isinstance(snapshot, Mapping):
        raise TypeError("cost snapshot")
    reason = cost_policy_readiness_reason(snapshot)
    identity = {
        "contract_version": _optional_str(snapshot, "contract_version"),
        "commission_rate": _optional_str(snapshot, "commission_rate"),
        "slippage_bps": _optional_str(snapshot, "slippage_bps"),
        "slippage_calibration_digest": _optional_str(snapshot, "slippage_calibration_digest"),
        "snapshot_digest": _require(snapshot, "snapshot_digest", str),
    }
    if reason is None:
        if not _is_sha256_hex(identity["snapshot_digest"]):
            raise ValueError("ready cost snapshot lacks exact digest")
        return _envelope(
            subject="cost_snapshot",
            status="READY",
            now=now,
            authority_status="COST_POLICY_SEALED",
            allowed_actions=["view_cost_details"],
            identity=identity,
        )
    return _envelope(
        subject="cost_snapshot",
        status="BLOCKED",
        now=now,
        authority_status=reason,
        reason_codes=[reason],
        allowed_actions=["view_calibration_requirements"],
        blocked_actions=[("interpret_net_result", reason)],
        identity=identity,
    )


_COMPARISON_VERDICTS: Final = frozenset({"NOT_COMPARABLE", "NO_CLEAR_EVIDENCE", "LIKELY_IMPROVED"})


def backtest_comparison_envelope(comparison: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Project a persisted comparison (task147 S20–S22, task150 B05–B07)."""

    comparable = _require(comparison, "comparable", bool)
    verdict = _require(comparison, "verdict", str)
    if verdict not in _COMPARISON_VERDICTS:
        raise ValueError(f"unknown comparison verdict {verdict!r}")
    config_diff = _require(comparison, "config_diff", list)
    if comparable == (verdict == "NOT_COMPARABLE"):
        raise ValueError("comparison projection is inconsistent")
    if not comparable and not config_diff:
        raise ValueError("non-comparable comparison must carry config_diff")
    fields = [
        str(item.get("field"))
        for item in config_diff
        if isinstance(item, Mapping) and "field" in item
    ]
    identity: dict[str, object] = {
        "comparison_id": _optional_str(comparison, "comparison_id"),
        "baseline_run_id": _optional_str(comparison, "baseline_run_id"),
        "challenger_run_id": _optional_str(comparison, "challenger_run_id"),
        "comparison_digest": _optional_str(comparison, "comparison_digest"),
        "message": _optional_str(comparison, "message"),
        "config_diff_count": len(config_diff),
        "config_diff_fields": ",".join(fields),
    }
    if (
        not identity["comparison_id"]
        or not identity["baseline_run_id"]
        or not identity["challenger_run_id"]
    ):
        raise ValueError("comparison lacks exact entity identity")
    if verdict == "LIKELY_IMPROVED" and not _is_sha256_hex(identity["comparison_digest"]):
        raise ValueError("ready comparison lacks exact provenance")
    if verdict == "NOT_COMPARABLE":
        return _envelope(
            subject="backtest_comparison",
            status="BLOCKED",
            now=now,
            authority_status=verdict,
            reason_codes=[verdict],
            allowed_actions=["reselect_runs", "view_config_diff"],
            blocked_actions=[
                ("interpret_outcome_delta", verdict),
                ("create_qualification_evidence", verdict),
            ],
            identity=identity,
        )
    if verdict == "NO_CLEAR_EVIDENCE":
        return _envelope(
            subject="backtest_comparison",
            status="DEGRADED",
            now=now,
            authority_status=verdict,
            reason_codes=[verdict],
            allowed_actions=["view_trade_diff", "view_outcome_deltas"],
            blocked_actions=[("promote_strategy", verdict)],
            identity=identity,
        )
    return _envelope(
        subject="backtest_comparison",
        status="READY",
        now=now,
        authority_status=verdict,
        advisory=["LIKELY_IMPROVED_NOT_CAUSAL"],
        allowed_actions=[
            "create_qualification_evidence",
            "view_trade_diff",
            "view_outcome_deltas",
        ],
        blocked_actions=[("start_local_paper", "QUALIFICATION_REQUIRED")],
        identity=identity,
    )


# ---------------------------------------------------------------------------
# Validation (fail closed, exact keys — mirrors the No-Overnight envelope gate).
# ---------------------------------------------------------------------------
class StatusEnvelopeInvalid(ValueError):
    """Raised when an envelope does not satisfy the exact ``status_envelope.v1`` contract."""


def _fail(message: str) -> StatusEnvelopeInvalid:
    return StatusEnvelopeInvalid(message)


def validate_status_envelope(envelope: object) -> dict[str, Any]:
    if not isinstance(envelope, Mapping) or set(envelope) != ENVELOPE_KEYS:
        raise _fail("envelope keys are not exact")
    if envelope["schema_version"] != STATUS_ENVELOPE_SCHEMA:
        raise _fail("envelope schema mismatch")
    if envelope["subject"] not in SUBJECTS + ENTITY_SUBJECTS + ("operator_surface",):
        raise _fail("unknown subject")
    if envelope["authority"] not in AUTHORITY_CLASSES:
        raise _fail("unknown authority class")
    status = envelope["status"]
    if status not in DISPLAY_STATES:
        raise _fail("unknown display state")
    glyph, label, _a11y, _live = DISPLAY_STATES[status]
    if envelope["status_glyph"] != glyph or envelope["status_label"] != label:
        raise _fail("display state copy mismatch")
    if envelope["authority_status"] is not None and type(envelope["authority_status"]) is not str:
        raise _fail("authority_status type")
    if type(envelope["revision"]) is not int or envelope["revision"] < 0:
        raise _fail("revision type")
    if type(envelope["as_of"]) is not str or not envelope["as_of"]:
        raise _fail("as_of type")
    codes = envelope["reason_codes"]
    if not isinstance(codes, list) or any(type(code) is not str or not code for code in codes):
        raise _fail("reason_codes type")
    reasons = envelope["reasons"]
    if (
        not isinstance(reasons, list)
        or [r.get("code") if isinstance(r, Mapping) else None for r in reasons] != codes
    ):
        raise _fail("reasons must mirror reason_codes")
    for reason in reasons:
        if set(reason) != REASON_KEYS or type(reason["known"]) is not bool:
            raise _fail("reason entry keys")
        if any(type(reason[key]) is not str for key in ("title", "impact", "next_step", "a11y")):
            raise _fail("reason entry types")
    advisory = envelope["advisory"]
    if not isinstance(advisory, list) or any(
        not isinstance(item, Mapping)
        or set(item) != ADVISORY_KEYS
        or any(type(item[key]) is not str or not item[key] for key in ADVISORY_KEYS)
        for item in advisory
    ):
        raise _fail("advisory entries")
    for key in ("allowed_actions",):
        if not isinstance(envelope[key], list) or any(type(a) is not str for a in envelope[key]):
            raise _fail(f"{key} type")
    blocked = envelope["blocked_actions"]
    if not isinstance(blocked, list) or any(
        not isinstance(item, Mapping)
        or set(item) != BLOCKED_ACTION_KEYS
        or any(type(item[key]) is not str for key in BLOCKED_ACTION_KEYS)
        for item in blocked
    ):
        raise _fail("blocked_actions entries")
    if set(envelope["allowed_actions"]) & {item["action"] for item in blocked}:
        raise _fail("an action cannot be both allowed and blocked")
    identity = envelope["identity"]
    if not isinstance(identity, Mapping):
        raise _fail("identity must be an object")
    try:
        _validate_signed_value(envelope)
    except ValueError as error:
        raise _fail(str(error)) from error
    if envelope["a11y"] not in {"A-INFO", "A-WARN", "A-BLOCK", "A-CRIT"}:
        raise _fail("a11y token")
    if envelope["live_region"] not in {"polite", "assertive"}:
        raise _fail("live region")
    client_policy = envelope["client_policy"]
    if not isinstance(client_policy, Mapping):
        raise _fail("client_policy type")
    if envelope["subject"] == "local_paper_runtime" and status != "UNAVAILABLE":
        if set(client_policy) != MOBILE_READ_ONLY_POLICY_KEYS:
            raise _fail("local paper client policy keys")
        if client_policy != MOBILE_READ_ONLY_POLICY:
            raise _fail("local paper mobile policy mismatch")
        advisory_codes = {item["code"] for item in advisory}
        if MOBILE_READ_ONLY_POLICY["reason_code"] not in advisory_codes:
            raise _fail("mobile policy reason is not server-owned advisory copy")
    if status in POSITIVE_STATES and any(
        reason["a11y"] in {"A-BLOCK", "A-CRIT"} for reason in reasons
    ):
        raise _fail("a blocking reason cannot carry a positive display state")
    if status == "UNAVAILABLE" and envelope["allowed_actions"] != [_ACTION_RELOAD]:
        raise _fail("unavailable envelopes only allow reload")
    if type(envelope["digest"]) is not str or envelope["digest"] != envelope_digest(envelope):
        raise _fail("digest mismatch")
    return dict(envelope)


def validate_status_envelope_set(
    payload: object, *, subjects: Sequence[str] = SUBJECTS
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != SET_KEYS:
        raise _fail("envelope set keys are not exact")
    if payload["schema_version"] != STATUS_ENVELOPE_SET_SCHEMA:
        raise _fail("envelope set schema mismatch")
    if type(payload["as_of"]) is not str or not payload["as_of"]:
        raise _fail("envelope set as_of")
    envelopes = payload["envelopes"]
    if not isinstance(envelopes, Mapping) or list(envelopes) != list(subjects):
        raise _fail("envelope set subjects are not exact")
    for subject, envelope in envelopes.items():
        validated = validate_status_envelope(envelope)
        if validated["subject"] != subject:
            raise _fail("envelope subject mismatch")
    return dict(payload)


# ---------------------------------------------------------------------------
# Composition helper used by the dashboard route.
# ---------------------------------------------------------------------------
SubjectBuilder = Callable[[], dict[str, Any]]


def build_status_envelope_set(
    builders: Mapping[str, SubjectBuilder],
    *,
    now: datetime,
    subjects: Sequence[str] = SUBJECTS,
) -> dict[str, Any]:
    """Run one builder per subject; any raise becomes an UNAVAILABLE envelope.

    The set is validated as a whole before it is returned so the route can
    fail closed (503) instead of shipping a partially trusted projection.
    """

    envelopes: dict[str, Any] = {}
    for subject in subjects:
        builder = builders.get(subject)
        if builder is None:
            if subject == "market_shadow":
                envelopes[subject] = market_shadow_envelope(now=now, error_type="BuilderMissing")
            else:
                envelopes[subject] = unavailable_envelope(
                    subject, now=now, error_type="BuilderMissing"
                )
            continue
        try:
            envelopes[subject] = builder()
        except Exception as error:  # noqa: BLE001 - fail closed by design
            envelopes[subject] = unavailable_envelope(
                subject, now=now, error_type=type(error).__name__
            )
    payload = {
        "schema_version": STATUS_ENVELOPE_SET_SCHEMA,
        "as_of": _iso(now),
        "envelopes": envelopes,
    }
    return validate_status_envelope_set(payload, subjects=subjects)
