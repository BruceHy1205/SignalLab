from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from signal_datahub import repo
from signal_datahub.config import DatahubSettings, build_providers
from signal_datahub.symbols import BENCHMARK_SYMBOL, normalize_symbol
from signal_datahub.sync import CSI300, SyncService, market_today
from sqlalchemy.orm import Session

from signal_api.db import get_session, make_session

router = APIRouter()


def _sync_service() -> SyncService:
    return SyncService(build_providers(DatahubSettings()))


class SyncRequest(BaseModel):
    scope: str = Field(default="csi300", description="csi300 | instruments")
    years: int = Field(default=3, ge=1, le=10, description="日线回补年数(scope=csi300)")


def _run_csi300_sync(years: int) -> None:
    svc = _sync_service()
    with make_session() as session:
        symbols = svc.sync_index_constituents(session, CSI300)
        if BENCHMARK_SYMBOL not in symbols:
            symbols = [BENCHMARK_SYMBOL, *symbols]
        end = market_today()
        svc.sync_daily_bars(session, symbols, end - timedelta(days=365 * years), end)


def _run_instruments_sync() -> None:
    svc = _sync_service()
    with make_session() as session:
        svc.sync_instruments(session)


@router.post("/sync", status_code=202)
def trigger_sync(req: SyncRequest, background: BackgroundTasks) -> dict:
    """触发后台同步,进度通过 GET /sync/runs 观察。"""
    if req.scope == "csi300":
        background.add_task(_run_csi300_sync, req.years)
    elif req.scope == "instruments":
        background.add_task(_run_instruments_sync)
    else:
        raise HTTPException(400, f"未知 scope: {req.scope}")
    return {"accepted": True, "scope": req.scope}


@router.get("/sync/runs")
def list_sync_runs(session: Session = Depends(get_session), limit: int = 20) -> list[dict]:
    return [
        {
            "id": r.id,
            "job_type": r.job_type,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "detail": r.detail,
        }
        for r in repo.recent_sync_runs(session, limit)
    ]


@router.get("/instruments")
def search_instruments(
    query: str = Query(min_length=1), session: Session = Depends(get_session)
) -> list[dict]:
    return [
        {"symbol": i.symbol, "name": i.name, "exchange": i.exchange}
        for i in repo.search_instruments(session, query)
    ]


@router.get("/bars")
def get_bars(
    symbol: str,
    start: date,
    end: date,
    adjust: str = Query(default="qfq", pattern="^(raw|qfq)$"),
    session: Session = Depends(get_session),
) -> list[dict]:
    """读库返回日线。adjust=qfq 返回前复权价(原始价 * qfq_factor)。"""
    try:
        symbol = normalize_symbol(symbol)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    bars = repo.get_bars(session, symbol, start, end)
    out = []
    for b in bars:
        factor = b.qfq_factor if adjust == "qfq" else 1.0
        out.append(
            {
                "trade_date": b.trade_date,
                "open": round(float(b.open) * factor, 4),
                "high": round(float(b.high) * factor, 4),
                "low": round(float(b.low) * factor, 4),
                "close": round(float(b.close) * factor, 4),
                "volume": b.volume,
                "amount": float(b.amount),
            }
        )
    return out


class ExportQlibRequest(BaseModel):
    name: str | None = Field(default=None, description="快照名,默认 qlib_cn_YYYYMMDD")
    symbols: list[str] | None = None
    start: date | None = None
    end: date | None = None
    include_csi300: bool = False
    out_root: str | None = Field(
        default=None,
        description="覆盖 RESEARCH_DATA_SNAPSHOTS_DIR;默认读配置",
    )


@router.post("/export-qlib")
def export_qlib(req: ExportQlibRequest) -> dict:
    """同步导出 Qlib dump_bin 兼容快照到快照根目录/{name}/。"""
    from pathlib import Path

    from signal_datahub.qlib_dump import dump_qlib_snapshot

    from signal_api.config import ApiSettings

    settings = ApiSettings()
    out_root = Path(
        req.out_root or settings.research_data_snapshots_dir or "/tmp/signal-qlib-snapshots"
    )
    symbols = None
    if req.symbols:
        try:
            symbols = [normalize_symbol(s) for s in req.symbols]
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    universe = None
    with make_session() as session:
        if req.include_csi300:
            universe = _sync_service().sync_index_constituents(session, CSI300)
        try:
            result = dump_qlib_snapshot(
                session,
                out_root,
                snapshot_name=req.name,
                symbols=symbols,
                start=req.start,
                end=req.end,
                universe_symbols=universe,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    return {
        "snapshot_name": result.snapshot_name,
        "out_dir": str(result.out_dir),
        "n_symbols": result.n_symbols,
        "n_calendar_days": result.n_calendar_days,
        "fields": list(result.fields),
    }
