"""Paced, symbol-day checkpointed FinMind Sponsor history acquisition."""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import sleep
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from backtest.domain import HistoricalBar, canonical_json, decimal


TAIPEI = ZoneInfo("Asia/Taipei")
DATA_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"
USAGE_ENDPOINT = "https://api.web.finmindtrade.com/v2/user_info"
REGULAR_OPEN = time(9, 0)
REGULAR_CLOSE = time(13, 30)
DELAYED_CLOSE = time(13, 33)
SOURCE = "FINMIND_SPONSOR_TAIWAN_STOCK_KBAR"
SOURCE_VERSION = "FINMIND_API_V4"
VOLUME_UNIT = "COMMON_LOTS"


class FinMindRequestError(RuntimeError):
    """A FinMind response is unusable and the current batch must stop."""

    def __init__(self, message: str, *, response: FinMindResponse | None = None) -> None:
        super().__init__(message)
        self.response = response


class FinMindQuotaReached(FinMindRequestError):
    """FinMind reports that the current request allowance is exhausted."""


@dataclass(frozen=True)
class FinMindResponse:
    http_status: int
    body: bytes
    payload: Mapping[str, Any] | None


@dataclass(frozen=True)
class FinMindUsage:
    user_count: int
    api_request_limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.api_request_limit - self.user_count)


@dataclass(frozen=True)
class FinMindIndustryLeader:
    industry: str
    symbol: str
    name: str
    market: str
    market_value: int
    market_value_date: date
    already_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "industry": self.industry,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "market_value": self.market_value,
            "market_value_date": self.market_value_date.isoformat(),
            "already_complete": self.already_complete,
        }


class FinMindApiClient:
    """Small secret-safe client for the two endpoints used by the downloader."""

    def __init__(self, token: str, *, timeout_seconds: float = 30.0) -> None:
        if not token.strip():
            raise ValueError("FINMIND_API_TOKEN is missing")
        self._token = token.strip()
        self._timeout_seconds = timeout_seconds

    def usage(self) -> FinMindUsage:
        response = self._request(USAGE_ENDPOINT, {})
        payload = response.payload
        if response.http_status != 200 or not isinstance(payload, Mapping):
            raise FinMindRequestError(
                f"FinMind usage endpoint returned HTTP {response.http_status}",
                response=response,
            )
        try:
            user_count = int(payload["user_count"])
            api_request_limit = int(payload["api_request_limit"])
        except (KeyError, TypeError, ValueError) as error:
            raise FinMindRequestError(
                "FinMind usage response is missing user_count/api_request_limit",
                response=response,
            ) from error
        if user_count < 0 or api_request_limit <= 0:
            raise FinMindRequestError("FinMind usage response contains invalid counts")
        return FinMindUsage(user_count=user_count, api_request_limit=api_request_limit)

    def data(
        self,
        *,
        dataset: str,
        data_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> FinMindResponse:
        query = {"dataset": dataset}
        if data_id is not None:
            query["data_id"] = data_id
        if start_date is not None:
            query["start_date"] = start_date.isoformat()
        if end_date is not None:
            if start_date is None:
                raise ValueError("end_date requires start_date")
            query["end_date"] = end_date.isoformat()
        response = self._request(DATA_ENDPOINT, query)
        payload = response.payload
        payload_status = payload.get("status") if isinstance(payload, Mapping) else None
        message = payload.get("msg") if isinstance(payload, Mapping) else None
        if response.http_status == 402 or payload_status == 402:
            raise FinMindQuotaReached(
                str(message or "FinMind request allowance reached"),
                response=response,
            )
        if response.http_status != 200 or payload_status != 200:
            raise FinMindRequestError(
                f"FinMind data request failed: HTTP {response.http_status}; status={payload_status}; msg={message}",
                response=response,
            )
        if not isinstance(payload.get("data"), list):
            raise FinMindRequestError(
                "FinMind data response does not contain an array",
                response=response,
            )
        return response

    def _request(self, endpoint: str, query: Mapping[str, str]) -> FinMindResponse:
        url = endpoint
        if query:
            url = f"{endpoint}?{urlencode(query)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "tw-intraday-trader-finmind-history/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                status = int(response.status)
                body = response.read()
        except HTTPError as error:
            status = int(error.code)
            body = error.read()
        except URLError as error:
            raise FinMindRequestError(
                f"FinMind transport failed: {error.reason}"
            ) from error
        try:
            decoded = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        payload = decoded if isinstance(decoded, Mapping) else None
        return FinMindResponse(http_status=status, body=body, payload=payload)


_NON_COMPANY_INDUSTRIES = {
    "ETF",
    "ETN",
    "Index",
    "大盤",
    "存託憑證",
    "受益證券",
    "創新板股票",
}
_AGGREGATE_INDUSTRIES = {"電子工業", "化學生技醫療", "創新板股票"}


def select_industry_market_value_leaders(
    *,
    stock_info_response: FinMindResponse,
    market_value_response: FinMindResponse,
    already_complete_symbols: Sequence[str] = (),
) -> tuple[FinMindIndustryLeader, ...]:
    """Select the latest market-value leader for each current listed industry."""

    info_rows = _payload_rows(stock_info_response, "TaiwanStockInfo")
    market_value_rows = _payload_rows(
        market_value_response, "TaiwanStockMarketValue"
    )
    grouped_info: dict[str, list[tuple[date, str, str, str]]] = {}
    for row in info_rows:
        symbol = str(row.get("stock_id") or "").strip().upper()
        market = str(row.get("type") or "").strip().lower()
        industry = str(row.get("industry_category") or "").strip()
        name = str(row.get("stock_name") or "").strip()
        if not symbol or not industry or not name:
            continue
        try:
            observed_date = date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        grouped_info.setdefault(symbol, []).append(
            (observed_date, market, industry, name)
        )

    current_info: dict[str, tuple[date, str, str, str]] = {}
    for symbol, observations in grouped_info.items():
        latest_date = max(item[0] for item in observations)
        latest_active = {
            item
            for item in observations
            if item[0] == latest_date and item[1] in {"twse", "tpex"}
        }
        identities = {(item[1], item[3]) for item in latest_active}
        if len(identities) != 1:
            continue
        industries = {item[2] for item in latest_active}
        specific_industries = industries - _AGGREGATE_INDUSTRIES
        if len(specific_industries) == 1:
            industry = specific_industries.pop()
        elif len(industries) == 1:
            industry = industries.pop()
        else:
            continue
        market, name = identities.pop()
        current_info[symbol] = (latest_date, market, industry, name)

    try:
        market_value_date = max(
            date.fromisoformat(str(row.get("date"))) for row in market_value_rows
        )
    except (ValueError, TypeError) as error:
        raise ValueError("TaiwanStockMarketValue contains an invalid date") from error

    values: dict[str, int] = {}
    for row in market_value_rows:
        if date.fromisoformat(str(row.get("date"))) != market_value_date:
            continue
        symbol = str(row.get("stock_id") or "").strip().upper()
        parsed = _finite_decimal(row.get("market_value"), "market_value")
        if parsed <= 0:
            continue
        if parsed != parsed.to_integral_value():
            raise ValueError("TaiwanStockMarketValue must be an integer")
        if symbol in values:
            raise ValueError(
                f"TaiwanStockMarketValue contains duplicate rows for {symbol}"
            )
        values[symbol] = int(parsed)

    completed = {symbol.strip().upper() for symbol in already_complete_symbols}
    leaders: dict[str, FinMindIndustryLeader] = {}
    for symbol, market_value in values.items():
        info = current_info.get(symbol)
        if info is None:
            continue
        _, market, industry, name = info
        if market not in {"twse", "tpex"}:
            continue
        if industry in _NON_COMPANY_INDUSTRIES:
            continue
        if len(symbol) != 4 or not symbol.isdigit():
            continue
        candidate = FinMindIndustryLeader(
            industry=industry,
            symbol=symbol,
            name=name,
            market=market,
            market_value=market_value,
            market_value_date=market_value_date,
            already_complete=symbol in completed,
        )
        existing = leaders.get(industry)
        if existing is None or (-market_value, symbol) < (
            -existing.market_value,
            existing.symbol,
        ):
            leaders[industry] = candidate
    if not leaders:
        raise ValueError("No listed industry leaders could be selected")
    return tuple(sorted(leaders.values(), key=lambda item: item.industry))


def _payload_rows(
    response: FinMindResponse, dataset: str
) -> list[Mapping[str, Any]]:
    payload = response.payload or {}
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{dataset} response contains no rows")
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"{dataset} response contains a non-object row")
    return rows


def trading_dates_from_response(
    response: FinMindResponse,
    *,
    start_date: date,
    end_date: date,
) -> tuple[date, ...]:
    payload = response.payload or {}
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("FinMind calendar response does not contain data rows")
    dates: set[date] = set()
    for row in rows:
        if not isinstance(row, Mapping) or "date" not in row:
            raise ValueError("FinMind calendar row is missing date")
        observed = date.fromisoformat(str(row["date"]))
        if not start_date <= observed <= end_date:
            raise ValueError("FinMind calendar response contains an out-of-range date")
        dates.add(observed)
    if not dates:
        raise ValueError("FinMind calendar response is empty")
    return tuple(sorted(dates))


def normalize_kbar_response(
    response: FinMindResponse,
    *,
    symbol: str,
    session_date: date,
    name: str = "",
    market: str = "",
) -> tuple[HistoricalBar, ...]:
    """Validate raw rows and convert start labels to observable event times."""

    payload = response.payload or {}
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("FinMind KBar response does not contain data rows")
    bars: list[HistoricalBar] = []
    raw_labels: set[datetime] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("FinMind KBar row must be an object")
        if str(row.get("stock_id") or "") != symbol:
            raise ValueError("FinMind KBar row symbol does not match the request")
        if date.fromisoformat(str(row.get("date"))) != session_date:
            raise ValueError("FinMind KBar row date does not match the request")
        raw_label = datetime.fromisoformat(
            f"{session_date.isoformat()}T{row.get('minute')}"
        ).replace(tzinfo=TAIPEI)
        raw_time = raw_label.timetz().replace(tzinfo=None)
        if not (REGULAR_OPEN <= raw_time <= REGULAR_CLOSE or raw_time == DELAYED_CLOSE):
            raise ValueError("FinMind KBar row is outside the regular session")
        if raw_label in raw_labels:
            raise ValueError("FinMind KBar response contains duplicate minute labels")
        raw_labels.add(raw_label)
        event_time = (
            raw_label
            if raw_time in {REGULAR_CLOSE, DELAYED_CLOSE}
            else raw_label + timedelta(minutes=1)
        )
        prices = tuple(_finite_decimal(row.get(field), field) for field in ("open", "high", "low", "close"))
        volume = _integral_volume(row.get("volume"))
        bar = HistoricalBar(
            symbol=symbol,
            name=name,
            market=market,
            timestamp=event_time,
            open=prices[0],
            high=prices[1],
            low=prices[2],
            close=prices[3],
            volume=volume,
            amount=prices[3] * volume,
            session_date=session_date,
        )
        bars.append(bar)
    ordered = tuple(sorted(bars, key=lambda bar: bar.timestamp))
    if len({bar.timestamp for bar in ordered}) != len(ordered):
        raise ValueError("FinMind normalized KBar timestamps are not unique")
    return ordered


def _finite_decimal(value: object, field: str) -> Decimal:
    try:
        parsed = decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"FinMind KBar {field} is not numeric") from error
    if not parsed.is_finite():
        raise ValueError(f"FinMind KBar {field} must be finite")
    return parsed


def _integral_volume(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("FinMind KBar volume must be an integer")
    parsed = _finite_decimal(value, "volume")
    if parsed != parsed.to_integral_value():
        raise ValueError("FinMind KBar volume must be an integer")
    volume = int(parsed)
    if volume < 0:
        raise ValueError("FinMind KBar volume cannot be negative")
    return volume


class FinMindHistoryStore:
    """Dedicated SQLite acquisition store; it is not the backtest authority."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def ensure_job(
        self,
        *,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        calendar_symbol: str,
    ) -> str:
        selected = tuple(sorted({item.strip().upper() for item in symbols if item.strip()}))
        if not selected:
            raise ValueError("At least one symbol is required")
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")
        config = {
            "calendar_symbol": calendar_symbol.strip().upper(),
            "end_date": end_date.isoformat(),
            "source": SOURCE,
            "start_date": start_date.isoformat(),
            "symbols": list(selected),
        }
        job_id = f"finmind-sponsor-{hashlib.sha256(canonical_json(config).encode()).hexdigest()[:16]}"
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO finmind_history_jobs (
                    job_id, source, source_version, start_date, end_date,
                    symbols_json, calendar_symbol, volume_unit, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?)
                """,
                (
                    job_id,
                    SOURCE,
                    SOURCE_VERSION,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    canonical_json(list(selected)),
                    config["calendar_symbol"],
                    VOLUME_UNIT,
                    now,
                    now,
                ),
            )
        job = self.get_job(job_id)
        if (
            job["start_date"] != start_date.isoformat()
            or job["end_date"] != end_date.isoformat()
            or tuple(json.loads(job["symbols_json"])) != selected
            or job["calendar_symbol"] != config["calendar_symbol"]
        ):
            raise ValueError("Existing FinMind job configuration does not match")
        return job_id

    def get_job(self, job_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM finmind_history_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown FinMind history job: {job_id}")
        return row

    def calendar_dates(self, job_id: str) -> tuple[date, ...]:
        raw = self.get_job(job_id)["trading_dates_json"]
        if raw is None:
            return ()
        return tuple(date.fromisoformat(value) for value in json.loads(raw))

    def save_calendar(
        self,
        job_id: str,
        *,
        response: FinMindResponse,
        dates: Sequence[date],
    ) -> None:
        raw_sha256 = hashlib.sha256(response.body).hexdigest()
        encoded_dates = canonical_json([value.isoformat() for value in dates])
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            row = self.get_job(job_id)
            existing = row["trading_dates_json"]
            if existing is not None and existing != encoded_dates:
                raise ValueError("FinMind job calendar is immutable")
            self._connection.execute(
                """
                UPDATE finmind_history_jobs
                SET trading_dates_json = ?, calendar_raw_sha256 = ?,
                    calendar_raw_payload = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    encoded_dates,
                    raw_sha256,
                    gzip.compress(response.body, mtime=0),
                    now,
                    job_id,
                ),
            )
            self._insert_attempt(
                job_id=job_id,
                request_kind="CALENDAR",
                symbol=row["calendar_symbol"],
                session_date=None,
                response=response,
                outcome="READY",
                error_message=None,
            )

    def save_partition(
        self,
        job_id: str,
        *,
        symbol: str,
        session_date: date,
        response: FinMindResponse,
        bars: Sequence[HistoricalBar],
        status: str,
        error_message: str | None = None,
    ) -> None:
        if status not in {"READY", "EMPTY", "INVALID"}:
            raise ValueError("Unsupported FinMind partition status")
        canonical_payload = canonical_json([bar.to_dict() for bar in bars]).encode()
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO finmind_history_partitions (
                    job_id, symbol, session_date, status, bar_count,
                    first_event_at, last_event_at, raw_sha256, raw_payload,
                    canonical_sha256, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, symbol, session_date) DO NOTHING
                """,
                (
                    job_id,
                    symbol,
                    session_date.isoformat(),
                    status,
                    len(bars),
                    bars[0].timestamp.isoformat() if bars else None,
                    bars[-1].timestamp.isoformat() if bars else None,
                    hashlib.sha256(response.body).hexdigest(),
                    gzip.compress(response.body, mtime=0),
                    hashlib.sha256(canonical_payload).hexdigest(),
                    error_message,
                    now,
                    now,
                ),
            )
            self._insert_attempt(
                job_id=job_id,
                request_kind="KBAR",
                symbol=symbol,
                session_date=session_date,
                response=response,
                outcome=status,
                error_message=error_message,
            )

    def save_failed_attempt(
        self,
        job_id: str,
        *,
        request_kind: str,
        symbol: str,
        session_date: date | None,
        error: FinMindRequestError,
    ) -> None:
        with self._connection:
            self._insert_attempt(
                job_id=job_id,
                request_kind=request_kind,
                symbol=symbol,
                session_date=session_date,
                response=error.response,
                outcome="FAILED",
                error_message=str(error),
            )

    def next_pending(self, job_id: str) -> tuple[str, date] | None:
        job = self.get_job(job_id)
        dates = self.calendar_dates(job_id)
        if not dates:
            return None
        for symbol in json.loads(job["symbols_json"]):
            completed = {
                date.fromisoformat(row["session_date"])
                for row in self._connection.execute(
                    """
                    SELECT session_date FROM finmind_history_partitions
                    WHERE job_id = ? AND symbol = ?
                    """,
                    (job_id, symbol),
                )
            }
            for session_date in dates:
                if session_date not in completed:
                    return str(symbol), session_date
        return None

    def set_status(self, job_id: str, status: str, message: str | None = None) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE finmind_history_jobs
                SET status = ?, status_message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, message, datetime.now(TAIPEI).isoformat(), job_id),
            )

    def summary(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        dates = self.calendar_dates(job_id)
        symbols = tuple(json.loads(job["symbols_json"]))
        counts = {
            row["status"]: int(row["count"])
            for row in self._connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM finmind_history_partitions
                WHERE job_id = ? GROUP BY status
                """,
                (job_id,),
            )
        }
        attempts = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM finmind_history_attempts WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
        )
        total = len(symbols) * len(dates)
        completed = sum(counts.values())
        return {
            "job_id": job_id,
            "status": job["status"],
            "status_message": job["status_message"],
            "source": job["source"],
            "source_version": job["source_version"],
            "volume_unit": job["volume_unit"],
            "start_date": job["start_date"],
            "end_date": job["end_date"],
            "symbols": list(symbols),
            "trading_date_count": len(dates),
            "expected_symbol_days": total,
            "checkpointed_symbol_days": completed,
            "remaining_symbol_days": max(0, total - completed),
            "partition_status_counts": counts,
            "recorded_data_requests": attempts,
            "next_pending": (
                {
                    "symbol": pending[0],
                    "session_date": pending[1].isoformat(),
                }
                if (pending := self.next_pending(job_id)) is not None
                else None
            ),
        }

    def reconcile_completion(self, job_id: str) -> dict[str, Any]:
        """Derive the terminal job state from durable partition counts."""

        summary = self.summary(job_id)
        if summary["trading_date_count"] == 0:
            if summary["status"] == "COMPLETED":
                self.set_status(job_id, "QUEUED", "Trading calendar not acquired")
                summary = self.summary(job_id)
            return summary
        if summary["remaining_symbol_days"] != 0:
            return summary
        invalid = summary["partition_status_counts"].get("INVALID", 0)
        if invalid:
            self.set_status(
                job_id,
                "BLOCKED_DATA_QUALITY",
                f"{invalid} invalid symbol-day partitions require review",
            )
        else:
            self.set_status(job_id, "COMPLETED", "All symbol-days checkpointed")
        return self.summary(job_id)

    def load_partition_bars(
        self, job_id: str, symbol: str, session_date: date
    ) -> tuple[HistoricalBar, ...]:
        row = self._connection.execute(
            """
            SELECT raw_sha256, raw_payload, canonical_sha256
            FROM finmind_history_partitions
            WHERE job_id = ? AND symbol = ? AND session_date = ?
            """,
            (job_id, symbol, session_date.isoformat()),
        ).fetchone()
        if row is None:
            raise KeyError("FinMind history partition not found")
        body = gzip.decompress(bytes(row["raw_payload"]))
        if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
            raise ValueError("FinMind raw partition digest mismatch")
        payload = json.loads(body)
        response = FinMindResponse(http_status=200, body=body, payload=payload)
        bars = normalize_kbar_response(
            response, symbol=symbol, session_date=session_date
        )
        canonical_payload = canonical_json([bar.to_dict() for bar in bars]).encode()
        if hashlib.sha256(canonical_payload).hexdigest() != row["canonical_sha256"]:
            raise ValueError("FinMind canonical partition digest mismatch")
        return bars

    def audit(self, job_id: str) -> dict[str, Any]:
        """Re-read raw bytes and verify every checkpointed partition offline."""

        rows = self._connection.execute(
            """
            SELECT symbol, session_date, status, bar_count,
                   first_event_at, last_event_at
            FROM finmind_history_partitions
            WHERE job_id = ?
            ORDER BY symbol, session_date
            """,
            (job_id,),
        ).fetchall()
        verified = 0
        total_bars = 0
        issues: list[str] = []
        first_event_at: str | None = None
        last_event_at: str | None = None
        for row in rows:
            symbol = str(row["symbol"])
            session_date = date.fromisoformat(str(row["session_date"]))
            try:
                bars = self.load_partition_bars(job_id, symbol, session_date)
                if len(bars) != int(row["bar_count"]):
                    raise ValueError("stored bar_count mismatch")
                observed_first = bars[0].timestamp.isoformat() if bars else None
                observed_last = bars[-1].timestamp.isoformat() if bars else None
                if observed_first != row["first_event_at"]:
                    raise ValueError("stored first_event_at mismatch")
                if observed_last != row["last_event_at"]:
                    raise ValueError("stored last_event_at mismatch")
                if any(bar.session_date != session_date for bar in bars):
                    raise ValueError("canonical session_date mismatch")
            except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
                issues.append(f"{symbol}/{session_date.isoformat()}: {error}")
                continue
            verified += 1
            total_bars += len(bars)
            if observed_first is not None:
                first_event_at = min(first_event_at, observed_first) if first_event_at else observed_first
            if observed_last is not None:
                last_event_at = max(last_event_at, observed_last) if last_event_at else observed_last
        return {
            "job_id": job_id,
            "checkpointed_partitions": len(rows),
            "verified_partitions": verified,
            "total_bars": total_bars,
            "first_event_at": first_event_at,
            "last_event_at": last_event_at,
            "issue_count": len(issues),
            "issues": issues[:20],
        }

    def revalidate_invalid(self, job_id: str) -> dict[str, Any]:
        """Reclassify stored INVALID responses after a reviewed contract change."""

        rows = self._connection.execute(
            """
            SELECT symbol, session_date, raw_sha256, raw_payload
            FROM finmind_history_partitions
            WHERE job_id = ? AND status = 'INVALID'
            ORDER BY symbol, session_date
            """,
            (job_id,),
        ).fetchall()
        repaired = 0
        issues: list[str] = []
        for row in rows:
            symbol = str(row["symbol"])
            session_date = date.fromisoformat(str(row["session_date"]))
            try:
                body = gzip.decompress(bytes(row["raw_payload"]))
                if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
                    raise ValueError("FinMind raw partition digest mismatch")
                payload = json.loads(body)
                bars = normalize_kbar_response(
                    FinMindResponse(http_status=200, body=body, payload=payload),
                    symbol=symbol,
                    session_date=session_date,
                )
                canonical_payload = canonical_json(
                    [bar.to_dict() for bar in bars]
                ).encode()
            except (OSError, ValueError, json.JSONDecodeError) as error:
                issues.append(f"{symbol}/{session_date.isoformat()}: {error}")
                continue
            with self._connection:
                self._connection.execute(
                    """
                    UPDATE finmind_history_partitions
                    SET status = ?, bar_count = ?, first_event_at = ?,
                        last_event_at = ?, canonical_sha256 = ?,
                        error_message = NULL, updated_at = ?
                    WHERE job_id = ? AND symbol = ? AND session_date = ?
                      AND status = 'INVALID'
                    """,
                    (
                        "READY" if bars else "EMPTY",
                        len(bars),
                        bars[0].timestamp.isoformat() if bars else None,
                        bars[-1].timestamp.isoformat() if bars else None,
                        hashlib.sha256(canonical_payload).hexdigest(),
                        datetime.now(TAIPEI).isoformat(),
                        job_id,
                        symbol,
                        session_date.isoformat(),
                    ),
                )
            repaired += 1
        if repaired:
            self.set_status(job_id, "PAUSED", "Stored invalid partitions revalidated")
        return {
            "job_id": job_id,
            "invalid_partitions": len(rows),
            "repaired_partitions": repaired,
            "issue_count": len(issues),
            "issues": issues[:20],
        }

    def _insert_attempt(
        self,
        *,
        job_id: str,
        request_kind: str,
        symbol: str,
        session_date: date | None,
        response: FinMindResponse | None,
        outcome: str,
        error_message: str | None,
    ) -> None:
        payload_status = (
            response.payload.get("status")
            if response is not None and isinstance(response.payload, Mapping)
            else None
        )
        self._connection.execute(
            """
            INSERT INTO finmind_history_attempts (
                job_id, request_kind, symbol, session_date, requested_at,
                http_status, payload_status, outcome, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                request_kind,
                symbol,
                session_date.isoformat() if session_date is not None else None,
                datetime.now(TAIPEI).isoformat(),
                response.http_status if response is not None else None,
                int(payload_status) if payload_status is not None else None,
                outcome,
                error_message,
            ),
        )


class FinMindSponsorDownloader:
    def __init__(
        self,
        *,
        client: FinMindApiClient,
        store: FinMindHistoryStore,
        report: Callable[[str], None] | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._client = client
        self._store = store
        self._report = report or (lambda _message: None)
        self._sleeper = sleeper

    def run(
        self,
        job_id: str,
        *,
        max_requests: int,
        reserve_requests: int,
        pace_seconds: float,
    ) -> dict[str, Any]:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if reserve_requests < 0:
            raise ValueError("reserve_requests cannot be negative")
        if pace_seconds < 0:
            raise ValueError("pace_seconds cannot be negative")
        job = self._store.get_job(job_id)
        usage = self._client.usage()
        allowance = min(max_requests, max(0, usage.remaining - reserve_requests))
        if allowance == 0:
            self._store.set_status(job_id, "PAUSED", "FinMind allowance reserve reached")
            return self._with_usage(self._store.summary(job_id), usage, 0)

        spent = 0
        self._store.set_status(job_id, "RUNNING", None)
        try:
            if not self._store.calendar_dates(job_id):
                response = self._client.data(
                    dataset="TaiwanStockPrice",
                    data_id=str(job["calendar_symbol"]),
                    start_date=date.fromisoformat(job["start_date"]),
                    end_date=date.fromisoformat(job["end_date"]),
                )
                spent += 1
                dates = trading_dates_from_response(
                    response,
                    start_date=date.fromisoformat(job["start_date"]),
                    end_date=date.fromisoformat(job["end_date"]),
                )
                self._store.save_calendar(job_id, response=response, dates=dates)
                self._report(f"已封存交易日曆：{len(dates)} 個交易日")
                if spent < allowance and pace_seconds:
                    self._sleeper(pace_seconds)

            while spent < allowance:
                pending = self._store.next_pending(job_id)
                if pending is None:
                    current = self._store.summary(job_id)
                    invalid = current["partition_status_counts"].get("INVALID", 0)
                    if invalid:
                        self._store.set_status(
                            job_id,
                            "BLOCKED_DATA_QUALITY",
                            f"{invalid} invalid symbol-day partitions require review",
                        )
                    else:
                        self._store.set_status(
                            job_id, "COMPLETED", "All symbol-days checkpointed"
                        )
                    break
                symbol, session_date = pending
                response = self._client.data(
                    dataset="TaiwanStockKBar",
                    data_id=symbol,
                    start_date=session_date,
                )
                spent += 1
                try:
                    bars = normalize_kbar_response(
                        response,
                        symbol=symbol,
                        session_date=session_date,
                    )
                except ValueError as error:
                    self._store.save_partition(
                        job_id,
                        symbol=symbol,
                        session_date=session_date,
                        response=response,
                        bars=(),
                        status="INVALID",
                        error_message=str(error),
                    )
                    self._store.set_status(job_id, "PAUSED", str(error))
                    raise
                status = "READY" if bars else "EMPTY"
                self._store.save_partition(
                    job_id,
                    symbol=symbol,
                    session_date=session_date,
                    response=response,
                    bars=bars,
                    status=status,
                )
                if spent == 1 or spent % 10 == 0:
                    self._report(
                        f"本批已使用 {spent}/{allowance} requests；"
                        f"{symbol} {session_date.isoformat()} {status} {len(bars)} bars"
                    )
                if spent < allowance and pace_seconds:
                    self._sleeper(pace_seconds)
        except FinMindRequestError as error:
            pending = self._store.next_pending(job_id)
            self._store.save_failed_attempt(
                job_id,
                request_kind="KBAR" if self._store.calendar_dates(job_id) else "CALENDAR",
                symbol=pending[0] if pending is not None else str(job["calendar_symbol"]),
                session_date=pending[1] if pending is not None else None,
                error=error,
            )
            self._store.set_status(job_id, "PAUSED", str(error))
            summary = self._with_usage(self._store.summary(job_id), usage, spent)
            summary["stop_reason"] = str(error)
            summary["stop_kind"] = (
                "QUOTA" if isinstance(error, FinMindQuotaReached) else "PROVIDER"
            )
            return summary

        summary = self._store.reconcile_completion(job_id)
        if summary["status"] == "RUNNING":
            self._store.set_status(job_id, "PAUSED", "Batch request budget reached")
            summary = self._store.summary(job_id)
        return self._with_usage(summary, usage, spent)

    @staticmethod
    def _with_usage(
        summary: dict[str, Any], usage: FinMindUsage, spent: int
    ) -> dict[str, Any]:
        return {
            **summary,
            "batch_requests_spent": spent,
            "quota_before": {
                "user_count": usage.user_count,
                "api_request_limit": usage.api_request_limit,
                "remaining": usage.remaining,
            },
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS finmind_history_jobs (
    job_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    calendar_symbol TEXT NOT NULL,
    trading_dates_json TEXT NULL,
    calendar_raw_sha256 TEXT NULL,
    calendar_raw_payload BLOB NULL,
    volume_unit TEXT NOT NULL,
    status TEXT NOT NULL,
    status_message TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS finmind_history_partitions (
    job_id TEXT NOT NULL REFERENCES finmind_history_jobs(job_id),
    symbol TEXT NOT NULL,
    session_date TEXT NOT NULL,
    status TEXT NOT NULL,
    bar_count INTEGER NOT NULL,
    first_event_at TEXT NULL,
    last_event_at TEXT NULL,
    raw_sha256 TEXT NOT NULL,
    raw_payload BLOB NOT NULL,
    canonical_sha256 TEXT NOT NULL,
    error_message TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (job_id, symbol, session_date)
);
CREATE TABLE IF NOT EXISTS finmind_history_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES finmind_history_jobs(job_id),
    request_kind TEXT NOT NULL,
    symbol TEXT NOT NULL,
    session_date TEXT NULL,
    requested_at TEXT NOT NULL,
    http_status INTEGER NULL,
    payload_status INTEGER NULL,
    outcome TEXT NOT NULL,
    error_message TEXT NULL
);
CREATE INDEX IF NOT EXISTS finmind_history_partitions_job_symbol
ON finmind_history_partitions (job_id, symbol, session_date);
CREATE INDEX IF NOT EXISTS finmind_history_attempts_job
ON finmind_history_attempts (job_id, attempt_id);
"""
