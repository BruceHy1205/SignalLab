from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from signal_datahub.symbols import normalize_symbol
from signal_tracker import repo
from signal_tracker.extract import LlmExtractor
from signal_tracker.service import ImportService
from sqlalchemy.orm import Session

from signal_api.adapters.datahub_bars import DatahubBarsReader
from signal_api.config import ApiSettings
from signal_api.db import get_session, make_session

router = APIRouter()


def _import_service() -> ImportService:
    settings = ApiSettings()
    extractor = None
    if settings.llm_api_key:
        extractor = LlmExtractor(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    return ImportService(DatahubBarsReader(make_session), extractor=extractor)


class ImportRequest(BaseModel):
    content: str = Field(min_length=1)
    source_name: str = Field(min_length=1, max_length=64)
    format: str = Field(default="paste", pattern="^(paste|wechat)$")


class ResolveRequest(BaseModel):
    symbol: str = Field(min_length=1)


@router.post("/import")
def import_chat(req: ImportRequest, session: Session = Depends(get_session)) -> dict:
    svc = _import_service()
    return svc.import_text(
        session, req.content, source_name=req.source_name, channel=req.format, format=req.format
    )


@router.get("/recommendations")
def list_recs(
    status: str | None = None,
    source_id: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[dict]:
    return [
        {
            "id": r.id,
            "source_id": r.source_id,
            "message_time": r.message_time,
            "symbol": r.symbol,
            "symbol_name": r.symbol_name,
            "action": r.action,
            "confidence": r.confidence,
            "target_price": r.target_price,
            "stop_loss": r.stop_loss,
            "status": r.status,
            "baseline_date": r.baseline_date,
            "baseline_price": r.baseline_price,
            "baseline_rule": r.baseline_rule,
            "reason": r.reason,
        }
        for r in repo.list_recommendations(session, source_id=source_id, status=status, limit=limit)
    ]


@router.get("/recommendations/{rec_id}")
def get_rec(rec_id: str, session: Session = Depends(get_session)) -> dict:
    r = repo.get_recommendation(session, rec_id)
    if not r:
        raise HTTPException(404, "not found")
    perfs = repo.get_performances(session, rec_id)
    return {
        "id": r.id,
        "source_id": r.source_id,
        "message_time": r.message_time,
        "symbol": r.symbol,
        "symbol_name": r.symbol_name,
        "action": r.action,
        "confidence": r.confidence,
        "target_price": r.target_price,
        "stop_loss": r.stop_loss,
        "status": r.status,
        "baseline_date": r.baseline_date,
        "baseline_price": r.baseline_price,
        "baseline_rule": r.baseline_rule,
        "reason": r.reason,
        "raw_text": r.raw_text,
        "performances": [
            {
                "window_days": p.window_days,
                "abs_return": p.abs_return,
                "excess_return": p.excess_return,
                "max_drawdown": p.max_drawdown,
                "max_runup": p.max_runup,
                "as_of_date": p.as_of_date,
            }
            for p in perfs
        ],
    }


@router.post("/recommendations/{rec_id}/resolve")
def resolve_rec(rec_id: str, req: ResolveRequest, session: Session = Depends(get_session)) -> dict:
    try:
        symbol = normalize_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    svc = _import_service()
    try:
        svc.resolve_pending(session, rec_id, symbol)
    except KeyError:
        raise HTTPException(404, "not found") from None
    return {"ok": True, "symbol": symbol}


@router.get("/leaderboard")
def leaderboard(window_days: int = 5, session: Session = Depends(get_session)) -> list[dict]:
    return repo.source_stats(session, window_days=window_days)


@router.post("/refresh", status_code=202)
def refresh_all(background: BackgroundTasks) -> dict:
    def _job() -> None:
        svc = _import_service()
        with make_session() as s:
            svc.refresh_all_active(s)

    background.add_task(_job)
    return {"accepted": True}
