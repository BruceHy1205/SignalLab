from datetime import datetime
from zoneinfo import ZoneInfo

from signal_tracker import repo
from signal_tracker.parser import ChatMessage
from signal_tracker.service import ImportService

CN = ZoneInfo("Asia/Shanghai")


def test_import_and_event_study(session, fake_bars):
    svc = ImportService(fake_bars)
    msgs = [
        ChatMessage(
            speaker="张老师",
            message_time=datetime(2026, 7, 1, 10, 0, tzinfo=CN),
            text="今天重点关注茅台,建议逢低吸纳,目标1900",
            raw_block="张老师 2026-07-01 10:00\n今天重点关注茅台,建议逢低吸纳,目标1900",
        )
    ]
    result = svc.import_messages(session, msgs, source_name="XX投顾")
    assert result["created"] == 1
    assert result["pending"] == 0

    recs = repo.list_recommendations(session)
    assert len(recs) == 1
    assert recs[0].symbol == "600519.SH"
    assert recs[0].baseline_price is not None
    perfs = repo.get_performances(session, recs[0].id)
    assert len(perfs) == 6
    assert any(p.abs_return is not None for p in perfs)

    result2 = svc.import_messages(session, msgs, source_name="XX投顾")
    assert result2["skipped"] == 1

    stats = repo.source_stats(session, window_days=5)
    assert stats and stats[0]["n"] >= 1
