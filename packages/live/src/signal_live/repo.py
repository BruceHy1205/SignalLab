"""live_intents 读写。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_live.models import LiveIntent, utcnow


def create_intent(
    session: Session,
    *,
    symbol: str,
    side: str,
    quantity: int,
    source: str = "manual",
    signal_id: str | None = None,
    note: str = "",
    broker: str = "stub",
    limit_price: float | None = None,
    extra: dict | None = None,
) -> LiveIntent:
    intent = LiveIntent(
        symbol=symbol,
        side=side,
        quantity=quantity,
        source=source,
        signal_id=signal_id,
        note=note,
        broker=broker,
        limit_price=limit_price,
        extra=extra or {},
        status="pending_confirm",
    )
    session.add(intent)
    session.flush()
    return intent


def get_intent(session: Session, intent_id: str) -> LiveIntent | None:
    return session.get(LiveIntent, intent_id)


def list_intents(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
) -> Sequence[LiveIntent]:
    stmt = select(LiveIntent).order_by(LiveIntent.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(LiveIntent.status == status)
    return session.execute(stmt).scalars().all()


def mark_rejected(session: Session, intent: LiveIntent, reason: str = "") -> None:
    intent.status = "rejected"
    intent.error = reason
    intent.decided_at = utcnow()
    session.flush()


def mark_cancelled(session: Session, intent: LiveIntent, reason: str = "") -> None:
    intent.status = "cancelled"
    intent.error = reason
    intent.decided_at = utcnow()
    session.flush()


def mark_submitted(
    session: Session,
    intent: LiveIntent,
    *,
    broker_order_id: str,
) -> None:
    intent.status = "submitted"
    intent.broker_order_id = broker_order_id
    intent.decided_at = utcnow()
    intent.submitted_at = utcnow()
    session.flush()


def mark_failed(session: Session, intent: LiveIntent, error: str) -> None:
    intent.status = "failed"
    intent.error = error[:2000]
    intent.decided_at = utcnow()
    session.flush()
