#!/usr/bin/env python3
"""Execute and monitor the one authorized R5 control without external providers."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from time import monotonic, sleep
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.application import BacktestApplicationService
from backtest.domain import RunStatus
from market_data.provider import MockProvider


BASELINE_RUN_ID = "run-91ad87981676414da87b928398fa43c9"
PREFLIGHT_DIGEST = "fc6a682dafc831bd15234bcf75c68d6a715c9dbd90a8a78bdc1075b405bb2879"
IDEMPOTENCY_KEY = "r5-vwap-cash-admission-control-v1-fc6a682dafc8"
ACTOR_ID = "local-researcher"
CHANGE_NOTE = (
    "Execute approved R5 cash-admission-neutral sensitivity control after "
    "schema-v2 preflight remediation review"
)
TERMINAL_STATUSES = {
    RunStatus.COMPLETED.value,
    RunStatus.INVALID_CASH_ADMISSION_CONTROL.value,
    RunStatus.CANCELLED.value,
    RunStatus.FAILED.value,
}


def _event(name: str, **values: Any) -> None:
    print(
        json.dumps(
            {"event": name, **values},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
        flush=True,
    )


class ProviderCallBlocker(MockProvider):
    """Make any accidental market-data read observable and fail closed."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def _deny(self, operation: str) -> None:
        self.calls.append(operation)
        raise RuntimeError(f"R5_PROVIDER_CALL_PROHIBITED:{operation}")

    def get_stock(self, symbol: str):  # type: ignore[no-untyped-def]
        self._deny("get_stock")

    def get_stock_identity(self, symbol: str):  # type: ignore[no-untyped-def]
        self._deny("get_stock_identity")

    def get_market_stocks(self):  # type: ignore[no-untyped-def]
        self._deny("get_market_stocks")

    def get_kbars(self, symbol, start, end):  # type: ignore[no-untyped-def]
        self._deny("get_kbars")

    def get_taifex_night_session(self, window, contract_alias):  # type: ignore[no-untyped-def]
        self._deny("get_taifex_night_session")


def _shutdown_without_global_cancellation(service: BacktestApplicationService) -> None:
    """Release only this process's worker/pool; never mutate other durable Runs."""

    service._closed = True  # noqa: SLF001 - isolated operations harness
    service._executor.shutdown(wait=True, cancel_futures=False)  # noqa: SLF001
    close = getattr(service._repository, "close", None)  # noqa: SLF001
    if callable(close):
        close()


def main() -> int:
    provider = ProviderCallBlocker()
    service = BacktestApplicationService(provider, workers=1)
    run_id: str | None = None
    try:
        run, idempotent = service.create_cash_admission_control(
            baseline_run_id=BASELINE_RUN_ID,
            request_schema_version="cash-admission-control-request-v1",
            control_contract_version="cash-admission-control-v1",
            preflight_digest=PREFLIGHT_DIGEST,
            expected_registration_revision=0,
            idempotency_key=IDEMPOTENCY_KEY,
            actor_id=ACTOR_ID,
            change_note=CHANGE_NOTE,
        )
        run_id = str(run["run_id"])
        _event(
            "R5_CONTROL_CREATED",
            run_id=run_id,
            idempotent=idempotent,
            status=run["status"],
            config_digest=run["config_digest"],
            dataset_id=run["dataset_id"],
            dataset_digest=run["dataset_digest"],
            registration=run.get("cash_admission_control"),
        )

        last_status: str | None = None
        last_emit = 0.0
        while True:
            current = service.get_run(run_id)
            status = str(current["status"])
            now = monotonic()
            if status != last_status or now - last_emit >= 30.0:
                _event(
                    "R5_CONTROL_PROGRESS",
                    run_id=run_id,
                    status=status,
                    progress=current.get("progress"),
                    progress_message=current.get("progress_message"),
                    error_message=current.get("error_message"),
                    result_digest=current.get("result_digest"),
                )
                last_status = status
                last_emit = now
            if status in TERMINAL_STATUSES:
                break
            sleep(5.0)

        registration = service._repository.get_cash_admission_control(run_id)  # noqa: SLF001
        summary = service.summary(run_id) if status == RunStatus.COMPLETED.value else None
        _event(
            "R5_CONTROL_TERMINAL",
            run_id=run_id,
            status=status,
            registration=registration,
            summary=summary,
            provider_calls=provider.calls,
        )
        if status == RunStatus.COMPLETED.value:
            return 0
        if status == RunStatus.INVALID_CASH_ADMISSION_CONTROL.value:
            return 2
        return 1
    finally:
        _event("R5_PROVIDER_AUDIT", run_id=run_id, provider_calls=provider.calls)
        _shutdown_without_global_cancellation(service)


if __name__ == "__main__":
    raise SystemExit(main())
