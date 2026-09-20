from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from signal_agents import repo
from signal_agents.service import AgentService, AgentSettings
from signal_datahub.symbols import normalize_symbol
from signal_papertrade.service import PaperService
from sqlalchemy.orm import Session

from signal_api.adapters.agent_ports import (
    CompositeMarketPort,
    CompositePaperPort,
    CompositeTrackerPort,
    ConfigWatchlist,
)
from signal_api.adapters.datahub_prices import DatahubPriceReader
from signal_api.config import ApiSettings
from signal_api.db import get_session, make_session

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_list(raw: list[str]) -> list[str]:
    out: list[str] = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        try:
            out.append(normalize_symbol(s))
        except ValueError:
            logger.warning("忽略无法识别的代码: %s", s)
    return out


def _agent_service(settings: ApiSettings | None = None) -> AgentService:
    settings = settings or ApiSettings()
    watch = _normalize_list([s for s in settings.watchlist.split(",") if s.strip()])
    paper = PaperService(DatahubPriceReader(make_session))
    return AgentService(
        market=CompositeMarketPort(make_session),
        tracker=CompositeTrackerPort(make_session),
        paper=CompositePaperPort(make_session, paper),
        watchlist=ConfigWatchlist(watch),
        settings=AgentSettings(
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
            llm_model=settings.llm_model,
            max_candidates=settings.agent_max_candidates,
            max_llm_cost_usd=settings.agent_max_llm_cost_usd,
        ),
    )


class RunRequest(BaseModel):
    account_id: str | None = None
    extra_symbols: list[str] = Field(default_factory=list)
    force_rule: bool = False


class AdoptRequest(BaseModel):
    account_id: str
    quantity: int | None = None


@router.post("/runs", status_code=202)
def start_run(req: RunRequest, background: BackgroundTasks) -> dict:
    extras = _normalize_list(req.extra_symbols)

    def _job() -> None:
        from signal_api.notify_util import get_notify

        svc = _agent_service()
        try:
            with make_session() as s:
                out = svc.run(
                    s,
                    account_id=req.account_id,
                    extra_symbols=extras,
                    force_rule=req.force_rule,
                )
            get_notify().notify_agent_run(
                str(out.get("run_id") or ""),
                str(out.get("status") or "done"),
                int(out.get("signals") or 0),
                summary=str(out.get("error") or "")[:200],
            )
        except Exception:
            logger.exception("后台 agent run 失败")

    background.add_task(_job)
    return {"accepted": True}


@router.post("/runs/sync")
def run_sync(req: RunRequest) -> dict:
    """同步执行(便于测试与小候选池)。"""
    from signal_api.notify_util import get_notify

    svc = _agent_service()
    extras = _normalize_list(req.extra_symbols)
    with make_session() as s:
        out = svc.run(
            s,
            account_id=req.account_id,
            extra_symbols=extras,
            force_rule=req.force_rule,
        )
    get_notify().notify_agent_run(
        str(out.get("run_id") or ""),
        str(out.get("status") or "done"),
        int(out.get("signals") or 0),
        summary=str(out.get("error") or "")[:200],
    )
    return out


@router.get("/runs")
def list_runs(session: Session = Depends(get_session), limit: int = 20) -> list[dict]:
    return [
        {
            "id": r.id,
            "status": r.status,
            "candidate_count": r.candidate_count,
            "model": r.model,
            "llm_cost_usd": r.llm_cost_usd,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        for r in repo.list_runs(session, limit)
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    r = repo.get_run(session, run_id)
    if not r:
        raise HTTPException(404, "not found")
    signals = repo.list_signals(session, run_id=run_id)
    return {
        "id": r.id,
        "status": r.status,
        "model": r.model,
        "llm_cost_usd": r.llm_cost_usd,
        "error": r.error,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "signals": [_sig(s) for s in signals],
    }


@router.get("/signals")
def list_signals(
    run_id: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[dict]:
    return [_sig(s) for s in repo.list_signals(session, run_id=run_id, limit=limit)]


@router.get("/signals/{signal_id}")
def get_signal(signal_id: str, session: Session = Depends(get_session)) -> dict:
    s = repo.get_signal(session, signal_id)
    if not s:
        raise HTTPException(404, "not found")
    return _sig(s, full=True)


@router.post("/signals/{signal_id}/adopt")
def adopt(signal_id: str, req: AdoptRequest) -> dict:
    svc = _agent_service()
    with make_session() as s:
        try:
            return svc.adopt_signal(s, signal_id, req.account_id, req.quantity)
        except KeyError:
            raise HTTPException(404, "not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


class ProposeLiveReq(BaseModel):
    quantity: int | None = None
    note: str = ""
    limit_price: float | None = None


@router.post("/signals/{signal_id}/propose-live")
def propose_live(signal_id: str, req: ProposeLiveReq | None = None) -> dict:
    """把 agent 信号推入实盘人工确认队列(不直接下单)。"""
    from signal_api.notify_util import get_notify
    from signal_api.routes.live_routes import _live

    req = req or ProposeLiveReq()
    with make_session() as s:
        sig = repo.get_signal(s, signal_id)
        if not sig:
            raise HTTPException(404, "not found")
        if sig.action == "hold":
            raise HTTPException(400, "hold 信号不可实盘")
        qty = req.quantity if req.quantity is not None else int(sig.suggested_qty or 0)
        if qty <= 0:
            raise HTTPException(400, "quantity 无效")
        try:
            out = _live().create_intent(
                s,
                symbol=sig.symbol,
                side=sig.action,
                quantity=qty,
                source="agent",
                signal_id=sig.id,
                note=req.note or f"from agent signal {sig.id}",
                limit_price=req.limit_price,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    get_notify().notify_live_intent(
        out["id"],
        "pending_confirm",
        f"agent {out['side']} {out['quantity']} {out['symbol']}",
    )
    return out


def _sig(s, full: bool = False) -> dict:
    out = {
        "id": s.id,
        "run_id": s.run_id,
        "symbol": s.symbol,
        "action": s.action,
        "confidence": s.confidence,
        "suggested_qty": s.suggested_qty,
        "created_at": s.created_at,
    }
    if full:
        out["reason"] = s.reason
    else:
        out["summary"] = (s.reason or {}).get("summary", "")
        out["mode"] = (s.reason or {}).get("mode", "")
    return out
