"""Strict adapter for the official TAIFEX after-hours daily futures report."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from premarket.artifacts import canonical_json, sha256_text_digest
from premarket.models import (
    ContractIdentityStatus,
    ReconciliationObservation,
    TaifexNightContextArtifact,
)


TAIFEX_FUT_DAILY_REPORT_URL = (
    "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
)
TAIFEX_DAILY_REPORT_SOURCE = "TAIFEX_FUT_DAILY_MARKET_REPORT"
TAIFEX_DAILY_REPORT_CAPTURE_SCHEMA = "taifex_fut_daily_report_capture_v0"
TAIFEX_AFTER_HOURS_VOLUME_BASIS = "INCLUDES_SPREAD_AND_BLOCK_CONTRACTS"
TAIFEX_AFTER_HOURS_VOLUME_LIMITATION = "TAIFEX_VOLUME_BASIS_UNQUALIFIED"


@dataclass(frozen=True)
class TaifexDailyReportCapture:
    schema_version: str
    source: str
    source_url: str
    trading_date: date
    product_code: str
    market_code: str
    request_parameters: tuple[tuple[str, str], ...]
    retrieved_at: datetime
    raw_response_encoding: str
    raw_response_text: str
    raw_response_sha256: str

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("TAIFEX capture retrieved_at must be timezone-aware")


class _TableRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, ...]] = []
        self.text_parts: list[str] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []
        elif tag.lower() == "br" and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._cell_parts is not None:
            assert self._row is not None
            self._row.append(_normalize_text("".join(self._cell_parts)))
            self._cell_parts = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(tuple(self._row))
            self._row = None
            self._cell_parts = None

    @property
    def page_text(self) -> str:
        return _normalize_text(" ".join(self.text_parts), remove_spaces=False)


def _normalize_text(value: str, *, remove_spaces: bool = True) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized.replace(" ", "") if remove_spaces else normalized


def _request_parameters(
    trading_date: date,
    product_code: str,
) -> tuple[tuple[str, str], ...]:
    return (
        ("MarketCode", "1"),
        ("commodity_id", product_code),
        ("commodity_idt", product_code),
        ("marketCode", "1"),
        ("queryDate", trading_date.strftime("%Y/%m/%d")),
        ("queryType", "2"),
    )


def build_taifex_daily_report_capture(
    *,
    trading_date: date,
    product_code: str,
    retrieved_at: datetime,
    raw_response: bytes,
) -> TaifexDailyReportCapture:
    if product_code != "TX":
        raise ValueError("TAIFEX premarket reconciliation only supports TX")
    try:
        raw_text = raw_response.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("TAIFEX daily report must be UTF-8 HTML") from error
    return TaifexDailyReportCapture(
        schema_version=TAIFEX_DAILY_REPORT_CAPTURE_SCHEMA,
        source=TAIFEX_DAILY_REPORT_SOURCE,
        source_url=TAIFEX_FUT_DAILY_REPORT_URL,
        trading_date=trading_date,
        product_code=product_code,
        market_code="1",
        request_parameters=_request_parameters(trading_date, product_code),
        retrieved_at=retrieved_at,
        raw_response_encoding="utf-8",
        raw_response_text=raw_text,
        raw_response_sha256=sha256(raw_response).hexdigest(),
    )


def fetch_taifex_daily_report(
    *,
    trading_date: date,
    product_code: str,
    retrieved_at: datetime,
    timeout_seconds: float = 30,
) -> TaifexDailyReportCapture:
    parameters = _request_parameters(trading_date, product_code)
    request = Request(
        TAIFEX_FUT_DAILY_REPORT_URL,
        data=urlencode(parameters).encode("ascii"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "tw-intraday-trader-taifex-reconciliation",
        },
        method="POST",
    )
    with urlopen(  # nosec B310: fixed HTTPS TAIFEX URL
        request,
        timeout=timeout_seconds,
    ) as response:
        raw_response = response.read()
    return build_taifex_daily_report_capture(
        trading_date=trading_date,
        product_code=product_code,
        retrieved_at=retrieved_at,
        raw_response=raw_response,
    )


def _decimal_or_none(value: str, field: str) -> Decimal | None:
    if value in {"", "-"}:
        return None
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise ValueError(f"official TAIFEX {field} is invalid") from error
    if not parsed.is_finite():
        raise ValueError(f"official TAIFEX {field} must be finite")
    return parsed


def _volume(value: str) -> int:
    parsed = _decimal_or_none(value, "volume")
    if parsed is None or parsed != parsed.to_integral_value() or parsed < 0:
        raise ValueError("official TAIFEX volume must be a non-negative integer")
    return int(parsed)


def _parse_report_row(
    capture: TaifexDailyReportCapture,
    *,
    delivery_month: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, int, Decimal | None]:
    parser = _TableRowParser()
    parser.feed(capture.raw_response_text)
    page_text = parser.page_text
    date_match = re.search(r"日期：\s*(\d{4}/\d{2}/\d{2})", page_text)
    if date_match is None:
        raise ValueError("official TAIFEX response trading date is missing")
    response_date = datetime.strptime(date_match.group(1), "%Y/%m/%d").date()
    if response_date != capture.trading_date:
        raise ValueError("official TAIFEX response trading date does not match request")
    if "盤後交易時段行情表" not in page_text:
        raise ValueError("official TAIFEX response is not an after-hours report")
    if "成交量與未沖銷契約量均含價差交易與鉅額交易成交之契約" not in page_text:
        raise ValueError("official TAIFEX volume scope note is missing")

    header = (
        "契約",
        "到期月份(週別)",
        "開盤價",
        "最高價",
        "最低價",
        "最後成交價",
        "漲跌價",
        "漲跌%",
        "*成交量",
        "結算價",
    )
    if not any(row[: len(header)] == header for row in parser.rows):
        raise ValueError("official TAIFEX report fields do not match reviewed contract")
    matches = [
        row
        for row in parser.rows
        if len(row) >= len(header)
        and row[0] == capture.product_code
        and row[1] == delivery_month
    ]
    if len(matches) != 1:
        raise ValueError(
            "official TAIFEX report has no unique row for the delivery month"
        )
    row = matches[0]
    values = tuple(
        _decimal_or_none(row[index], field)
        for index, field in zip(
            (2, 3, 4, 5),
            ("open", "high", "low", "close"),
        )
    )
    if any(value is None for value in values):
        raise ValueError("official TAIFEX row has missing OHLC")
    open_price, high, low, close = values
    assert open_price is not None and high is not None
    assert low is not None and close is not None
    return (
        open_price,
        high,
        low,
        close,
        _volume(row[8]),
        _decimal_or_none(row[9], "settlement price"),
    )


def parse_taifex_after_hours_observation(
    capture: TaifexDailyReportCapture,
    *,
    context: TaifexNightContextArtifact,
) -> ReconciliationObservation:
    if capture.schema_version != TAIFEX_DAILY_REPORT_CAPTURE_SCHEMA:
        raise ValueError("unsupported TAIFEX daily report capture schema")
    if (
        capture.source != TAIFEX_DAILY_REPORT_SOURCE
        or capture.source_url != TAIFEX_FUT_DAILY_REPORT_URL
    ):
        raise ValueError("capture must use the official TAIFEX source URL")
    if capture.product_code != "TX" or context.product_root != "TXF":
        raise ValueError("TAIFEX report product does not match context product")
    if capture.market_code != "1" or capture.request_parameters != _request_parameters(
        capture.trading_date,
        capture.product_code,
    ):
        raise ValueError("TAIFEX capture request is not the reviewed after-hours query")
    if capture.trading_date != context.trading_date:
        raise ValueError("TAIFEX capture trading date does not match context")
    if sha256(capture.raw_response_text.encode("utf-8")).hexdigest() != (
        capture.raw_response_sha256
    ):
        raise ValueError("TAIFEX capture response digest does not match")

    identity = context.contract_identity
    if (
        identity.status is ContractIdentityStatus.UNRESOLVED
        or identity.resolved_contract_code is None
    ):
        raise ValueError("TAIFEX reconciliation requires a resolved contract identity")
    if identity.delivery_month is None:
        raise ValueError("TAIFEX reconciliation requires a dated delivery month")
    open_price, high, low, close, volume, settlement = _parse_report_row(
        capture,
        delivery_month=identity.delivery_month,
    )
    raw_source_json = canonical_json(asdict(capture))
    return ReconciliationObservation(
        source=TAIFEX_DAILY_REPORT_SOURCE,
        raw_source_digest=sha256_text_digest(raw_source_json),
        raw_source_json=raw_source_json,
        taifex_trading_date=capture.trading_date,
        contract_code=identity.resolved_contract_code,
        reconciled_at=capture.retrieved_at,
        taifex_settlement_price=settlement,
        taifex_open=open_price,
        taifex_high=high,
        taifex_low=low,
        taifex_close=close,
        taifex_volume=volume,
        taifex_delivery_month=identity.delivery_month,
        taifex_volume_basis=TAIFEX_AFTER_HOURS_VOLUME_BASIS,
        comparable_fields=("open", "high", "low", "close"),
        comparison_limitations=(TAIFEX_AFTER_HOURS_VOLUME_LIMITATION,),
    )
