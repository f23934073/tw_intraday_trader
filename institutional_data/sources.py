"""Official TWSE/TPEx institutional-flow fetch and normalization adapters."""

from __future__ import annotations

import json
import re
import ssl
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from institutional_data.artifacts import InstitutionalRawArtifact
from institutional_data.domain import (
    CorrectionPolicy,
    InstitutionalFlowDaily,
    InstitutionalMarket,
)


TWSE_SOURCE_PRODUCT = "TWSE_T86_FINAL"
TWSE_TRADE_SCOPE_ID = "TWSE_T86_FINAL_WITH_BLOCK_V1"
TWSE_PARSER_VERSION = "twse_t86_json_v1"
TWSE_ENDPOINT = "https://www.twse.com.tw/rwd/zh/fund/T86"
TWSE_RESPONSE_SCOPE_NOTE = (
    "TWSE T86 final data: includes general, odd-lot, after-hours fixed-price and "
    "block trades; excludes auction and tender; original trades."
)

TPEX_SOURCE_PRODUCT = "TPEX_INSTI_DAILY_EW"
TPEX_TRADE_SCOPE_ID = "TPEX_DAILY_ORIGINAL_TRADES_V1"
TPEX_PARSER_VERSION = "tpex_insti_daily_trade_v1"
TPEX_ENDPOINT = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
TPEX_RESPONSE_SCOPE_NOTE = (
    "TPEx daily EW data: all securities excluding warrants and bull/bear "
    "certificates; includes ordinary, block and odd-lot trades; original trades."
)


@dataclass(frozen=True)
class InstitutionalSourceResponse:
    """Transport result retained byte-for-byte before normalization."""

    source_url: str
    request_method: str
    request_parameters: tuple[tuple[str, str], ...]
    response_headers: tuple[tuple[str, str], ...]
    content_type: str
    retrieved_at: datetime
    first_observed_at: datetime
    body: bytes

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if (
            self.first_observed_at.tzinfo is None
            or self.first_observed_at.utcoffset() is None
        ):
            raise ValueError("first_observed_at must be timezone-aware")
        if self.first_observed_at > self.retrieved_at:
            raise ValueError("first_observed_at cannot be after retrieved_at")
        if not isinstance(self.body, bytes):
            raise ValueError("body must be bytes")


@dataclass(frozen=True)
class ParsedInstitutionalSource:
    rows: tuple[InstitutionalFlowDaily, ...]
    source_row_count: int


class InstitutionalSourceContractError(ValueError):
    """Official response is not safe to publish as a normalized partition."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class InstitutionalOfficialSourceAdapter(Protocol):
    market: InstitutionalMarket
    source_product: str
    trade_scope_id: str
    correction_policy: CorrectionPolicy
    response_scope_note: str
    parser_version: str

    def fetch(
        self,
        session_date: date,
        *,
        timeout_seconds: float = 30.0,
    ) -> InstitutionalSourceResponse:
        """Fetch one official response without parsing it."""

    def parse(
        self,
        artifact: InstitutionalRawArtifact,
        *,
        partition_id: str,
        requested_session: date,
        usable_from_session: date,
    ) -> ParsedInstitutionalSource:
        """Strictly normalize a previously sealed raw artifact."""


def _official_https_context() -> ssl.SSLContext:
    """Keep peer/hostname validation while tolerating TPEx's legacy chain metadata."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        # Python 3.13 enables strict-chain checks which reject TPEx's otherwise
        # trusted chain because one certificate omits Subject Key Identifier.
        context.verify_flags &= ~strict_flag
    return context


def _fetch_response(
    *,
    source_url: str,
    method: str,
    parameters: tuple[tuple[str, str], ...],
    timeout_seconds: float,
) -> InstitutionalSourceResponse:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    encoded = urlencode(parameters)
    request_url = f"{source_url}?{encoded}" if method == "GET" else source_url
    request_body = encoded.encode("ascii") if method == "POST" else None
    request = Request(
        request_url,
        data=request_body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "tw-intraday-trader/0.1 institutional-source-adapter",
        },
    )
    with urlopen(  # nosec B310: endpoints are fixed HTTPS constants
        request,
        timeout=timeout_seconds,
        context=_official_https_context(),
    ) as response:
        body = response.read()
        response_headers = tuple(
            (str(key), str(value)) for key, value in response.headers.items()
        )
        content_type = response.headers.get_content_type()
        final_url = response.geturl()
    observed_at = datetime.now(timezone.utc)
    return InstitutionalSourceResponse(
        source_url=final_url,
        request_method=method,
        request_parameters=parameters,
        response_headers=response_headers,
        content_type=content_type,
        retrieved_at=observed_at,
        first_observed_at=observed_at,
        body=body,
    )


def _json_object(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise InstitutionalSourceContractError("EMPTY_RESPONSE", "response is empty")
    try:
        decoded = payload.decode("utf-8-sig")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstitutionalSourceContractError(
            "INVALID_JSON",
            "response is not valid UTF-8 JSON",
        ) from error
    if not isinstance(value, dict):
        raise InstitutionalSourceContractError(
            "SCHEMA_DRIFT",
            "response envelope must be an object",
        )
    return value


def _require_exact_keys(
    value: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    if set(value) == expected:
        return
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing={','.join(missing)}")
    if unexpected:
        details.append(f"unexpected={','.join(unexpected)}")
    raise InstitutionalSourceContractError(
        "SCHEMA_DRIFT",
        f"{label} keys changed ({'; '.join(details)})",
    )


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InstitutionalSourceContractError(
            "SCHEMA_DRIFT",
            f"{field_name} must be a string",
        )
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InstitutionalSourceContractError(
            "SCHEMA_DRIFT",
            f"{field_name} must be an integer",
        )
    return value


_PLAIN_INTEGER = re.compile(r"[+-]?(?:0|[1-9]\d*)")
_GROUPED_INTEGER = re.compile(r"[+-]?[1-9]\d{0,2}(?:,\d{3})+")


def _shares(value: object, field_name: str) -> int:
    text = _require_string(value, field_name).strip()
    if not (_PLAIN_INTEGER.fullmatch(text) or _GROUPED_INTEGER.fullmatch(text)):
        raise InstitutionalSourceContractError(
            "INVALID_NUMERIC_VALUE",
            f"{field_name} is not a canonical share count",
        )
    return int(text.replace(",", ""))


def _require_row(value: object, length: int, label: str) -> list[Any]:
    if not isinstance(value, list) or len(value) != length:
        raise InstitutionalSourceContractError(
            "SCHEMA_DRIFT",
            f"{label} must contain exactly {length} values",
        )
    return value


def _require_requested_parameters(
    artifact: InstitutionalRawArtifact,
    expected: tuple[tuple[str, str], ...],
) -> None:
    if artifact.request_parameters != expected:
        raise InstitutionalSourceContractError(
            "SCOPE_MISMATCH",
            "captured request parameters do not match the reviewed source scope",
        )


def _require_endpoint(artifact: InstitutionalRawArtifact, endpoint: str) -> None:
    actual = urlsplit(artifact.source_url)
    expected = urlsplit(endpoint)
    if (
        actual.scheme != expected.scheme
        or actual.netloc != expected.netloc
        or actual.path != expected.path
    ):
        raise InstitutionalSourceContractError(
            "SOURCE_ENDPOINT_MISMATCH",
            "captured response did not originate from the reviewed endpoint",
        )


def _build_row(
    *,
    artifact: InstitutionalRawArtifact,
    partition_id: str,
    requested_session: date,
    usable_from_session: date,
    symbol: str,
    foreign_ex_dealer: tuple[int, int, int],
    foreign_dealer: tuple[int, int, int] | None,
    investment_trust: tuple[int, int, int],
    dealer_proprietary: tuple[int, int, int] | None,
    dealer_hedge: tuple[int, int, int] | None,
    dealer_total: tuple[int, int, int],
    published_total: int,
) -> InstitutionalFlowDaily:
    def optional(
        values: tuple[int, int, int] | None,
    ) -> tuple[int | None, int | None, int | None]:
        return (None, None, None) if values is None else values

    foreign_dealer_values = optional(foreign_dealer)
    dealer_proprietary_values = optional(dealer_proprietary)
    dealer_hedge_values = optional(dealer_hedge)
    return InstitutionalFlowDaily(
        partition_id=partition_id,
        market=artifact.key.market,
        symbol=symbol,
        session_date=requested_session,
        foreign_ex_dealer_buy_shares=foreign_ex_dealer[0],
        foreign_ex_dealer_sell_shares=foreign_ex_dealer[1],
        foreign_ex_dealer_net_shares=foreign_ex_dealer[2],
        foreign_dealer_buy_shares=foreign_dealer_values[0],
        foreign_dealer_sell_shares=foreign_dealer_values[1],
        foreign_dealer_net_shares=foreign_dealer_values[2],
        investment_trust_buy_shares=investment_trust[0],
        investment_trust_sell_shares=investment_trust[1],
        investment_trust_net_shares=investment_trust[2],
        dealer_proprietary_buy_shares=dealer_proprietary_values[0],
        dealer_proprietary_sell_shares=dealer_proprietary_values[1],
        dealer_proprietary_net_shares=dealer_proprietary_values[2],
        dealer_hedge_buy_shares=dealer_hedge_values[0],
        dealer_hedge_sell_shares=dealer_hedge_values[1],
        dealer_hedge_net_shares=dealer_hedge_values[2],
        dealer_total_buy_shares=dealer_total[0],
        dealer_total_sell_shares=dealer_total[1],
        dealer_total_net_shares=dealer_total[2],
        published_total_net_shares=published_total,
        trade_scope_id=artifact.key.trade_scope_id,
        correction_policy=CorrectionPolicy.ORIGINAL_TRADES,
        raw_artifact_id=artifact.artifact_id,
        raw_sha256=artifact.raw_sha256,
        retrieved_at=artifact.retrieved_at,
        first_observed_at=artifact.first_observed_at,
        usable_from_session=usable_from_session,
    )


TWSE_FIELDS = (
    "證券代號",
    "證券名稱",
    "外陸資買進股數(不含外資自營商)",
    "外陸資賣出股數(不含外資自營商)",
    "外陸資買賣超股數(不含外資自營商)",
    "外資自營商買進股數",
    "外資自營商賣出股數",
    "外資自營商買賣超股數",
    "投信買進股數",
    "投信賣出股數",
    "投信買賣超股數",
    "自營商買賣超股數",
    "自營商買進股數(自行買賣)",
    "自營商賣出股數(自行買賣)",
    "自營商買賣超股數(自行買賣)",
    "自營商買進股數(避險)",
    "自營商賣出股數(避險)",
    "自營商買賣超股數(避險)",
    "三大法人買賣超股數",
)

_TWSE_ENVELOPE_KEYS = {
    "data",
    "date",
    "fields",
    "hints",
    "notes",
    "selectType",
    "stat",
    "title",
    "total",
}


class TwseInstitutionalSourceAdapter:
    market = InstitutionalMarket.TWSE
    source_product = TWSE_SOURCE_PRODUCT
    trade_scope_id = TWSE_TRADE_SCOPE_ID
    correction_policy = CorrectionPolicy.ORIGINAL_TRADES
    response_scope_note = TWSE_RESPONSE_SCOPE_NOTE
    parser_version = TWSE_PARSER_VERSION

    def fetch(
        self,
        session_date: date,
        *,
        timeout_seconds: float = 30.0,
    ) -> InstitutionalSourceResponse:
        return _fetch_response(
            source_url=TWSE_ENDPOINT,
            method="GET",
            parameters=(
                ("date", session_date.strftime("%Y%m%d")),
                ("selectType", "ALLBUT0999"),
                ("response", "json"),
            ),
            timeout_seconds=timeout_seconds,
        )

    def parse(
        self,
        artifact: InstitutionalRawArtifact,
        *,
        partition_id: str,
        requested_session: date,
        usable_from_session: date,
    ) -> ParsedInstitutionalSource:
        expected_date = requested_session.strftime("%Y%m%d")
        _require_endpoint(artifact, TWSE_ENDPOINT)
        _require_requested_parameters(
            artifact,
            (
                ("date", expected_date),
                ("selectType", "ALLBUT0999"),
                ("response", "json"),
            ),
        )
        payload = _json_object(artifact.payload)
        _require_exact_keys(payload, _TWSE_ENVELOPE_KEYS, "TWSE envelope")
        if payload["stat"] != "OK":
            raise InstitutionalSourceContractError(
                "SOURCE_NOT_OK",
                "TWSE response status is not OK",
            )
        if payload["date"] != expected_date:
            raise InstitutionalSourceContractError(
                "RESPONSE_DATE_MISMATCH",
                "TWSE response date differs from the requested session",
            )
        if payload["selectType"] != "ALLBUT0999":
            raise InstitutionalSourceContractError(
                "SCOPE_MISMATCH",
                "TWSE selectType differs from the reviewed final scope",
            )
        if payload["hints"] != "單位：股":
            raise InstitutionalSourceContractError(
                "UNIT_MISMATCH",
                "TWSE source unit is not shares",
            )
        if tuple(payload["fields"]) != TWSE_FIELDS:
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TWSE T86 fields changed",
            )
        notes = payload["notes"]
        if not isinstance(notes, list) or not all(
            isinstance(note, str) for note in notes
        ):
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TWSE notes must be a list of strings",
            )
        required_scope_notes = (
            "本統計資訊含一般、零股、盤後定價、鉅額，不含拍賣、標購。",
            "本資訊以當日原始成交情形統計，不以證券商申報錯帳、更正帳號等調整後資料統計。",
        )
        if not all(note in notes for note in required_scope_notes):
            raise InstitutionalSourceContractError(
                "SCOPE_MISMATCH",
                "TWSE scope/correction notes differ from the reviewed contract",
            )
        data = payload["data"]
        if not isinstance(data, list) or not data:
            raise InstitutionalSourceContractError(
                "EMPTY_RESPONSE",
                "TWSE response has no data rows",
            )
        total = _require_int(payload["total"], "TWSE total")
        if total != len(data):
            raise InstitutionalSourceContractError(
                "ROW_COUNT_MISMATCH",
                "TWSE total does not match the data row count",
            )

        rows: list[InstitutionalFlowDaily] = []
        for row_index, value in enumerate(data):
            source = _require_row(value, len(TWSE_FIELDS), f"TWSE row {row_index}")
            symbol = _require_string(source[0], f"TWSE row {row_index} symbol")
            _require_string(source[1], f"TWSE row {row_index} name")
            prop = tuple(
                _shares(source[index], f"TWSE row {row_index} field {index}")
                for index in (12, 13, 14)
            )
            hedge = tuple(
                _shares(source[index], f"TWSE row {row_index} field {index}")
                for index in (15, 16, 17)
            )
            rows.append(
                _build_row(
                    artifact=artifact,
                    partition_id=partition_id,
                    requested_session=requested_session,
                    usable_from_session=usable_from_session,
                    symbol=symbol,
                    foreign_ex_dealer=tuple(
                        _shares(source[index], f"TWSE row {row_index} field {index}")
                        for index in (2, 3, 4)
                    ),
                    foreign_dealer=tuple(
                        _shares(source[index], f"TWSE row {row_index} field {index}")
                        for index in (5, 6, 7)
                    ),
                    investment_trust=tuple(
                        _shares(source[index], f"TWSE row {row_index} field {index}")
                        for index in (8, 9, 10)
                    ),
                    dealer_proprietary=prop,
                    dealer_hedge=hedge,
                    dealer_total=(
                        prop[0] + hedge[0],
                        prop[1] + hedge[1],
                        _shares(source[11], f"TWSE row {row_index} field 11"),
                    ),
                    published_total=_shares(
                        source[18],
                        f"TWSE row {row_index} field 18",
                    ),
                )
            )
        return ParsedInstitutionalSource(tuple(rows), total)


TPEX_FIELDS = (
    "代號",
    "名稱",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "三大法人買賣超股數合計",
)

_TPEX_ENVELOPE_KEYS = {"columnNum", "date", "stat", "tables", "template"}
_TPEX_TABLE_KEYS = {
    "columnNum",
    "data",
    "date",
    "fields",
    "notes",
    "subtitle",
    "summary",
    "title",
    "totalCount",
}


def _parse_roc_date(value: object) -> date:
    text = _require_string(value, "TPEx table date")
    match = re.fullmatch(r"(\d{3})/(\d{2})/(\d{2})", text)
    if match is None:
        raise InstitutionalSourceContractError(
            "SCHEMA_DRIFT",
            "TPEx table date is not ROC YYY/MM/DD",
        )
    try:
        return date(
            int(match.group(1)) + 1911, int(match.group(2)), int(match.group(3))
        )
    except ValueError as error:
        raise InstitutionalSourceContractError(
            "RESPONSE_DATE_MISMATCH",
            "TPEx table date is invalid",
        ) from error


class TpexInstitutionalSourceAdapter:
    market = InstitutionalMarket.TPEX
    source_product = TPEX_SOURCE_PRODUCT
    trade_scope_id = TPEX_TRADE_SCOPE_ID
    correction_policy = CorrectionPolicy.ORIGINAL_TRADES
    response_scope_note = TPEX_RESPONSE_SCOPE_NOTE
    parser_version = TPEX_PARSER_VERSION

    def fetch(
        self,
        session_date: date,
        *,
        timeout_seconds: float = 30.0,
    ) -> InstitutionalSourceResponse:
        return _fetch_response(
            source_url=TPEX_ENDPOINT,
            method="POST",
            parameters=(
                ("type", "Daily"),
                ("sect", "EW"),
                ("date", session_date.strftime("%Y/%m/%d")),
                ("response", "json"),
            ),
            timeout_seconds=timeout_seconds,
        )

    def parse(
        self,
        artifact: InstitutionalRawArtifact,
        *,
        partition_id: str,
        requested_session: date,
        usable_from_session: date,
    ) -> ParsedInstitutionalSource:
        expected_date = requested_session.strftime("%Y%m%d")
        expected_request_date = requested_session.strftime("%Y/%m/%d")
        _require_endpoint(artifact, TPEX_ENDPOINT)
        _require_requested_parameters(
            artifact,
            (
                ("type", "Daily"),
                ("sect", "EW"),
                ("date", expected_request_date),
                ("response", "json"),
            ),
        )
        payload = _json_object(artifact.payload)
        _require_exact_keys(payload, _TPEX_ENVELOPE_KEYS, "TPEx envelope")
        if payload["stat"] != "ok":
            raise InstitutionalSourceContractError(
                "SOURCE_NOT_OK",
                "TPEx response status is not ok",
            )
        if payload["date"] != expected_date:
            raise InstitutionalSourceContractError(
                "RESPONSE_DATE_MISMATCH",
                "TPEx response date differs from the requested session",
            )
        if payload["template"] != "/template/insti/dailyTrade":
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TPEx template marker changed",
            )
        if _require_int(payload["columnNum"], "TPEx columnNum") != 25:
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TPEx columnNum changed",
            )
        tables = payload["tables"]
        if not isinstance(tables, list) or len(tables) != 2 or tables[1] != {}:
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TPEx table envelope changed",
            )
        table = tables[0]
        if not isinstance(table, dict):
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TPEx active table must be an object",
            )
        _require_exact_keys(table, _TPEX_TABLE_KEYS, "TPEx active table")
        if _require_int(table["columnNum"], "TPEx table columnNum") != 25:
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TPEx table columnNum changed",
            )
        if _parse_roc_date(table["date"]) != requested_session:
            raise InstitutionalSourceContractError(
                "RESPONSE_DATE_MISMATCH",
                "TPEx table date differs from the requested session",
            )
        if tuple(table["fields"]) != TPEX_FIELDS:
            raise InstitutionalSourceContractError(
                "SCHEMA_DRIFT",
                "TPEx institutional fields changed",
            )
        subtitle = _require_string(table["subtitle"], "TPEx subtitle")
        required_scope_markers = ("含普通股", "鉅額", "零股", "投信買賣成交量")
        if not all(marker in subtitle for marker in required_scope_markers):
            raise InstitutionalSourceContractError(
                "SCOPE_MISMATCH",
                "TPEx response scope subtitle changed",
            )
        data = table["data"]
        if not isinstance(data, list) or not data:
            raise InstitutionalSourceContractError(
                "EMPTY_RESPONSE",
                "TPEx response has no data rows",
            )
        total = _require_int(table["totalCount"], "TPEx totalCount")
        if total != len(data):
            raise InstitutionalSourceContractError(
                "ROW_COUNT_MISMATCH",
                "TPEx totalCount does not match the data row count",
            )

        rows: list[InstitutionalFlowDaily] = []
        for row_index, value in enumerate(data):
            source = _require_row(value, len(TPEX_FIELDS), f"TPEx row {row_index}")
            symbol = _require_string(source[0], f"TPEx row {row_index} symbol")
            _require_string(source[1], f"TPEx row {row_index} name")
            values = tuple(
                _shares(source[index], f"TPEx row {row_index} field {index}")
                for index in range(2, len(TPEX_FIELDS))
            )
            foreign_ex_dealer = values[0:3]
            foreign_dealer = values[3:6]
            combined_foreign = values[6:9]
            expected_combined = tuple(
                foreign_ex_dealer[index] + foreign_dealer[index] for index in range(3)
            )
            if combined_foreign != expected_combined:
                raise InstitutionalSourceContractError(
                    "FOREIGN_TOTAL_MISMATCH",
                    f"TPEx combined foreign values do not reconcile for {symbol}",
                )
            rows.append(
                _build_row(
                    artifact=artifact,
                    partition_id=partition_id,
                    requested_session=requested_session,
                    usable_from_session=usable_from_session,
                    symbol=symbol,
                    foreign_ex_dealer=foreign_ex_dealer,
                    foreign_dealer=foreign_dealer,
                    investment_trust=values[9:12],
                    dealer_proprietary=values[12:15],
                    dealer_hedge=values[15:18],
                    dealer_total=values[18:21],
                    published_total=values[21],
                )
            )
        return ParsedInstitutionalSource(tuple(rows), total)
