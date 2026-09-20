from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from signal_datahub.symbols import normalize_symbol
from signal_live import LiveService, LiveSettings, build_broker

from signal_api.config import ApiSettings
from signal_api.db import make_session
from signal_api.notify_util import get_notify

router = APIRouter()


def _live() -> LiveService:
    s = ApiSettings()
    broker = build_broker(
        s.live_broker,
        account=s.live_miniqmt_account,
        path=s.live_miniqmt_path,
    )
    return LiveService(
        broker=broker,
        settings=LiveSettings(
            broker=s.live_broker,
            miniqmt_account=s.live_miniqmt_account,
            miniqmt_path=s.live_miniqmt_path,
        ),
    )


class CreateIntentReq(BaseModel):
    symbol: str
    side: str
    quantity: int = Field(gt=0)
    note: str = ""
    limit_price: float | None = None
    signal_id: str | None = None
    source: str = "manual"


@router.post("/intents")
def create_intent(req: CreateIntentReq) -> dict:
    try:
        symbol = normalize_symbol(req.symbol)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    svc = _live()
    with make_session() as s:
        try:
            out = svc.create_intent(
                s,
                symbol=symbol,
                side=req.side,
                quantity=req.quantity,
                source=req.source,
                signal_id=req.signal_id,
                note=req.note,
                limit_price=req.limit_price,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    get_notify().notify_live_intent(
        out["id"],
        "pending_confirm",
        f"{out['side']} {out['quantity']} {out['symbol']}",
    )
    return out


@router.get("/intents")
def list_intents(
    status: str | None = Query(default=None),
    limit: int = 50,
) -> list[dict]:
    with make_session() as s:
        return _live().list_intents(s, status=status, limit=limit)


@router.get("/broker")
def broker_status() -> dict:
    """当前 broker 配置与 miniQMT 连通探测(stub 直接返回)。"""
    s = ApiSettings()
    broker = build_broker(
        s.live_broker,
        account=s.live_miniqmt_account,
        path=s.live_miniqmt_path,
    )
    if hasattr(broker, "probe"):
        return broker.probe()  # type: ignore[no-any-return]
    return {
        "broker": broker.name,
        "connected": True,
        "message": "stub broker always ready",
    }


@router.post("/intents/{intent_id}/confirm")
def confirm_intent(intent_id: str) -> dict:
    svc = _live()
    with make_session() as s:
        try:
            out = svc.confirm(s, intent_id)
        except KeyError:
            raise HTTPException(404, "not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from e
    get_notify().notify_live_intent(
        out["id"],
        out["status"],
        f"{out['side']} {out['quantity']} {out['symbol']} broker={out.get('broker_order_id')}",
    )
    return out


@router.post("/intents/{intent_id}/reject")
def reject_intent(intent_id: str, reason: str = "user rejected") -> dict:
    with make_session() as s:
        try:
            out = _live().reject(s, intent_id, reason)
        except KeyError:
            raise HTTPException(404, "not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    get_notify().notify_live_intent(out["id"], "rejected", reason)
    return out
