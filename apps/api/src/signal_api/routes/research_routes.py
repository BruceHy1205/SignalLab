from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from signal_research import repo
from signal_research.service import ResearchService, ResearchSettings
from sqlalchemy.orm import Session

from signal_api.adapters.research_market import ResearchMarketAdapter
from signal_api.config import ApiSettings
from signal_api.db import get_session, make_session

router = APIRouter()


def _hmac_secret(settings: ApiSettings) -> str:
    return (
        os.environ.get("RUNNER_CALLBACK_SECRET") or settings.runner_callback_secret or "dev-secret"
    )


def _svc() -> ResearchService:
    settings = ApiSettings()
    return ResearchService(
        market=ResearchMarketAdapter(make_session),
        settings=ResearchSettings(
            callback_base_host=settings.research_callback_host,
            hmac_secret_env="RUNNER_CALLBACK_SECRET",
            llm_api_key_env="LLM_API_KEY",
            llm_provider="deepseek",
            llm_model=settings.llm_model,
            llm_base_url=settings.llm_base_url,
            default_max_loops=settings.research_default_max_loops,
            artifacts_dir=settings.research_artifacts_dir,
            heartbeat_timeout_sec=settings.research_heartbeat_timeout_sec,
            data_snapshots_dir=settings.research_data_snapshots_dir,
            remote_runner_image=settings.research_remote_image,
            alphaagent_image=settings.research_alphaagent_image,
            rdagent_image=settings.research_rdagent_image,
            runner_backend=settings.research_runner_backend,
            remote_work_root=settings.research_remote_work_root,
            ssh_port=settings.research_ssh_port,
            remote_reverse_tunnel=settings.research_remote_reverse_tunnel,
            cleanup_remote_on_complete=settings.research_cleanup_remote_on_complete,
        ),
    )


class CreateJobReq(BaseModel):
    producer: str = Field(default="alphaagent", description="alphaagent | rdagent")
    scenario: str = "fin_factor"
    data_snapshot: str = "qlib_cn_stub"
    max_loops: int = Field(default=3, ge=1, le=50)
    # local_docker | remote_ssh
    runner_type: str = "local_docker"
    ssh_host: str | None = None
    ssh_user: str | None = None
    ssh_key_ref: str | None = Field(default=None, description="env:VAR,默认 env:RUNNER_SSH_KEY")


class StartJobReq(BaseModel):
    use_docker: bool = False
    use_remote: bool | None = None


class GenSignalsReq(BaseModel):
    trade_date: date


@router.post("/jobs")
def create_job(req: CreateJobReq) -> dict:
    if req.runner_type not in ("local_docker", "remote_ssh"):
        raise HTTPException(400, "runner_type 须为 local_docker 或 remote_ssh")
    if req.runner_type == "remote_ssh" and not (req.ssh_host and req.ssh_user):
        raise HTTPException(400, "remote_ssh 需要 ssh_host 与 ssh_user")
    svc = _svc()
    with make_session() as s:
        try:
            return svc.create_job(
                s,
                producer=req.producer,
                scenario=req.scenario,
                data_snapshot=req.data_snapshot,
                max_loops=req.max_loops,
                runner_type=req.runner_type,
                ssh_host=req.ssh_host,
                ssh_user=req.ssh_user,
                ssh_key_ref=req.ssh_key_ref,
            )
        except Exception as e:
            raise HTTPException(400, str(e)) from e


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_session), limit: int = 50) -> list[dict]:
    return [_job(j) for j in repo.list_jobs(session, limit)]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    j = repo.get_job(session, job_id)
    if not j:
        raise HTTPException(404, "not found")
    events = repo.list_events(session, job_id)
    return {
        **_job(j),
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "seq": e.seq,
                "payload": e.payload,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


@router.post("/jobs/{job_id}/start")
def start_job(job_id: str, req: StartJobReq | None = None) -> dict:
    req = req or StartJobReq()
    svc = _svc()
    with make_session() as s:
        try:
            return svc.start_job(
                s,
                job_id,
                use_docker=req.use_docker,
                use_remote=req.use_remote,
            )
        except KeyError:
            raise HTTPException(404, "not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(500, str(e)) from e


@router.post("/jobs/{job_id}/cleanup")
def cleanup_job(job_id: str) -> dict:
    """手动清理远端容器与工作目录(完成时默认也会自动清理)。"""
    svc = _svc()
    with make_session() as s:
        try:
            return svc.cleanup_job(s, job_id)
        except KeyError:
            raise HTTPException(404, "not found") from None


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    svc = _svc()
    with make_session() as s:
        try:
            return svc.retry_job(s, job_id)
        except KeyError:
            raise HTTPException(404, "not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/jobs/{job_id}/events")
async def post_event(
    job_id: str,
    request: Request,
    x_signal_signature: str = Header(alias="X-Signal-Signature"),
) -> dict:
    body = await request.body()
    svc = _svc()
    secret = _hmac_secret(ApiSettings())
    with make_session() as s:
        try:
            return svc.handle_event(s, job_id, body, x_signal_signature, secret)
        except PermissionError:
            raise HTTPException(401, "bad signature") from None
        except KeyError:
            raise HTTPException(404, "not found") from None
        except Exception as e:
            raise HTTPException(400, str(e)) from e


@router.post("/jobs/{job_id}/complete")
async def post_complete(
    job_id: str,
    request: Request,
    x_signal_signature: str = Header(alias="X-Signal-Signature"),
) -> dict:
    body = await request.body()
    svc = _svc()
    secret = _hmac_secret(ApiSettings())
    with make_session() as s:
        try:
            out = svc.handle_complete(s, job_id, body, x_signal_signature, secret)
        except PermissionError:
            raise HTTPException(401, "bad signature") from None
        except KeyError:
            raise HTTPException(404, "not found") from None
        except Exception as e:
            raise HTTPException(400, str(e)) from e
    from signal_api.notify_util import get_notify

    get_notify().notify_research_complete(
        job_id, str(out.get("status") or ""), summary="job finished"
    )
    return out


@router.put("/jobs/{job_id}/artifact")
async def put_artifact(
    job_id: str,
    request: Request,
    x_signal_signature: str | None = Header(default=None, alias="X-Signal-Signature"),
) -> dict:
    data = await request.body()
    svc = _svc()
    secret = _hmac_secret(ApiSettings())
    with make_session() as s:
        try:
            return svc.handle_artifact(s, job_id, data, x_signal_signature, secret)
        except PermissionError:
            raise HTTPException(401, "bad signature") from None
        except KeyError:
            raise HTTPException(404, "not found") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/probe-lost")
def probe_lost() -> dict:
    svc = _svc()
    with make_session() as s:
        marked = svc.probe_lost_jobs(s)
    return {"lost": marked}


@router.get("/strategies")
def list_strategies(session: Session = Depends(get_session), limit: int = 50) -> list[dict]:
    return [_strat(s) for s in repo.list_strategies(session, limit)]


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str, session: Session = Depends(get_session)) -> dict:
    s = repo.get_strategy(session, strategy_id)
    if not s:
        raise HTTPException(404, "not found")
    return _strat(s, full=True)


@router.post("/strategies/{strategy_id}/signals")
def gen_signals(strategy_id: str, req: GenSignalsReq) -> dict:
    svc = _svc()
    with make_session() as s:
        try:
            return svc.generate_signals(s, strategy_id, req.trade_date)
        except KeyError:
            raise HTTPException(404, "not found") from None


@router.get("/strategies/{strategy_id}/signals")
def list_signals(
    strategy_id: str,
    trade_date: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    return [
        {
            "symbol": x.symbol,
            "trade_date": x.trade_date,
            "score": x.score,
            "action": x.action,
        }
        for x in repo.list_strategy_signals(session, strategy_id, trade_date)
    ]


def _job(j) -> dict:
    return {
        "id": j.id,
        "status": j.status,
        "producer": j.producer,
        "scenario": j.scenario,
        "data_snapshot": j.data_snapshot,
        "last_loop": j.last_loop,
        "best_ic": j.best_ic,
        "llm_cost_usd": j.llm_cost_usd,
        "error": j.error,
        "strategy_id": j.strategy_id,
        "last_heartbeat_at": j.last_heartbeat_at,
        "created_at": j.created_at,
        "finished_at": j.finished_at,
        "runtime": j.runtime,
        "runner_target": (j.spec or {}).get("runner_target"),
    }


def _strat(s, full: bool = False) -> dict:
    out = {
        "id": s.id,
        "package_id": s.package_id,
        "job_id": s.job_id,
        "producer": s.producer,
        "name": s.name,
        "universe": s.universe,
        "metrics": s.metrics,
        "verified_metrics": s.verified_metrics,
        "status": s.status,
        "created_at": s.created_at,
    }
    if full:
        out["manifest"] = s.manifest
        out["signal_protocol"] = s.signal_protocol
    return out
