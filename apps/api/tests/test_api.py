"""API 骨架测试:sqlite 内存库替代 pg,验证健康检查与 datahub 读端点。"""

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from signal_api.db import get_session
from signal_api.main import create_app
from signal_datahub import repo
from signal_datahub.models import Base
from signal_datahub.providers.base import BAR_COLUMNS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 内存库跨连接共享,否则每个连接各自一个空库
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app()

    def override_session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    # 不走 lifespan(避免连接真实 pg),直接用 TestClient 的非 lifespan 模式
    with TestClient(app, raise_server_exceptions=True) as c, factory() as seed:
        df = pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 7, 1),
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.8,
                    "close": 10.5,
                    "volume": 100,
                    "amount": 1e6,
                    "qfq_factor": 0.5,
                }
            ]
        ).loc[:, BAR_COLUMNS]
        repo.upsert_daily_bars(seed, "600519.SH", df, "test")
        seed.commit()
        yield c


def test_bars_qfq_and_raw(client):
    qfq = client.get(
        "/api/datahub/bars",
        params={"symbol": "600519", "start": "2026-07-01", "end": "2026-07-02"},
    ).json()
    assert qfq[0]["close"] == pytest.approx(5.25)  # 10.5 * 0.5

    raw = client.get(
        "/api/datahub/bars",
        params={
            "symbol": "600519.SH",
            "start": "2026-07-01",
            "end": "2026-07-02",
            "adjust": "raw",
        },
    ).json()
    assert raw[0]["close"] == pytest.approx(10.5)


def test_bars_rejects_bad_symbol(client):
    r = client.get(
        "/api/datahub/bars",
        params={"symbol": "not-a-symbol", "start": "2026-07-01", "end": "2026-07-02"},
    )
    assert r.status_code == 400


def test_sync_runs_empty(client):
    assert client.get("/api/datahub/sync/runs").json() == []
