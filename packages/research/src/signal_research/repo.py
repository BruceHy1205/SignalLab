"""research 表读写。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_research.models import ResearchEvent, ResearchJob, Strategy, StrategySignal, utcnow


def create_job(
    session: Session,
    *,
    producer: str,
    scenario: str,
    data_snapshot: str,
    spec: dict,
) -> ResearchJob:
    job = ResearchJob(
        id=str(spec.get("job_id") or ""),
        status="draft",
        producer=producer,
        scenario=scenario,
        data_snapshot=data_snapshot,
        spec=spec,
    )
    if not job.id:
        import uuid

        job.id = str(uuid.uuid4())
        spec = {**spec, "job_id": job.id}
        job.spec = spec
    session.add(job)
    session.flush()
    return job


def get_job(session: Session, job_id: str) -> ResearchJob | None:
    return session.get(ResearchJob, job_id)


def list_jobs(session: Session, limit: int = 50) -> Sequence[ResearchJob]:
    return (
        session.execute(select(ResearchJob).order_by(ResearchJob.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )


def set_status(
    session: Session,
    job: ResearchJob,
    status: str,
    *,
    error: str = "",
    finished: bool = False,
) -> None:
    job.status = status
    job.updated_at = utcnow()
    if error:
        job.error = error
    if finished:
        job.finished_at = utcnow()
    session.flush()


def update_runtime(session: Session, job: ResearchJob, **fields) -> None:
    runtime = dict(job.runtime or {})
    runtime.update(fields)
    job.runtime = runtime
    job.updated_at = utcnow()
    session.flush()


def append_event(
    session: Session,
    job_id: str,
    *,
    type: str,
    seq: int,
    payload: dict,
) -> ResearchEvent | None:
    """幂等:同 job_id+seq 已存在则跳过。"""
    existing = session.execute(
        select(ResearchEvent).where(ResearchEvent.job_id == job_id, ResearchEvent.seq == seq)
    ).scalar_one_or_none()
    if existing:
        return None
    ev = ResearchEvent(job_id=job_id, type=type, seq=seq, payload=payload)
    session.add(ev)
    session.flush()
    return ev


def list_events(session: Session, job_id: str, limit: int = 200) -> Sequence[ResearchEvent]:
    return (
        session.execute(
            select(ResearchEvent)
            .where(ResearchEvent.job_id == job_id)
            .order_by(ResearchEvent.seq.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def touch_heartbeat(
    session: Session,
    job: ResearchJob,
    *,
    loop: int | None = None,
    best_ic: float | None = None,
    llm_cost_usd: float | None = None,
    at: datetime | None = None,
) -> None:
    job.last_heartbeat_at = at or utcnow()
    if loop is not None:
        job.last_loop = loop
    if best_ic is not None:
        job.best_ic = best_ic
    if llm_cost_usd is not None:
        job.llm_cost_usd = llm_cost_usd
    job.updated_at = utcnow()
    session.flush()


def insert_strategy(
    session: Session,
    *,
    package_id: str,
    job_id: str | None,
    producer: str,
    name: str,
    universe: str,
    data_snapshot: str,
    signal_protocol: str,
    manifest: dict,
    metrics: dict,
    verified_metrics: dict,
) -> Strategy:
    existing = session.execute(
        select(Strategy).where(Strategy.package_id == package_id)
    ).scalar_one_or_none()
    if existing:
        return existing
    s = Strategy(
        package_id=package_id,
        job_id=job_id,
        producer=producer,
        name=name,
        universe=universe,
        data_snapshot=data_snapshot,
        signal_protocol=signal_protocol,
        manifest=manifest,
        metrics=metrics,
        verified_metrics=verified_metrics,
    )
    session.add(s)
    session.flush()
    return s


def get_strategy(session: Session, strategy_id: str) -> Strategy | None:
    return session.get(Strategy, strategy_id)


def list_strategies(session: Session, limit: int = 50) -> Sequence[Strategy]:
    return (
        session.execute(select(Strategy).order_by(Strategy.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )


def upsert_strategy_signals(session: Session, strategy_id: str, rows: list[dict]) -> int:
    n = 0
    for r in rows:
        existing = session.execute(
            select(StrategySignal).where(
                StrategySignal.strategy_id == strategy_id,
                StrategySignal.trade_date == r["trade_date"],
                StrategySignal.symbol == r["symbol"],
            )
        ).scalar_one_or_none()
        if existing:
            existing.score = r["score"]
            existing.action = r["action"]
        else:
            session.add(
                StrategySignal(
                    strategy_id=strategy_id,
                    trade_date=r["trade_date"],
                    symbol=r["symbol"],
                    score=r["score"],
                    action=r["action"],
                )
            )
        n += 1
    session.flush()
    return n


def list_strategy_signals(
    session: Session, strategy_id: str, trade_date: str | None = None
) -> Sequence[StrategySignal]:
    q = select(StrategySignal).where(StrategySignal.strategy_id == strategy_id)
    if trade_date:
        q = q.where(StrategySignal.trade_date == trade_date)
    return session.execute(q.order_by(StrategySignal.score.desc())).scalars().all()


def list_running_jobs(session: Session) -> Sequence[ResearchJob]:
    return (
        session.execute(
            select(ResearchJob).where(ResearchJob.status.in_(("provisioning", "running")))
        )
        .scalars()
        .all()
    )
