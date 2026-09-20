"""股票代码规范化:全系统统一使用 `600519.SH` 形式。"""

from __future__ import annotations

import re

_CODE_RE = re.compile(r"^\d{6}$")
_FULL_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")

# 常见指数:裸代码无法用首位规则推断交易所
# 注意:000001 有歧义(上证指数.SH / 平安银行.SZ),不收入;请写全 000001.SH
_INDEX_EXCHANGE = {
    "000016": "SH",  # 上证50
    "000300": "SH",  # 沪深300
    "000905": "SH",  # 中证500
    "000852": "SH",  # 中证1000
    "399001": "SZ",  # 深证成指
    "399006": "SZ",  # 创业板指
}

# 规范 symbol 集合;个股日线接口拉不到这些,需走指数通道
INDEX_SYMBOLS = frozenset(f"{code}.{ex}" for code, ex in _INDEX_EXCHANGE.items())
# 超额收益 / 模拟盘基准
BENCHMARK_SYMBOL = "000300.SH"


def normalize_symbol(raw: str) -> str:
    """接受 '600519' / '600519.SH' / 'sh600519' 等形式,输出 '600519.SH'。"""
    s = raw.strip().upper()
    if m := _FULL_RE.match(s):
        return f"{m.group(1)}.{m.group(2)}"
    if m := re.match(r"^(SH|SZ|BJ)(\d{6})$", s):
        return f"{m.group(2)}.{m.group(1)}"
    if _CODE_RE.match(s):
        return f"{s}.{_infer_exchange(s)}"
    raise ValueError(f"无法识别的股票代码: {raw!r}")


def is_index_symbol(symbol: str) -> bool:
    """是否为已知指数代码(需走指数行情接口)。"""
    try:
        return normalize_symbol(symbol) in INDEX_SYMBOLS
    except ValueError:
        return False


def _infer_exchange(code6: str) -> str:
    if code6 in _INDEX_EXCHANGE:
        return _INDEX_EXCHANGE[code6]
    head = code6[0]
    if head == "6":
        return "SH"
    if head in ("0", "3"):
        return "SZ"
    if head in ("4", "8", "9"):
        return "BJ"
    raise ValueError(f"无法推断交易所: {code6}")


def bare_code(symbol: str) -> str:
    """'600519.SH' -> '600519'(部分外部 API 只吃 6 位代码)。"""
    if m := _FULL_RE.match(symbol):
        return m.group(1)
    raise ValueError(f"非规范代码: {symbol!r}")


def to_qlib_code(symbol: str) -> str:
    """'600519.SH' -> 'sh600519'(Qlib dump_bin 目录名约定)。"""
    s = normalize_symbol(symbol)
    m = _FULL_RE.match(s)
    assert m
    return f"{m.group(2).lower()}{m.group(1)}"


def from_qlib_code(code: str) -> str:
    """'sh600519' -> '600519.SH'。"""
    s = code.strip().lower()
    m = re.match(r"^(sh|sz|bj)(\d{6})$", s)
    if not m:
        raise ValueError(f"非法 qlib code: {code!r}")
    return f"{m.group(2)}.{m.group(1).upper()}"
