"""source_stats 方向胜率。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from signal_tracker import repo
from signal_tracker.models import RecPerformance

CN = ZoneInfo("Asia/Shanghai")


def test_source_stats_sell_direction(session):
    """卖出后股价上涨不应记为胜;应用方向取反。"""
    src = repo.get_or_create_source(session, "方向测试")
    buy = repo.insert_recommendation(
        session,
        source_id=src.id,
        message_time=datetime(2026, 7, 1, 10, 0, tzinfo=CN),
        symbol="600519.SH",
        symbol_name="贵州茅台",
        action="buy",
        confidence="explicit",
        reason="",
        raw_text="buy",
        status="active",
    )
    sell = repo.insert_recommendation(
        session,
        source_id=src.id,
        message_time=datetime(2026, 7, 1, 11, 0, tzinfo=CN),
        symbol="600519.SH",
        symbol_name="贵州茅台",
        action="sell",
        confidence="explicit",
        reason="",
        raw_text="sell",
        status="active",
    )
    session.add_all(
        [
            RecPerformance(
                recommendation_id=buy.id,
                window_days=5,
                abs_return=0.1,
                excess_return=0.05,
            ),
            RecPerformance(
                recommendation_id=sell.id,
                window_days=5,
                abs_return=0.1,
                excess_return=0.05,
            ),
        ]
    )
    session.commit()
    stats = repo.source_stats(session, window_days=5)
    assert len(stats) == 1
    assert stats[0]["win_rate"] == 0.5
    assert abs(stats[0]["avg_abs"]) < 1e-9
    assert abs(stats[0]["avg_excess"]) < 1e-9
