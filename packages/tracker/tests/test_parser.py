from signal_tracker.parser import parse_paste, parse_wechat_txt


def test_parse_wechat():
    text = """张老师 2026-07-15 09:21:03
今天重点关注茅台,建议逢低吸纳,目标1900

李老师 2026-07-15 15:30:00
宁德时代可以减仓了
"""
    msgs = parse_wechat_txt(text)
    assert len(msgs) == 2
    assert msgs[0].speaker == "张老师"
    assert msgs[0].message_time is not None
    assert msgs[0].message_time.hour == 9
    assert "茅台" in msgs[0].text
    assert msgs[1].message_time is not None
    assert msgs[1].message_time.hour == 15


def test_parse_paste_with_timestamp():
    text = """2026-07-15 10:00
关注茅台

2026-07-16 11:00
卖出五粮液
"""
    msgs = parse_paste(text, "投顾A")
    assert len(msgs) == 2
    assert msgs[0].speaker == "投顾A"
    assert msgs[0].message_time is not None
