"""research service 状态机与事件/产物处理(不启真实 runner 进程)。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pandas as pd
from signal_contracts.runner_events import (
    CompletionReport,
    CompletionStatus,
    RunnerEvent,
    RunnerEventType,
    sign_payload,
)
from signal_research.models import Base
from signal_research.provisioners import Provisioner
from signal_research.service import ResearchService, ResearchSettings
from signal_research.validator import build_stub_package_zip
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeMarket:
    def get_qfq_bars(self, symbol, start, end):
        n = 40
        dates = [d.date() for d in pd.bdate_range(end=end, periods=n)]
        return pd.DataFrame(
            {
                "trade_date": dates,
                "open": [10.0] * n,
                "high": [11.0] * n,
                "low": [9.0] * n,
                "close": [10.0 + i * 0.05 for i in range(n)],
                "volume": [1e6] * n,
            }
        )

    def list_universe_symbols(self, universe="csi300", limit=30):
        return ["600519.SH", "000001.SZ"][:limit]


class FakeProvisioner(Provisioner):
    def __init__(self):
        self.started = []
        self._alive = True

    def start(self, job_id, spec, *, work_root=None):
        self.started.append(job_id)
        return {"type": "fake", "pid": 1, "work_dir": "/tmp"}

    def is_alive(self, runtime):
        return self._alive

    def stop(self, runtime):
        self._alive = False


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_and_start():
    with _session() as session:
        svc = ResearchService(
            FakeMarket(),
            provisioner=FakeProvisioner(),
            settings=ResearchSettings(callback_base_host="http://127.0.0.1:8000"),
        )
        job = svc.create_job(session, max_loops=2)
        assert job["status"] == "draft"
        out = svc.start_job(session, job["id"])
        assert out["status"] == "running"
        assert svc._provisioner.started  # type: ignore[union-attr]


def test_event_and_artifact_and_complete():
    secret = "dev-secret"
    with _session() as session:
        svc = ResearchService(
            FakeMarket(),
            provisioner=FakeProvisioner(),
            settings=ResearchSettings(callback_base_host="http://127.0.0.1:8000"),
        )
        job = svc.create_job(session, max_loops=2)
        svc.start_job(session, job["id"])
        job_id = job["id"]

        ev = RunnerEvent(
            job_id=UUID(job_id),
            type=RunnerEventType.LOOP_DONE,
            ts=datetime.now(UTC),
            seq=1,
            loop=1,
            best_ic=0.02,
            llm_cost_usd=0.1,
        )
        body = ev.model_dump_json().encode()
        sig = sign_payload(secret, body)
        r = svc.handle_event(session, job_id, body, sig, secret)
        assert r["accepted"]

        pkg_id = uuid4()
        data = build_stub_package_zip(package_id=str(pkg_id), ic=-0.02)
        art = svc.handle_artifact(session, job_id, data, sign_payload(secret, data), secret)
        assert art["ok"]
        strategy_id = art["strategy_id"]

        report = CompletionReport(
            job_id=UUID(job_id),
            status=CompletionStatus.BUDGET_EXCEEDED,
            package_id=pkg_id,
            total_loops=2,
            total_llm_cost_usd=0.1,
            summary={"best_ic": 0.02},
        )
        body2 = report.model_dump_json().encode()
        svc.handle_complete(session, job_id, body2, sign_payload(secret, body2), secret)
        from signal_research import repo

        j = repo.get_job(session, job_id)
        assert j is not None
        assert j.status == "budget_exceeded"
        assert j.strategy_id == strategy_id

        sigs = svc.generate_signals(session, strategy_id, date(2024, 6, 1))
        assert sigs["count"] >= 1


def test_probe_lost():
    with _session() as session:
        prov = FakeProvisioner()
        svc = ResearchService(
            FakeMarket(),
            provisioner=prov,
            settings=ResearchSettings(callback_base_host="http://127.0.0.1:8000"),
        )
        job = svc.create_job(session)
        svc.start_job(session, job["id"])
        from signal_research import repo

        j = repo.get_job(session, job["id"])
        assert j is not None
        j.last_heartbeat_at = datetime(2020, 1, 1, tzinfo=UTC)
        session.commit()
        prov._alive = False
        marked = svc.probe_lost_jobs(session)
        assert job["id"] in marked
        j2 = repo.get_job(session, job["id"])
        assert j2 is not None and j2.status == "lost"
