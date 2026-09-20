"""tracker 表的读写。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from signal_tracker.models import Recommendation, RecPerformance, Source, utcnow


def get_or_create_source(session: Session, name: str, channel: str = "wechat") -> Source:
    src = session.execute(select(Source).where(Source.name == name)).scalar_one_or_none()
    if src:
        return src
    src = Source(name=name, channel=channel)
    session.add(src)
    session.flush()
    return src


def insert_recommendation(session: Session, **kwargs) -> Recommendation:
    rec = Recommendation(**kwargs)
    session.add(rec)
    session.flush()
    return rec


def find_duplicate(
    session: Session, source_id: str, message_time: datetime | None, raw_text: str
) -> Recommendation | None:
    """简单去重:同来源 + 同原文。"""
    q: Select = select(Recommendation).where(
        Recommendation.source_id == source_id, Recommendation.raw_text == raw_text
    )
    if message_time is not None:
        q = q.where(Recommendation.message_time == message_time)
    return session.execute(q.limit(1)).scalars().first()


def list_recommendations(
    session: Session,
    *,
    source_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> Sequence[Recommendation]:
    q = select(Recommendation).order_by(Recommendation.message_time.desc()).limit(limit)
    if source_id:
        q = q.where(Recommendation.source_id == source_id)
    if status:
        q = q.where(Recommendation.status == status)
    return session.execute(q).scalars().all()


def get_recommendation(session: Session, rec_id: str) -> Recommendation | None:
    return session.get(Recommendation, rec_id)


def upsert_performance(session: Session, recommendation_id: str, rows: list[dict]) -> int:
    """按 (recommendation_id, window_days) 幂等更新。"""
    if not rows:
        return 0
    import uuid

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise NotImplementedError(dialect)
    for r in rows:
        payload = {
            **r,
            "id": str(uuid.uuid4()),
            "recommendation_id": recommendation_id,
            "updated_at": utcnow(),
        }
        stmt = insert(RecPerformance).values(payload)
        update_cols = {
            c.name: getattr(stmt.excluded, c.name)
            for c in RecPerformance.__table__.columns
            if c.name not in ("id", "recommendation_id", "window_days")
        }
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["recommendation_id", "window_days"], set_=update_cols
            )
        )
    return len(rows)


def get_performances(session: Session, recommendation_id: str) -> Sequence[RecPerformance]:
    return (
        session.execute(
            select(RecPerformance)
            .where(RecPerformance.recommendation_id == recommendation_id)
            .order_by(RecPerformance.window_days)
        )
        .scalars()
        .all()
    )


def source_stats(session: Session, window_days: int = 5) -> list[dict]:
    """机构排行:按窗口胜率与平均超额收益(Python 侧聚合,跨方言可靠)。

    胜率按方向计:买入后上涨 / 卖出后下跌 记为胜;hold/watch 不计入。
    """
    q = (
        select(
            Source.id,
            Source.name,
            Recommendation.action,
            RecPerformance.abs_return,
            RecPerformance.excess_return,
        )
        .join(Recommendation, Recommendation.source_id == Source.id)
        .join(RecPerformance, RecPerformance.recommendation_id == Recommendation.id)
        .where(
            RecPerformance.window_days == window_days,
            RecPerformance.abs_return.is_not(None),
            Recommendation.confidence == "explicit",
            Recommendation.status == "active",
            Recommendation.action.in_(("buy", "sell")),
        )
    )
    buckets: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum_abs": 0.0, "sum_excess": 0.0, "excess_n": 0, "name": ""}
    )
    for sid, name, action, abs_r, excess in session.execute(q):
        b = buckets[sid]
        b["name"] = name
        b["n"] += 1
        signed = float(abs_r) if action == "buy" else -float(abs_r)
        b["sum_abs"] += signed
        if signed > 0:
            b["wins"] += 1
        if excess is not None:
            signed_ex = float(excess) if action == "buy" else -float(excess)
            b["sum_excess"] += signed_ex
            b["excess_n"] += 1
    out = []
    for sid, b in buckets.items():
        out.append(
            {
                "source_id": sid,
                "name": b["name"],
                "n": b["n"],
                "avg_abs": b["sum_abs"] / b["n"] if b["n"] else None,
                "avg_excess": b["sum_excess"] / b["excess_n"] if b["excess_n"] else None,
                "win_rate": b["wins"] / b["n"] if b["n"] else None,
            }
        )
    out.sort(key=lambda x: (x["avg_excess"] is not None, x["avg_excess"] or -999), reverse=True)
    return out
