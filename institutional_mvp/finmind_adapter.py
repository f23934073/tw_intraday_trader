"""FinMind infrastructure adapter for the bounded institutional MVP datasets."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path

from backtest.finmind_history import (
    FinMindApiClient,
    FinMindQuotaReached,
    FinMindRequestError,
)
from institutional_mvp.domain import (
    InstitutionalMvpDailyError,
    InstitutionalMvpSourceNotReady,
)
from institutional_mvp.ports import InstitutionalFlowSnapshot


FLOW_DATASET = "TaiwanStockInstitutionalInvestorsBuySellWide"
STOCK_INFO_DATASET = "TaiwanStockInfo"
SOURCE_VERSION = "FINMIND_API_V4"


class FinMindInstitutionalFlowProvider:
    """Fetch exactly the two allowlisted payloads after a secret-safe preflight."""

    def __init__(
        self,
        token: str,
        *,
        minimum_remaining_after_batch: int,
        acquisition_lock_path: Path,
        client_factory: Callable[[str], FinMindApiClient] = FinMindApiClient,
        clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        if not token.strip():
            raise ValueError("FINMIND_API_TOKEN is missing")
        if (
            isinstance(minimum_remaining_after_batch, bool)
            or minimum_remaining_after_batch < 0
        ):
            raise ValueError("minimum_remaining_after_batch must be non-negative")
        self._client = client_factory(token.strip())
        self._minimum_remaining_after_batch = minimum_remaining_after_batch
        self._acquisition_lock_path = Path(acquisition_lock_path)
        self._clock = clock

    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        self._acquisition_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._acquisition_lock_path.open("a+b") as lock_file:
            os.chmod(self._acquisition_lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return self._fetch_daily_locked(source_session)

    def _fetch_daily_locked(self, source_session: date) -> InstitutionalFlowSnapshot:
        try:
            usage = self._client.usage()
        except (FinMindQuotaReached, FinMindRequestError) as error:
            code = _request_failure_code(
                error,
                quota_code="PROVIDER_QUOTA_REACHED",
                default_code="PROVIDER_PREFLIGHT_FAILED",
            )
            raise InstitutionalMvpDailyError(
                code, "FinMind usage preflight failed"
            ) from error
        required = 2 + self._minimum_remaining_after_batch
        if usage.remaining < required:
            raise InstitutionalMvpDailyError(
                "PROVIDER_QUOTA_INSUFFICIENT",
                "FinMind quota is insufficient; no data request was sent",
            )

        try:
            wide = self._client.data(
                dataset=FLOW_DATASET,
                start_date=source_session,
            )
            wide_row_count = _row_count(wide.payload, FLOW_DATASET)
            if wide_row_count == 0:
                raise InstitutionalMvpSourceNotReady()
            stock_info = self._client.data(dataset=STOCK_INFO_DATASET)
        except FinMindQuotaReached as error:
            raise InstitutionalMvpDailyError(
                "PROVIDER_QUOTA_REACHED", "FinMind quota was reached during acquisition"
            ) from error
        except FinMindRequestError as error:
            code = _request_failure_code(
                error,
                quota_code="PROVIDER_QUOTA_REACHED",
                default_code="PROVIDER_REQUEST_FAILED",
            )
            raise InstitutionalMvpDailyError(
                code, "FinMind institutional acquisition failed"
            ) from error

        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("provider clock must return a timezone-aware datetime")
        return InstitutionalFlowSnapshot(
            provider="FINMIND",
            source_version=SOURCE_VERSION,
            retrieved_at=retrieved_at,
            wide_payload=wide.body,
            stock_info_payload=stock_info.body,
            wide_row_count=wide_row_count,
            stock_info_row_count=_row_count(stock_info.payload, STOCK_INFO_DATASET),
            usage_user_count_before=usage.user_count,
            usage_request_limit=usage.api_request_limit,
            usage_remaining_before=usage.remaining,
        )


def _row_count(payload: Mapping[str, object] | None, dataset: str) -> int:
    if not isinstance(payload, Mapping):
        raise InstitutionalMvpDailyError(
            "SOURCE_SCHEMA_INVALID", f"{dataset} response envelope is invalid"
        )
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise InstitutionalMvpDailyError(
            "SOURCE_SCHEMA_INVALID", f"{dataset} response rows are invalid"
        )
    return len(rows)


def _request_failure_code(
    error: FinMindRequestError,
    *,
    quota_code: str,
    default_code: str,
) -> str:
    response = error.response
    if response is None:
        return default_code
    status = response.http_status
    if status == 200 and isinstance(response.payload, Mapping):
        payload_status = response.payload.get("status")
        if isinstance(payload_status, int) and not isinstance(payload_status, bool):
            status = payload_status
    if status == 402:
        return quota_code
    if status in {408, 429} or status >= 500:
        return default_code
    if status in {401, 403}:
        return "PROVIDER_ACCESS_DENIED"
    if 400 <= status < 500:
        return "PROVIDER_REQUEST_REJECTED"
    if response.http_status == 200:
        return "PROVIDER_RESPONSE_INVALID"
    return default_code
