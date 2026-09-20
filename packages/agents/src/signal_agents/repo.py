"""agents 表读写。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_agents.models import AgentRun, Signal, utcnow


def create_run(session: Session, model: str, candidate_count: int) -> AgentRun:
    run = AgentRun(model=model, candidate_count=candidate_count, status="running")
    session.add(run)
    session.flush()
    return run


def finish_run(
    session: Session, run: AgentRun, status: str, llm_cost_usd: float = 0.0, error: str = ""
) -> None:
    run.status = status
    run.llm_cost_usd = llm_cost_usd
    run.error = error
    run.finished_at = utcnow()


def insert_signal(session: Session, **kwargs) -> Signal:
    sig = Signal(**kwargs)
    session.add(sig)
    session.flush()
    return sig


def list_runs(session: Session, limit: int = 20) -> Sequence[AgentRun]:
    return (
        session.execute(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))
        .scalars()
        .all()
    )


def get_run(session: Session, run_id: str) -> AgentRun | None:
    return session.get(AgentRun, run_id)


def list_signals(session: Session, run_id: str | None = None, limit: int = 100) -> Sequence[Signal]:
    q = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
    if run_id:
        q = q.where(Signal.run_id == run_id)
    return session.execute(q).scalars().all()


def get_signal(session: Session, signal_id: str) -> Signal | None:
    return session.get(Signal, signal_id)
