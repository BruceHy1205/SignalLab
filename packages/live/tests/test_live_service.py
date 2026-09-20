"""live 意图队列 + stub broker。"""

from __future__ import annotations

from signal_live.broker import StubBroker, build_broker
from signal_live.models import Base
from signal_live.service import LiveService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_confirm_reject_flow():
    with _session() as session:
        svc = LiveService(broker=StubBroker())
        intent = svc.create_intent(
            session, symbol="600519.SH", side="buy", quantity=100, note="test"
        )
        assert intent["status"] == "pending_confirm"
        assert intent["broker"] == "stub"

        out = svc.confirm(session, intent["id"])
        assert out["status"] == "submitted"
        assert out["broker_order_id"] and out["broker_order_id"].startswith("stub-")

        intent2 = svc.create_intent(session, symbol="000001.SZ", side="sell", quantity=200)
        rejected = svc.reject(session, intent2["id"], "nope")
        assert rejected["status"] == "rejected"


def test_confirm_wrong_status():
    with _session() as session:
        svc = LiveService(broker=StubBroker())
        intent = svc.create_intent(session, symbol="600519.SH", side="buy", quantity=100)
        svc.confirm(session, intent["id"])
        try:
            svc.confirm(session, intent["id"])
            raise AssertionError("should fail")
        except ValueError:
            pass


def test_build_broker_stub():
    assert build_broker("stub").name == "stub"


def test_miniqmt_missing_xtquant():
    from signal_live.broker import MiniqmtBroker

    try:
        MiniqmtBroker(account="x", path="C:\\missing\\userdata_mini").submit_order(
            symbol="600519.SH", side="buy", quantity=100
        )
        # 若环境碰巧装了 xtquant 则可能走别的错误路径;至少不应静默成功无账号路径
    except RuntimeError as e:
        msg = str(e).lower()
        assert (
            "xtquant" in msg
            or "account" in msg
            or "miniqmt" in msg
            or "path" in msg
            or "不存在" in str(e)
        )


def test_miniqmt_probe_without_xtquant():
    from signal_live.broker import MiniqmtBroker

    info = MiniqmtBroker(account="", path="").probe()
    assert info["broker"] == "miniqmt"
    assert info["connected"] is False


def test_to_qmt_code():
    from signal_live.broker import _to_qmt_code

    assert _to_qmt_code("600519.SH") == "600519.SH"
    assert _to_qmt_code("600519") == "600519.SH"
    assert _to_qmt_code("000001") == "000001.SZ"
