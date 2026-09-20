import pytest
from signal_datahub.symbols import BENCHMARK_SYMBOL, bare_code, is_index_symbol, normalize_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "600519.SH"),
        ("000001", "000001.SZ"),
        ("000300", "000300.SH"),  # 沪深300指数
        ("300750", "300750.SZ"),
        ("430047", "430047.BJ"),
        ("835185", "835185.BJ"),
        ("600519.SH", "600519.SH"),
        ("600519.sh", "600519.SH"),
        ("sh600519", "600519.SH"),
        (" 600519 ", "600519.SH"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("bad", ["", "abc", "12345", "1234567", "500000"])
def test_normalize_rejects(bad):
    with pytest.raises(ValueError):
        normalize_symbol(bad)


def test_bare_code():
    assert bare_code("600519.SH") == "600519"
    with pytest.raises(ValueError):
        bare_code("600519")


def test_is_index_symbol():
    assert is_index_symbol(BENCHMARK_SYMBOL)
    assert is_index_symbol("000300")
    assert not is_index_symbol("600519.SH")
    assert not is_index_symbol("not-a-symbol")
