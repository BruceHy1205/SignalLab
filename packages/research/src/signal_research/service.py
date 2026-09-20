"""研究任务服务:创建 → 供给 → 收事件 → 导入策略 → 失联探测/补账 → 远端清理。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from signal_contracts.research_job import (
    ArtifactUpload,
    ArtifactUploadType,
    Budget,
    CallbackConfig,
    LlmConfig,
    ResearchJobSpec,
    RunnerTarget,
    RunnerTargetType,
)
from signal_contracts.runner_events import (
    CompletionReport,
    RunnerEvent,
    verify_signature,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_research import repo
from signal_research.models import Strategy
from signal_research.ports import MarketBarsPort
from signal_research.provisioners import (
    LocalDockerProvisioner,
    LocalProcessProvisioner,
    Provisioner,
    RemoteSSHProvisioner,
)
from signal_research.validator import (
    PackageValidationError,
    generate_signals_for_date,
    independent_verify,
    load_package,
)

logger = logging.getLogger(__name__)

SUPPORTED_PRODUCERS = frozenset({"alphaagent", "rdagent"})


@dataclass
class ResearchSettings:
    callback_base_host: str = "http://127.0.0.1:8000"
    hmac_secret_env: str = "RUNNER_CALLBACK_SECRET"
    llm_api_key_env: str = "LLM_API_KEY"
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    default_max_loops: int = 3
    default_max_hours: float = 1.0
    default_max_llm_cost_usd: float = 2.0
    heartbeat_timeout_sec: int = 600  # 2 个 5 分钟心跳周期
    artifacts_dir: str = "/tmp/signal-artifacts"
    runner_script: str = ""  # 空则按 producer 解析;兼容旧配置
    data_snapshots_dir: str = ""  # 本地快照根目录,供 rsync
    remote_runner_image: str = "signal-rdagent:stub"
    alphaagent_image: str = "signal-alphaagent:stub"
    rdagent_image: str = "signal-rdagent:stub"
    runner_backend: str = "stub"  # stub | real
    remote_work_root: str = "/tmp/signal-jobs"
    ssh_port: int = 22
    remote_reverse_tunnel: bool = False
    cleanup_remote_on_complete: bool = True


class ResearchService:
    def __init__(
        self,
        market: MarketBarsPort,
        provisioner: Provisioner | None = None,
        settings: ResearchSettings | None = None,
        remote_provisioner: RemoteSSHProvisioner | None = None,
    ) -> None:
        self._market = market
        self._settings = settings or ResearchSettings()
        self._provisioner = provisioner
        self._remote_provisioner = remote_provisioner

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _normalize_producer(self, producer: str) -> str:
        p = (producer or "").strip().lower()
        # 允许 alphaagent@x.y / rdagent@stub 前缀
        base = p.split("@", 1)[0]
        if base not in SUPPORTED_PRODUCERS:
            raise ValueError(
                f"不支持的 producer: {producer!r};可选: {', '.join(sorted(SUPPORTED_PRODUCERS))}"
            )
        return base

    def _runner_script_for(self, producer: str) -> Path:
        if self._settings.runner_script:
            return Path(self._settings.runner_script)
        root = self._repo_root()
        if producer.startswith("rdagent"):
            return root / "runners" / "rdagent" / "runner.py"
        return root / "runners" / "alphaagent" / "runner.py"

    def _default_local_provisioner(self, producer: str = "alphaagent") -> Provisioner:
        if self._provisioner:
            return self._provisioner
        return LocalProcessProvisioner(
            self._runner_script_for(producer),
            runner_backend=self._settings.runner_backend,
        )

    def _default_docker_provisioner(self) -> LocalDockerProvisioner:
        return LocalDockerProvisioner(
            image=self._settings.remote_runner_image,
            alphaagent_image=self._settings.alphaagent_image,
            rdagent_image=self._settings.rdagent_image,
            runner_backend=self._settings.runner_backend,
        )

    def _default_remote_provisioner(self) -> RemoteSSHProvisioner:
        if self._remote_provisioner:
            return self._remote_provisioner
        snap = (
            Path(self._settings.data_snapshots_dir) if self._settings.data_snapshots_dir else None
        )
        return RemoteSSHProvisioner(
            image=self._settings.rdagent_image or self._settings.remote_runner_image,
            alphaagent_image=self._settings.alphaagent_image,
            rdagent_image=self._settings.rdagent_image or self._settings.remote_runner_image,
            remote_work_root=self._settings.remote_work_root,
            data_snapshots_dir=snap,
            ssh_port=self._settings.ssh_port,
            reverse_tunnel=self._settings.remote_reverse_tunnel,
            runner_backend=self._settings.runner_backend,
        )

    def _provisioner_for_runtime(
        self, runtime: dict | None, spec: dict | None = None
    ) -> Provisioner:
        rtype = (runtime or {}).get("type")
        if not rtype and spec:
            rtype = (spec.get("runner_target") or {}).get("type")
        producer = (spec or {}).get("producer") or "alphaagent"
        if rtype == "remote_ssh":
            return self._default_remote_provisioner()
        if rtype == "local_docker":
            return self._default_docker_provisioner()
        return self._default_local_provisioner(str(producer))

    def create_job(
        self,
        session: Session,
        *,
        producer: str = "alphaagent",
        scenario: str = "fin_factor",
        data_snapshot: str = "qlib_cn_stub",
        max_loops: int | None = None,
        runner_type: str = "local_docker",
        ssh_host: str | None = None,
        ssh_user: str | None = None,
        ssh_key_ref: str | None = None,
    ) -> dict:
        producer = self._normalize_producer(producer)
        job_id = uuid4()
        host = self._settings.callback_base_host.rstrip("/")
        base = f"{host}/api/research/jobs/{job_id}"

        if runner_type == RunnerTargetType.REMOTE_SSH.value:
            target = RunnerTarget(
                type=RunnerTargetType.REMOTE_SSH,
                host=ssh_host,
                user=ssh_user,
                ssh_key_ref=ssh_key_ref,
            )
        else:
            target = RunnerTarget(type=RunnerTargetType.LOCAL_DOCKER)

        spec = ResearchJobSpec(
            job_id=job_id,
            producer=producer,
            scenario=scenario,
            runner_target=target,
            llm=LlmConfig(
                provider=self._settings.llm_provider,
                model=self._settings.llm_model,
                base_url=self._settings.llm_base_url,
                api_key_ref=f"env:{self._settings.llm_api_key_env}",
            ),
            budget=Budget(
                max_loops=max_loops or self._settings.default_max_loops,
                max_hours=self._settings.default_max_hours,
                max_llm_cost_usd=self._settings.default_max_llm_cost_usd,
            ),
            data_snapshot=data_snapshot,
            callback=CallbackConfig(
                base_url=base,
                hmac_key_ref=f"env:{self._settings.hmac_secret_env}",
            ),
            artifact_upload=ArtifactUpload(
                type=ArtifactUploadType.HTTP_PUT,
                url=f"{base}/artifact",
            ),
        )
        job = repo.create_job(
            session,
            producer=producer,
            scenario=scenario,
            data_snapshot=data_snapshot,
            spec=spec.model_dump(mode="json"),
        )
        # 确保 id 与 spec 一致
        job.id = str(job_id)
        job.spec = spec.model_dump(mode="json")
        session.commit()
        return self._job_dict(job)

    def start_job(
        self,
        session: Session,
        job_id: str,
        *,
        use_docker: bool = False,
        use_remote: bool | None = None,
    ) -> dict:
        job = repo.get_job(session, job_id)
        if not job:
            raise KeyError(job_id)
        if job.status not in ("draft", "lost", "failed"):
            raise ValueError(f"状态 {job.status} 不可启动")
        repo.set_status(session, job, "provisioning")
        session.commit()

        target_type = (job.spec.get("runner_target") or {}).get("type")
        producer = str(job.producer or (job.spec or {}).get("producer") or "alphaagent")
        if use_remote is True or (use_remote is None and target_type == "remote_ssh"):
            provisioner: Provisioner = self._default_remote_provisioner()
        elif use_docker:
            provisioner = self._default_docker_provisioner()
        else:
            # 默认本地进程冒烟(即便 spec.runner_target=local_docker)
            provisioner = self._default_local_provisioner(producer)

        try:
            runtime = provisioner.start(job.id, job.spec)
        except Exception as e:
            repo.set_status(session, job, "failed", error=str(e)[:500], finished=True)
            session.commit()
            raise

        repo.update_runtime(session, job, **runtime)
        repo.set_status(session, job, "running")
        repo.touch_heartbeat(session, job)
        session.commit()
        return self._job_dict(job)

    def handle_event(
        self,
        session: Session,
        job_id: str,
        body: bytes,
        signature: str,
        hmac_secret: str,
    ) -> dict:
        if not verify_signature(hmac_secret, body, signature):
            raise PermissionError("invalid signature")
        event = RunnerEvent.model_validate_json(body)
        if str(event.job_id) != job_id:
            raise ValueError("job_id mismatch")
        return self._ingest_event(session, job_id, event)

    def _ingest_event(self, session: Session, job_id: str, event: RunnerEvent) -> dict:
        job = repo.get_job(session, job_id)
        if not job:
            raise KeyError(job_id)

        inserted = repo.append_event(
            session,
            job_id,
            type=event.type.value,
            seq=event.seq,
            payload=event.model_dump(mode="json"),
        )
        repo.touch_heartbeat(
            session,
            job,
            loop=event.loop,
            best_ic=event.best_ic,
            llm_cost_usd=event.llm_cost_usd,
            at=event.ts if event.ts.tzinfo else event.ts.replace(tzinfo=UTC),
        )
        if job.status == "provisioning":
            repo.set_status(session, job, "running")
        session.commit()
        return {"accepted": True, "duplicate": inserted is None}

    def replay_events_jsonl(self, session: Session, job_id: str, text: str) -> int:
        """把远端 events.jsonl 补账入库(幂等按 seq)。"""
        n = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            # 跳过 reporter 内部错误行
            if "_send_error" in payload or "_complete" in payload:
                # complete 行也可尝试
                if "_complete" in payload and isinstance(payload["_complete"], dict):
                    continue
                continue
            if "job_id" not in payload or "type" not in payload or "seq" not in payload:
                continue
            try:
                event = RunnerEvent.model_validate(payload)
            except Exception:
                continue
            if str(event.job_id) != job_id:
                continue
            r = self._ingest_event(session, job_id, event)
            if not r.get("duplicate"):
                n += 1
        return n

    def handle_complete(
        self,
        session: Session,
        job_id: str,
        body: bytes,
        signature: str,
        hmac_secret: str,
    ) -> dict:
        if not verify_signature(hmac_secret, body, signature):
            raise PermissionError("invalid signature")
        report = CompletionReport.model_validate_json(body)
        if str(report.job_id) != job_id:
            raise ValueError("job_id mismatch")
        job = repo.get_job(session, job_id)
        if not job:
            raise KeyError(job_id)

        status = report.status.value
        repo.set_status(session, job, status, finished=True)
        job.llm_cost_usd = report.total_llm_cost_usd
        job.last_loop = report.total_loops
        if report.package_id and status in ("succeeded", "budget_exceeded"):
            # 策略应已通过 artifact 上传入库;此处仅关联
            strat = session.execute(
                select(Strategy).where(Strategy.package_id == str(report.package_id))
            ).scalar_one_or_none()
            if strat:
                job.strategy_id = strat.id
        session.commit()

        if self._settings.cleanup_remote_on_complete:
            self._maybe_cleanup_remote(job)

        return {"ok": True, "status": status}

    def _maybe_cleanup_remote(self, job) -> None:
        runtime = job.runtime or {}
        if runtime.get("type") != "remote_ssh":
            return
        try:
            self._default_remote_provisioner().cleanup(runtime)
            logger.info("remote cleanup done for job %s", job.id)
        except Exception as e:
            logger.warning("remote cleanup failed for %s: %s", job.id, e)

    def cleanup_job(self, session: Session, job_id: str) -> dict:
        job = repo.get_job(session, job_id)
        if not job:
            raise KeyError(job_id)
        provisioner = self._provisioner_for_runtime(job.runtime, job.spec)
        provisioner.cleanup(job.runtime or {})
        return {"ok": True, "job_id": job_id}

    def handle_artifact(
        self,
        session: Session,
        job_id: str,
        data: bytes,
        signature: str | None,
        hmac_secret: str,
    ) -> dict:
        if signature and not verify_signature(hmac_secret, data, signature):
            raise PermissionError("invalid signature")
        job = repo.get_job(session, job_id)
        if not job:
            raise KeyError(job_id)

        art_dir = Path(self._settings.artifacts_dir)
        art_dir.mkdir(parents=True, exist_ok=True)
        path = art_dir / f"{job_id}.zip"
        path.write_bytes(data)

        try:
            contents = load_package(data)
        except PackageValidationError as e:
            raise ValueError(str(e)) from e

        # 抽样行情做独立复算
        symbols = self._market.list_universe_symbols(contents.manifest.universe, limit=10)
        end = date.today()
        start = end - timedelta(days=120)
        bars_map = {}
        for s in symbols:
            df = self._market.get_qfq_bars(s, start, end)
            if df is not None and not df.empty:
                bars_map[s] = df
        verify = independent_verify(contents, bars_map)
        if not verify.ok:
            raise ValueError(f"独立复算未通过: {verify.reason}")

        strat = repo.insert_strategy(
            session,
            package_id=str(contents.manifest.package_id),
            job_id=job_id,
            producer=contents.manifest.producer,
            name=contents.manifest.factors[0].name,
            universe=contents.manifest.universe,
            data_snapshot=contents.manifest.data_snapshot,
            signal_protocol=contents.manifest.signal_protocol.value,
            manifest=contents.raw_manifest,
            metrics=contents.manifest.metrics_summary.model_dump(),
            verified_metrics=verify.verified_metrics,
        )
        job.strategy_id = strat.id
        session.commit()
        return {"ok": True, "strategy_id": strat.id, "package_id": strat.package_id}

    def probe_lost_jobs(self, session: Session) -> list[str]:
        """心跳超时且进程/容器已死 → 尝试补账 events.jsonl → 仍无进展则 lost。"""
        marked: list[str] = []
        timeout = timedelta(seconds=self._settings.heartbeat_timeout_sec)
        now = datetime.now(UTC)
        for job in repo.list_running_jobs(session):
            hb = job.last_heartbeat_at
            if hb and hb.tzinfo is None:
                hb = hb.replace(tzinfo=UTC)
            stale = hb is None or (now - hb) > timeout
            if not stale:
                continue

            provisioner = self._provisioner_for_runtime(job.runtime, job.spec)
            # webhook 丢失兜底:先拉回 events.jsonl 补账
            try:
                text = provisioner.fetch_events_jsonl(job.runtime or {})
                if text:
                    self.replay_events_jsonl(session, job.id, text)
                    session.refresh(job)
                    hb2 = job.last_heartbeat_at
                    if hb2 and hb2.tzinfo is None:
                        hb2 = hb2.replace(tzinfo=UTC)
                    if hb2 and (now - hb2) <= timeout:
                        continue
            except Exception as e:
                logger.warning("replay events failed for %s: %s", job.id, e)

            alive = provisioner.is_alive(job.runtime or {})
            if not alive:
                repo.set_status(session, job, "lost", error="heartbeat timeout", finished=True)
                marked.append(job.id)
        session.commit()
        return marked

    def retry_job(self, session: Session, job_id: str) -> dict:
        job = repo.get_job(session, job_id)
        if not job:
            raise KeyError(job_id)
        if job.status != "lost":
            raise ValueError("仅 lost 状态可重试")
        return self.start_job(session, job_id)

    def generate_signals(self, session: Session, strategy_id: str, trade_date: date) -> dict:
        from signal_contracts.strategy_package import StrategyManifest

        from signal_research.validator import PackageContents

        strat = repo.get_strategy(session, strategy_id)
        if not strat:
            raise KeyError(strategy_id)
        manifest = StrategyManifest.model_validate(strat.manifest)
        contents = PackageContents(
            manifest=manifest,
            raw_manifest=strat.manifest,
            factors=[f.model_dump() for f in manifest.factors],
        )
        symbols = self._market.list_universe_symbols(strat.universe, limit=20)
        start = trade_date - timedelta(days=90)
        bars_map = {}
        for s in symbols:
            df = self._market.get_qfq_bars(s, start, trade_date)
            if df is not None and not df.empty:
                bars_map[s] = df
        rows = generate_signals_for_date(contents, bars_map, trade_date)
        n = repo.upsert_strategy_signals(session, strategy_id, rows)
        session.commit()
        return {"count": n, "signals": rows}

    def _job_dict(self, job) -> dict:
        return {
            "id": job.id,
            "status": job.status,
            "producer": job.producer,
            "scenario": job.scenario,
            "data_snapshot": job.data_snapshot,
            "last_loop": job.last_loop,
            "best_ic": job.best_ic,
            "llm_cost_usd": job.llm_cost_usd,
            "error": job.error,
            "strategy_id": job.strategy_id,
            "last_heartbeat_at": job.last_heartbeat_at,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
            "runtime": job.runtime,
            "runner_target": (job.spec or {}).get("runner_target"),
        }
