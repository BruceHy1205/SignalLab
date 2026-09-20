from datetime import date

import pandas as pd
import pytest
from signal_agents.candidates import build_candidate_pool, snapshot_symbol
from signal_agents.models import Base
from signal_agents.rule_engine import decide_rule
from signal_agents.service import AgentService, AgentSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeMarket:
    def get_qfq_bars(self, symbol, start, end):
        dates = pd.bdate_range(end=date.today(), periods=30).tolist()
        closes = [10 + i * 0.1 for i in range(30)]
        return pd.DataFrame(
            {
                "trade_date": [d.date() for d in dates],
                "open": closes,
                "high": [c + 0.2 for c in closes],
                "low": [c - 0.2 for c in closes],
                "close": closes,
            }
        )

    def resolve_name(self, name):
        return []


class FakeTracker:
    def recent_recommended_symbols(self, days=30, limit=50):
        return ["600519.SH", "000001.SZ"]

    def rec_stats_for_symbol(self, symbol, window_days=5):
        return {
            "n": 3,
            "win_rate": 0.67,
            "avg_excess": 0.02,
            "sources": ["投顾A"],
        }


class FakePaper:
    def __init__(self):
        self.orders = []

    def list_positions(self, account_id):
        return []

    def place_order(self, account_id, symbol, side, quantity, note=""):
        o = {
            "account_id": account_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "note": note,
        }
        self.orders.append(o)
        return o


class FakeWatch:
    def list_symbols(self):
        return ["300750.SZ"]


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_candidate_pool():
    pool = build_candidate_pool(FakeWatch(), FakeTracker(), limit=10)
    assert pool[0] == "300750.SZ"
    assert "600519.SH" in pool


def test_rule_decide_buy_bias():
    snap = snapshot_symbol(FakeMarket(), FakeTracker(), "600519.SH")
    assert snap is not None
    d = decide_rule(snap, 0)
    assert d["action"] in ("buy", "sell", "hold")
    assert "technical_analyst" in d["reason"]
    assert d["reason"]["mode"] == "rule"


def test_agent_run_rule_mode(session):
    paper = FakePaper()
    svc = AgentService(
        FakeMarket(),
        FakeTracker(),
        paper,
        FakeWatch(),
        AgentSettings(llm_api_key="", max_candidates=5),
    )
    result = svc.run(session, account_id="acc1", force_rule=True)
    assert result["status"] == "succeeded"
    assert result["signals"] >= 1
    assert result["model"] == "rule"

    from signal_agents import repo

    sigs = repo.list_signals(session, run_id=result["run_id"])
    assert len(sigs) == result["signals"]
    # adopt a buy/sell if any
    actionable = [s for s in sigs if s.action in ("buy", "sell") and s.suggested_qty > 0]
    if actionable:
        out = svc.adopt_signal(session, actionable[0].id, "acc1")
        assert paper.orders and out["symbol"] == actionable[0].symbol
