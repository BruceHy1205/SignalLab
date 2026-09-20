from signal_tracker.extract import rule_extract
from signal_tracker.resolve import build_name_index, resolve_name


def test_rule_extract_buy():
    recs = rule_extract("今天重点关注茅台,建议逢低吸纳,目标1900,止损1650")
    assert len(recs) == 1
    assert recs[0].symbol_name == "贵州茅台"
    assert recs[0].action == "buy"
    assert recs[0].confidence == "explicit"
    assert recs[0].target_price == 1900
    assert recs[0].stop_loss == 1650


def test_rule_extract_mention():
    recs = rule_extract("今天大盘一般,茅台也没动")
    assert recs[0].confidence == "mention"


def test_resolve_exact_and_fuzzy():
    instruments = [("600519.SH", "贵州茅台"), ("000858.SZ", "五粮液")]
    aliases = {"茅台": "600519.SH"}
    index = build_name_index(aliases, instruments)
    assert resolve_name("茅台", index).status == "resolved"
    assert resolve_name("贵州茅台", index).symbol == "600519.SH"
    assert resolve_name("不存在的票", index).status == "unresolved"
