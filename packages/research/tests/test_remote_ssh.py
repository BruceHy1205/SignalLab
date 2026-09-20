"""RemoteSSHProvisioner 与事件补账(假 SSH,不连真机)。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from signal_contracts.runner_events import RunnerEvent, RunnerEventType
from signal_research.models import Base
from signal_research.provisioners import RemoteSSHProvisioner
from signal_research.service import ResearchService, ResearchSettings
from signal_research.ssh_ops import SshExecResult
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeTransport:
    def __init__(self):
        self.files: dict[str, str] = {}
        self.commands: list[str] = []
        self.alive = True
        self.closed = False

    def run(self, command: str, *, env: dict[str, str] | None = None) -> SshExecResult:
        self.commands.append(command)
        if env:
            # secrets 应只经 env 注入,不出现在落盘文件
            assert "job_spec" not in json.dumps(env)
        if "docker info" in command or "command -v docker" in command:
            return SshExecResult(0, "", "")
        if "docker image inspect" in command:
            return SshExecResult(0, "", "")
        if command.startswith("mkdir -p"):
            return SshExecResult(0, "", "")
        if "docker run" in command:
            # 确认 -e 传递变量名而非把 secret 写进文件
            assert "-e " in command
            if env:
                for k in env:
                    assert f"-e {k}" in command or f"-e '{k}'" in command or f'-e "{k}"' in command
            return SshExecResult(0, "sha256:deadbeef\n", "")
        if "docker inspect" in command:
            return SshExecResult(0, "true\n" if self.alive else "false\n", "")
        if "docker rm" in command:
            self.alive = False
            return SshExecResult(0, "", "")
        if command.startswith("rm -rf"):
            return SshExecResult(0, "", "")
        if "test -f" in command and "events.jsonl" in command:
            # 取 path: test -f '...' && cat '...'
            for p, content in self.files.items():
                if "events.jsonl" in p:
                    return SshExecResult(0, content, "")
            return SshExecResult(1, "", "missing")
        if command.startswith("cat "):
            return SshExecResult(0, "", "")
        return SshExecResult(0, "", "")

    def write_text(self, remote_path: str, content: str) -> None:
        # secrets 不得写入 job_spec
        if remote_path.endswith("job_spec.json"):
            data = json.loads(content)
            dumped = json.dumps(data)
            assert "sk-" not in dumped
            assert "BEGIN OPENSSH" not in dumped
        self.files[remote_path] = content

    def read_text(self, remote_path: str) -> str:
        return self.files[remote_path]

    def close(self) -> None:
        self.closed = True


class FakeMarket:
    def get_qfq_bars(self, symbol, start, end):
        import pandas as pd

        n = 20
        dates = [d.date() for d in pd.bdate_range(end=end, periods=n)]
        return pd.DataFrame(
            {
                "trade_date": dates,
                "open": [10.0] * n,
                "high": [11.0] * n,
                "low": [9.0] * n,
                "close": [10.0 + i * 0.01 for i in range(n)],
                "volume": [1e6] * n,
            }
        )

    def list_universe_symbols(self, universe="csi300", limit=30):
        return ["600519.SH"][:limit]


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_remote_start_is_alive_cleanup(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_API_KEY", "test-llm-key")
    monkeypatch.setenv("RUNNER_CALLBACK_SECRET", "dev-secret")

    fake = FakeTransport()

    def factory(host, user, key, port):
        assert host == "1.2.3.4"
        assert user == "ubuntu"
        return fake

    rsync_calls: list = []

    def fake_rsync(local, **kw):
        rsync_calls.append((local, kw))

    snap = tmp_path / "qlib_cn_stub"
    snap.mkdir()
    (snap / "meta").write_text("x", encoding="utf-8")

    prov = RemoteSSHProvisioner(
        image="signal-rdagent:stub",
        data_snapshots_dir=tmp_path,
        transport_factory=factory,
        rsync_fn=fake_rsync,
        run_host_provision=True,
    )
    spec = {
        "job_id": "11111111-1111-1111-1111-111111111111",
        "producer": "rdagent",
        "scenario": "fin_factor",
        "data_snapshot": "qlib_cn_stub",
        "runner_target": {
            "type": "remote_ssh",
            "host": "1.2.3.4",
            "user": "ubuntu",
            "ssh_key_ref": None,
        },
        "llm": {"api_key_ref": "env:LLM_API_KEY"},
        "callback": {"hmac_key_ref": "env:RUNNER_CALLBACK_SECRET"},
    }
    runtime = prov.start("11111111-1111-1111-1111-111111111111", spec)
    assert runtime["type"] == "remote_ssh"
    assert runtime["container_id"] == "sha256:deadbeef"
    assert rsync_calls
    assert prov.is_alive(runtime)
    events = "\n".join(
        [
            json.dumps(
                {
                    "schema_version": "1.0",
                    "job_id": "11111111-1111-1111-1111-111111111111",
                    "type": "heartbeat",
                    "ts": datetime.now(UTC).isoformat(),
                    "seq": 1,
                    "loop": 1,
                    "best_ic": 0.01,
                    "llm_cost_usd": 0.1,
                }
            )
        ]
    )
    fake.files[f"{runtime['remote_work_dir']}/events.jsonl"] = events
    text = prov.fetch_events_jsonl(runtime)
    assert text and "heartbeat" in text
    prov.cleanup(runtime)
    assert any("rm -rf" in c for c in fake.commands)


def test_create_remote_job_and_probe_replay():
    fake = FakeTransport()

    def factory(host, user, key, port):
        return fake

    remote = RemoteSSHProvisioner(
        transport_factory=factory,
        run_host_provision=False,
        rsync_fn=lambda *a, **k: None,
    )
    with _session() as session:
        svc = ResearchService(
            FakeMarket(),
            remote_provisioner=remote,
            settings=ResearchSettings(
                callback_base_host="http://127.0.0.1:8000",
                cleanup_remote_on_complete=False,
            ),
        )
        job = svc.create_job(
            session,
            producer="rdagent",
            runner_type="remote_ssh",
            ssh_host="10.0.0.1",
            ssh_user="ubuntu",
            ssh_key_ref=None,
            max_loops=2,
        )
        assert job["runner_target"]["type"] == "remote_ssh"
        out = svc.start_job(session, job["id"])
        assert out["status"] == "running"
        assert out["runtime"]["type"] == "remote_ssh"

        # 模拟 webhook 丢失:写远端 events,心跳过期,进程仍死 → 补账后若仍 stale 则 lost
        from signal_research import repo

        j = repo.get_job(session, job["id"])
        assert j is not None
        ev_line = RunnerEvent(
            job_id=UUID(job["id"]),
            type=RunnerEventType.LOOP_DONE,
            ts=datetime(2020, 1, 1, tzinfo=UTC),
            seq=9,
            loop=2,
            best_ic=0.03,
            llm_cost_usd=0.2,
        ).model_dump(mode="json")
        fake.files[f"{j.runtime['remote_work_dir']}/events.jsonl"] = json.dumps(ev_line)
        j.last_heartbeat_at = datetime(2020, 1, 1, tzinfo=UTC)
        session.commit()
        fake.alive = False

        marked = svc.probe_lost_jobs(session)
        # 补账后心跳仍是 2020 → 应标记 lost
        assert job["id"] in marked
        # 事件已入库
        events = repo.list_events(session, job["id"])
        assert any(e.seq == 9 for e in events)
