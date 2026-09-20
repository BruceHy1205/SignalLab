"""策略包导入校验:格式 → 独立复算抽样 → 注册。"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

import pandas as pd
from signal_contracts.strategy_package import SignalProtocol, StrategyManifest

from signal_research.expr import ExprError, eval_expression

logger = logging.getLogger(__name__)


@dataclass
class PackageContents:
    manifest: StrategyManifest
    raw_manifest: dict
    factors: list[dict]


@dataclass
class VerifyResult:
    ok: bool
    verified_metrics: dict
    reason: str = ""


class PackageValidationError(ValueError):
    pass


def load_package(source: bytes | str | Path) -> PackageContents:
    """从 zip bytes / 目录路径加载并做格式校验。"""
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_dir():
            manifest_raw = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        elif path.suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                manifest_raw = json.loads(zf.read("manifest.json"))
        else:
            raise PackageValidationError(f"无法识别的策略包路径: {path}")
    else:
        with zipfile.ZipFile(io.BytesIO(source)) as zf:
            names = zf.namelist()
            if "manifest.json" not in names:
                raise PackageValidationError("策略包缺少 manifest.json")
            manifest_raw = json.loads(zf.read("manifest.json"))

    try:
        manifest = StrategyManifest.model_validate(manifest_raw)
    except Exception as e:
        raise PackageValidationError(f"manifest 校验失败: {e}") from e

    if manifest.signal_protocol is SignalProtocol.PYTHON_MODULE:
        raise PackageValidationError("python_module 协议默认禁用,仅接受 qlib_expression")

    factors = [f.model_dump(mode="json") for f in manifest.factors]
    for f in manifest.factors:
        if not f.expression:
            raise PackageValidationError(f"因子 {f.name} 缺少 expression")
    return PackageContents(manifest=manifest, raw_manifest=manifest_raw, factors=factors)


def independent_verify(
    contents: PackageContents,
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    min_ic: float = -1.0,
) -> VerifyResult:
    """用自有日线对因子表达式做抽样复算,估计方向性 IC。

    bars_by_symbol: symbol → DataFrame(trade_date, open, high, low, close, volume)
    简化:用次日收益与因子值的时序相关粗估 IC;达不到阈值则拒绝。
    """
    factor_expr = contents.manifest.factors[0].expression or ""
    if not bars_by_symbol:
        # 无行情时仍做语法抽检,标记为 skipped(便于 stub 冒烟)
        dates = [d.date() for d in pd.bdate_range("2024-01-01", periods=30)]
        synthetic = pd.DataFrame(
            {
                "trade_date": dates,
                "open": [10.0] * 30,
                "high": [10.5] * 30,
                "low": [9.5] * 30,
                "close": [10.0 + i * 0.01 for i in range(30)],
                "volume": [1e6] * 30,
            }
        )
        try:
            eval_expression(factor_expr, synthetic)
        except ExprError as e:
            return VerifyResult(False, {}, f"表达式求值失败: {e}")
        return VerifyResult(
            True,
            {
                "sample_ic": None,
                "verify_skipped": True,
                "claimed_ic": contents.manifest.metrics_summary.ic,
            },
            "no market data; syntax-only check",
        )

    ics: list[float] = []
    for _symbol, bars in bars_by_symbol.items():
        if bars is None or len(bars) < 10:
            continue
        try:
            values = eval_expression(factor_expr, bars)
        except ExprError as e:
            return VerifyResult(False, {}, f"表达式求值失败: {e}")
        close = pd.Series(bars["close"], dtype=float)
        fwd = close.shift(-1) / close - 1.0
        f = pd.Series(values, dtype=float)
        aligned = pd.DataFrame({"f": f, "r": fwd}).dropna()
        if len(aligned) < 5:
            continue
        # 避免依赖 scipy:秩次 + pearson ≈ spearman
        left = pd.Series(aligned["f"], dtype=float).rank()
        right = pd.Series(aligned["r"], dtype=float).rank()
        corr_val = left.corr(right)
        if corr_val is None or (isinstance(corr_val, float) and pd.isna(corr_val)):
            continue
        ic = float(corr_val)
        ics.append(ic)

    if not ics:
        return VerifyResult(False, {}, "无法计算有效 IC")
    mean_ic = sum(ics) / len(ics)
    metrics = {
        "sample_ic": round(mean_ic, 6),
        "sample_n_symbols": len(ics),
        "claimed_ic": contents.manifest.metrics_summary.ic,
    }
    claimed = contents.manifest.metrics_summary.ic
    same_sign = (mean_ic >= 0 and claimed >= 0) or (mean_ic < 0 and claimed < 0)
    if mean_ic < min_ic:
        return VerifyResult(False, metrics, f"复算 IC {mean_ic:.4f} 低于下限 {min_ic}")
    if abs(claimed) > 0.01 and not same_sign:
        return VerifyResult(False, metrics, "复算 IC 与声称 IC 方向不一致")
    return VerifyResult(True, metrics, "ok")


def package_id_str(package_id: UUID | str) -> str:
    return str(package_id)


def build_stub_package_zip(
    *,
    package_id: str,
    producer: str = "alphaagent@stub",
    expression: str = "Ref($close, 1) / $close - 1",
    ic: float = -0.03,
) -> bytes:
    """测试/冒烟用:构造最小合法策略包 zip。"""
    from datetime import UTC, datetime
    from uuid import UUID

    manifest = {
        "schema_version": "1.0",
        "package_id": str(UUID(package_id) if len(package_id) == 36 else package_id),
        "producer": producer,
        "created_at": datetime.now(UTC).isoformat(),
        "data_snapshot": "qlib_cn_stub",
        "universe": "csi300",
        "backtest_start": "2024-01-01",
        "backtest_end": "2024-12-31",
        "metrics_summary": {"ic": ic, "arr": 0.1, "mdd": -0.08},
        "signal_protocol": "qlib_expression",
        "factors": [
            {
                "name": "mom_1d",
                "expression": expression,
                "description": "1日动量",
                "hypothesis": "短期反转/动量 stub",
            }
        ],
    }
    # fix package_id if not uuid
    try:
        UUID(manifest["package_id"])
    except ValueError:
        from uuid import uuid4

        manifest["package_id"] = str(uuid4())

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("README.md", "# stub strategy\n")
        zf.writestr(
            "report/metrics.json",
            json.dumps(manifest["metrics_summary"]),
        )
    return buf.getvalue()


def generate_signals_for_date(
    contents: PackageContents,
    bars_by_symbol: dict[str, pd.DataFrame],
    trade_date: date,
    *,
    top_n: int = 5,
) -> list[dict]:
    """对给定日生成策略信号:因子值最高 top_n 买入,最低 top_n 卖出。"""
    expr = contents.manifest.factors[0].expression or ""
    scores: list[tuple[str, float]] = []
    for symbol, bars in bars_by_symbol.items():
        if bars is None or bars.empty:
            continue
        sub = bars.loc[bars["trade_date"] <= trade_date].tail(60)
        if len(sub) < 5:
            continue
        try:
            values = eval_expression(expr, sub.reset_index(drop=True))
        except ExprError:
            continue
        if values.empty or pd.isna(values.iloc[-1]):
            continue
        scores.append((symbol, float(values.iloc[-1])))
    scores.sort(key=lambda x: x[1], reverse=True)
    out: list[dict] = []
    for symbol, score in scores[:top_n]:
        out.append(
            {
                "symbol": symbol,
                "score": score,
                "action": "buy",
                "trade_date": trade_date.isoformat(),
            }
        )
    for symbol, score in scores[-top_n:] if len(scores) > top_n else []:
        if any(o["symbol"] == symbol for o in out):
            continue
        out.append(
            {
                "symbol": symbol,
                "score": score,
                "action": "sell",
                "trade_date": trade_date.isoformat(),
            }
        )
    return out
