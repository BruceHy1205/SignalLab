"""双框架接入:producer 路由、镜像选择、产出转换与 harvest。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from signal_research.models import Base
from signal_research.provisioners import LocalDockerProvisioner, Provisioner, RemoteSSHProvisioner
from signal_research.service import ResearchService, ResearchSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
RUNNERS = ROOT / "runners"
if str(RUNNERS) not in sys.path:
    sys.path.insert(0, str(RUNNERS))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # 保证同目录相对 import(to_package / real_backend)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        if str(path.parent) in sys.path:
            sys.path.remove(str(path.parent))
    return mod


class FakeMarket:
    def get_qfq_bars(self, symbol: str, start, end) -> pd.DataFrame:
        return pd.DataFrame(
            columns=["trade_date", "open", "high", "low", "close", "volume"]
        )

    def list_universe_symbols(self, universe: str = "csi300", limit: int = 30) -> list[str]:
        return ["600519.SH"][:limit]


class FakeProvisioner(Provisioner):
    def start(self, job_id, spec, *, work_root=None):
        return {"type": "fake", "pid": 1, "work_dir": "/tmp"}

    def is_alive(self, runtime):
        return True

    def stop(self, runtime):
        return None


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_normalize_producer_and_scripts():
    svc = ResearchService(FakeMarket(), settings=ResearchSettings())
    assert svc._normalize_producer("AlphaAgent") == "alphaagent"
    assert svc._normalize_producer("rdagent@0.8") == "rdagent"
    with pytest.raises(ValueError):
        svc._normalize_producer("unknown")
    aa = svc._runner_script_for("alphaagent")
    rd = svc._runner_script_for("rdagent")
    assert aa.name == "runner.py" and "alphaagent" in str(aa)
    assert rd.name == "runner.py" and "rdagent" in str(rd)


def test_create_job_rejects_bad_producer():
    with _session() as session:
        svc = ResearchService(
            FakeMarket(),
            provisioner=FakeProvisioner(),
            settings=ResearchSettings(),
        )
        with pytest.raises(ValueError):
            svc.create_job(session, producer="foobar")


def test_create_rdagent_and_alphaagent_jobs():
    with _session() as session:
        svc = ResearchService(
            FakeMarket(),
            provisioner=FakeProvisioner(),
            settings=ResearchSettings(),
        )
        a = svc.create_job(session, producer="alphaagent")
        r = svc.create_job(
            session,
            producer="rdagent",
            runner_type="remote_ssh",
            ssh_host="1.2.3.4",
            ssh_user="u",
        )
        assert a["producer"] == "alphaagent"
        assert r["producer"] == "rdagent"
        assert r["runner_target"]["type"] == "remote_ssh"


def test_image_routing_local_and_remote():
    local = LocalDockerProvisioner(
        alphaagent_image="signal-alphaagent:stub",
        rdagent_image="signal-rdagent:stub",
    )
    assert local._image_for_producer("alphaagent") == "signal-alphaagent:stub"
    assert local._image_for_producer("rdagent@real") == "signal-rdagent:stub"

    remote = RemoteSSHProvisioner(
        alphaagent_image="aa:real",
        rdagent_image="rd:real",
    )
    assert remote._image_for_producer("alphaagent") == "aa:real"
    assert remote._image_for_producer("rdagent") == "rd:real"


def test_alphaagent_to_package_and_harvest(tmp_path: Path):
    to_pkg = _load(ROOT / "runners/alphaagent/to_package.py", "aa_to_pkg")
    real = _load(ROOT / "runners/alphaagent/real_backend.py", "aa_real")
    result = {
        "producer": "alphaagent@real",
        "factors": [
            {
                "name": "mom_5",
                "expression": "Ref($close, 5) / $close - 1",
                "description": "5日动量",
                "hypothesis": "trend",
            }
        ],
        "metrics": {"ic": -0.03, "arr": 0.1, "mdd": -0.1},
    }
    data = to_pkg.alphaagent_result_to_package(result, package_id="p1")
    assert data[:2] == b"PK"

    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    harvested = real.harvest_workspace(tmp_path)
    assert harvested and harvested["factors"][0]["name"] == "mom_5"


def test_rdagent_harvest_from_nested_json(tmp_path: Path):
    real = _load(ROOT / "runners/rdagent/real_backend.py", "rd_real")
    nested = tmp_path / "log" / "factor.json"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        json.dumps(
            {
                "name": "rd_x",
                "expression": "Mean($close, 5) / $close - 1",
                "hypothesis": "h",
            }
        ),
        encoding="utf-8",
    )
    out = real.harvest_workspace(tmp_path)
    assert out and out["factors"][0]["expression"].startswith("Mean")
