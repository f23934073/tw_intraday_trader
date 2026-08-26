from __future__ import annotations

import sys

import pytest

from scripts import download_backtest_history


class _PreparedRepository:
    def __init__(self, *, kind: str, lineage_mode: str | None) -> None:
        self.closed = False
        self.kind = kind
        self.lineage_mode = lineage_mode

    def get_job(self, job_id: str) -> dict[str, object]:
        return {
            "job_id": job_id,
            "kind": self.kind,
            "request": {"lineage_mode": self.lineage_mode},
        }

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("kind", "lineage_mode"),
    [
        ("PRICE_COVERAGE_PREPARED", None),
        ("DATASET_DOWNLOAD", "FRESH_R3_NO_CHECKPOINT_REUSE"),
    ],
)
def test_generic_cli_rejects_prepared_r3_before_provider_build(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    lineage_mode: str | None,
) -> None:
    repository = _PreparedRepository(kind=kind, lineage_mode=lineage_mode)
    provider_builds = 0

    def _poison_provider():  # type: ignore[no-untyped-def]
        nonlocal provider_builds
        provider_builds += 1
        raise AssertionError("provider must not be built for a prepared r3 job")

    monkeypatch.setattr(
        download_backtest_history.BacktestApplicationService,
        "_build_repository",
        staticmethod(lambda: repository),
    )
    monkeypatch.setattr(download_backtest_history, "build_provider", _poison_provider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_backtest_history.py",
            "--resume",
            "dataset-download-r3-fixture",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        download_backtest_history.main()

    assert raised.value.code == 2
    assert provider_builds == 0
    assert repository.closed is True
