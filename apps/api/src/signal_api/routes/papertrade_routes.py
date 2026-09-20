from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from signal_datahub.symbols import normalize_symbol
from signal_papertrade import repo
from signal_papertrade.service import PaperService
from sqlalchemy.orm import Session

from signal_api.adapters.datahub_prices import DatahubPriceReader
from signal_api.db import get_session, make_session

router = APIRouter()


def _svc() -> PaperService:
    return PaperService(DatahubPriceReader(make_session))


class CreateAccountReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    initial_cash: float = Field(default=1_000_000, gt=0)


class PlaceOrderReq(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(gt=0)
    note: str = ""


class RunDayReq(BaseModel):
    trade_date: date
    account_id: str | None = None


@router.post("/accounts")
def create_account(req: CreateAccountReq) -> dict:
    svc = _svc()
    with make_session() as s:
        try:
            acct = svc.create_account(s, req.name, req.initial_cash)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return _acct_dict(acct)


@router.get("/accounts")
def list_accounts(session: Session = Depends(get_session)) -> list[dict]:
    return [_acct_dict(a) for a in repo.list_accounts(session)]


@router.get("/accounts/{account_id}")
def get_account(account_id: str, session: Session = Depends(get_session)) -> dict:
    acct = repo.get_account(session, account_id)
    if not acct:
        raise HTTPException(404, "not found")
    svc = _svc()
    perf = svc.account_performance(session, account_id)
    return {**_acct_dict(acct), "performance": perf}


@router.post("/accounts/{account_id}/orders")
def place_order(account_id: str, req: PlaceOrderReq) -> dict:
    try:
        symbol = normalize_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    svc = _svc()
    with make_session() as s:
        try:
            order = svc.place_order(s, account_id, symbol, req.side, req.quantity, note=req.note)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from e
        return _order_dict(order)


@router.get("/accounts/{account_id}/orders")
def list_orders(
    account_id: str,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    return [_order_dict(o) for o in repo.list_orders(session, account_id, status=status)]


@router.get("/accounts/{account_id}/positions")
def list_positions(account_id: str, session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "symbol": p.symbol,
            "quantity": p.quantity,
            "avg_cost": p.avg_cost,
        }
        for p in repo.list_positions(session, account_id)
    ]


@router.get("/accounts/{account_id}/nav")
def list_nav(account_id: str, session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "trade_date": p.trade_date,
            "cash": float(p.cash),
            "market_value": float(p.market_value),
            "nav": float(p.nav),
            "bench_nav": p.bench_nav,
        }
        for p in repo.list_nav(session, account_id)
    ]


@router.post("/run-day")
def run_day(req: RunDayReq) -> dict:
    svc = _svc()
    with make_session() as s:
        return svc.run_day(s, req.trade_date, req.account_id)


def _acct_dict(a) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "cash": float(a.cash),
        "initial_cash": float(a.initial_cash),
        "status": a.status,
        "commission_rate": a.commission_rate,
        "slippage_bps": a.slippage_bps,
        "lot_size": a.lot_size,
    }


def _order_dict(o) -> dict:
    return {
        "id": o.id,
        "account_id": o.account_id,
        "symbol": o.symbol,
        "side": o.side,
        "quantity": o.quantity,
        "status": o.status,
        "source": o.source,
        "note": o.note,
        "submitted_at": o.submitted_at,
        "fill_date": o.fill_date,
        "fill_price": o.fill_price,
        "fill_amount": float(o.fill_amount) if o.fill_amount is not None else None,
        "commission": o.commission,
        "reject_reason": o.reject_reason,
    }
