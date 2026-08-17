"""FastAPI 入口：提供儀表板頁面與唯讀掃描快照。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import build_provider
from dashboard.service import DashboardService

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="台股盤中雷達")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_service: DashboardService | None = None


def get_dashboard_service() -> DashboardService:
    """在 Web process 生命週期中共用同一個 Provider 與快照快取。"""
    global _service
    if _service is None:
        _service = DashboardService(build_provider())
    return _service


@app.get("/", include_in_schema=False)
def dashboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/dashboard/snapshot")
def dashboard_snapshot() -> dict[str, Any]:
    return get_dashboard_service().snapshot()


@app.post("/api/dashboard/refresh")
def refresh_dashboard_snapshot() -> dict[str, Any]:
    return get_dashboard_service().refresh()


@app.get("/api/dashboard/candidates/{symbol}/history")
def candidate_history(symbol: str, period: str = "1d") -> dict[str, Any]:
    """回傳選定 Candidate 的按需 Kbar；沒有任何下單能力。"""
    try:
        return get_dashboard_service().candidate_history(symbol, period)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
