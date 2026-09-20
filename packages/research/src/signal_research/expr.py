"""轻量 Qlib 风格因子表达式解释器(主平台侧,不装 Qlib)。

支持常用子集:
  $close / $open / $high / $low / $volume
  Ref(x, n)   — 滞后 n 期
  Mean(x, n)  — 滚动均值
  Std(x, n)   — 滚动标准差
  Rank(x)     — 截面排名(0~1),单票时退化为自身
  Abs / Log / Sign
  四则运算与括号
"""

from __future__ import annotations

import ast
import operator
from typing import Any

import pandas as pd

_ALLOWED_FIELDS = {"close", "open", "high", "low", "volume", "amount"}

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class ExprError(ValueError):
    pass


def eval_expression(expr: str, bars: pd.DataFrame) -> pd.Series:
    """对单票 OHLCV DataFrame 求值,返回与 bars 对齐的 Series。"""
    if bars.empty:
        return pd.Series(dtype=float)
    try:
        tree = ast.parse(expr.replace("$", ""), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"表达式语法错误: {e}") from e
    result = _eval_node(tree.body, bars)
    if isinstance(result, pd.Series):
        return result
    if isinstance(result, (int, float)):
        return pd.Series([float(result)] * len(bars), index=bars.index)
    return pd.Series(result, dtype=float)


def _series(bars: pd.DataFrame, name: str) -> pd.Series:
    if name not in _ALLOWED_FIELDS:
        raise ExprError(f"未知字段: {name}")
    if name not in bars.columns:
        raise ExprError(f"bars 缺少列: {name}")
    return pd.Series(bars[name], dtype=float)


def _eval_node(node: ast.AST, bars: pd.DataFrame) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, bars)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        return _series(bars, node.id)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_node(node.left, bars), _eval_node(node.right, bars))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand, bars))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _call(node.func.id, [_eval_node(a, bars) for a in node.args], bars)
    raise ExprError(f"不支持的语法: {ast.dump(node)}")


def _as_series(x: Any) -> pd.Series:
    return x if isinstance(x, pd.Series) else pd.Series(x, dtype=float)


def _call(name: str, args: list[Any], bars: pd.DataFrame) -> pd.Series:
    name_l = name.lower()
    aliases = {
        "ref": "Ref",
        "mean": "Mean",
        "std": "Std",
        "rank": "Rank",
        "abs": "Abs",
        "log": "Log",
        "sign": "Sign",
    }
    key = aliases.get(name_l, name[0].upper() + name[1:] if name else name)
    if key == "Ref":
        if len(args) != 2:
            raise ExprError("Ref(x, n) 需要 2 个参数")
        x, n = _as_series(args[0]), int(args[1])
        return _as_series(x.shift(n))
    if key == "Mean":
        x, n = _as_series(args[0]), int(args[1])
        return _as_series(x.rolling(n, min_periods=1).mean())
    if key == "Std":
        x, n = _as_series(args[0]), int(args[1])
        return _as_series(x.rolling(n, min_periods=1).std())
    if key == "Rank":
        return _as_series(_as_series(args[0]).rank(pct=True))
    if key == "Abs":
        return _as_series(_as_series(args[0]).abs())
    if key == "Log":
        import math

        return _as_series(
            _as_series(args[0]).map(lambda v: float("nan") if v <= 0 else math.log(float(v)))
        )
    if key == "Sign":

        def _sign(v: float) -> float:
            if v == 0:
                return 0.0
            return 1.0 if v > 0 else -1.0

        return _as_series(_as_series(args[0]).map(lambda v: _sign(float(v))))
    raise ExprError(f"未知函数: {name}")
