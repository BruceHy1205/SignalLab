"""实盘意图服务:创建 → 人工确认 → broker 提交。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from signal_live import repo
from signal_live.broker import BrokerPort, StubBroker


@dataclass
class LiveSettings:
    broker: str = "stub"
    miniqmt_account: str = ""
    miniqmt_path: str = ""
    require_confirm: bool = True  # 永远建议 True;False 仅测试


class LiveService:
    def __init__(
        self,
        broker: BrokerPort | None = None,
        settings: LiveSettings | None = None,
    ) -> None:
        self._settings = settings or LiveSettings()
        self._broker = broker or StubBroker()

    def create_intent(
        self,
        session: Session,
        *,
        symbol: str,
        side: str,
        quantity: int,
        source: str = "manual",
        signal_id: str | None = None,
        note: str = "",
        limit_price: float | None = None,
    ) -> dict:
        side = side.lower().strip()
        if side not in ("buy", "sell"):
            raise ValueError("side 须为 buy/sell")
        if quantity <= 0:
            raise ValueError("quantity 必须 > 0")
        intent = repo.create_intent(
            session,
            symbol=symbol,
            side=side,
            quantity=quantity,
            source=source,
            signal_id=signal_id,
            note=note,
            broker=self._broker.name,
            limit_price=limit_price,
        )
        session.commit()
        return self._dict(intent)

    def confirm(self, session: Session, intent_id: str) -> dict:
        intent = repo.get_intent(session, intent_id)
        if not intent:
            raise KeyError(intent_id)
        if intent.status != "pending_confirm":
            raise ValueError(f"状态 {intent.status} 不可确认")
        try:
            result = self._broker.submit_order(
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                limit_price=intent.limit_price,
            )
        except Exception as e:
            repo.mark_failed(session, intent, str(e))
            session.commit()
            raise
        if result.status == "rejected":
            repo.mark_failed(session, intent, result.message or "broker rejected")
            session.commit()
            return self._dict(intent)
        repo.mark_submitted(session, intent, broker_order_id=result.broker_order_id)
        session.commit()
        return self._dict(intent)

    def reject(self, session: Session, intent_id: str, reason: str = "user rejected") -> dict:
        intent = repo.get_intent(session, intent_id)
        if not intent:
            raise KeyError(intent_id)
        if intent.status != "pending_confirm":
            raise ValueError(f"状态 {intent.status} 不可拒绝")
        repo.mark_rejected(session, intent, reason)
        session.commit()
        return self._dict(intent)

    def cancel(self, session: Session, intent_id: str, reason: str = "cancelled") -> dict:
        intent = repo.get_intent(session, intent_id)
        if not intent:
            raise KeyError(intent_id)
        if intent.status != "pending_confirm":
            raise ValueError(f"状态 {intent.status} 不可取消")
        repo.mark_cancelled(session, intent, reason)
        session.commit()
        return self._dict(intent)

    def list_intents(
        self, session: Session, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        return [self._dict(x) for x in repo.list_intents(session, status=status, limit=limit)]

    def _dict(self, intent) -> dict:
        return {
            "id": intent.id,
            "symbol": intent.symbol,
            "side": intent.side,
            "quantity": intent.quantity,
            "status": intent.status,
            "source": intent.source,
            "signal_id": intent.signal_id,
            "note": intent.note,
            "broker": intent.broker,
            "broker_order_id": intent.broker_order_id,
            "limit_price": intent.limit_price,
            "error": intent.error,
            "created_at": intent.created_at,
            "decided_at": intent.decided_at,
            "submitted_at": intent.submitted_at,
        }
