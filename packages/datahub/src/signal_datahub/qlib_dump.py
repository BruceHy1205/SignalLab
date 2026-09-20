"""Qlib dump_bin 兼容快照导出(纯 numpy/pandas,主平台不安装 qlib)。

目录布局(与 microsoft/qlib scripts/dump_bin 一致)::

    {out_dir}/
      calendars/day.txt
      instruments/all.txt
      instruments/csi300.txt   # 可选
      features/{sh600519}/open.day.bin
      ...

.bin 格式:首 4 字节为 float32 的 calendar start_index,其后为连续 float32 序列。

OHLC 导出为前复权价(raw * qfq_factor),与主平台 event study / research 复算口径一致;
另写 factor 字段保留原始 qfq_factor 供对账。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from signal_datahub import repo
from signal_datahub.symbols import from_qlib_code, to_qlib_code

logger = logging.getLogger(__name__)

FEATURE_FIELDS = ("open", "high", "low", "close", "volume", "amount", "factor")


@dataclass(frozen=True)
class DumpResult:
    snapshot_name: str
    out_dir: Path
    n_symbols: int
    n_calendar_days: int
    fields: tuple[str, ...]


def write_feature_bin(path: Path, start_index: int, values: np.ndarray) -> None:
    """写入单个 Qlib feature .bin。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = np.empty(len(values) + 1, dtype="<f4")
    payload[0] = float(start_index)
    payload[1:] = values.astype("<f4", copy=False)
    payload.tofile(path)


def read_feature_bin(path: Path) -> tuple[int, np.ndarray]:
    """测试/对账用:读回 (start_index, values)。"""
    raw = np.fromfile(path, dtype="<f4")
    if raw.size < 1:
        raise ValueError(f"空 bin: {path}")
    return int(raw[0]), raw[1:]


def _bars_to_frame(bars) -> pd.DataFrame:
    rows = []
    for b in bars:
        factor = float(b.qfq_factor or 1.0)
        rows.append(
            {
                "trade_date": b.trade_date,
                "open": float(b.open) * factor,
                "high": float(b.high) * factor,
                "low": float(b.low) * factor,
                "close": float(b.close) * factor,
                "volume": float(b.volume),
                "amount": float(b.amount),
                "factor": factor,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["trade_date", *FEATURE_FIELDS])
    df = pd.DataFrame(rows).sort_values("trade_date").drop_duplicates("trade_date")
    return df.reset_index(drop=True)


def dump_symbol_features(
    out_features: Path,
    qlib_code: str,
    df: pd.DataFrame,
    calendar_index: dict[date, int],
) -> tuple[date, date] | None:
    """写出一只标的的全部 feature bin;返回 (start, end) 交易日。"""
    if df.empty:
        return None
    dates = [d if isinstance(d, date) else d.date() for d in df["trade_date"].tolist()]
    # 只保留落在全局日历上的行
    mask = [d in calendar_index for d in dates]
    if not any(mask):
        return None
    df = df.loc[mask].reset_index(drop=True)
    dates = [d if isinstance(d, date) else d.date() for d in df["trade_date"].tolist()]
    start_idx = calendar_index[dates[0]]
    # 按日历对齐:中间缺日填 nan
    end_idx = calendar_index[dates[-1]]
    length = end_idx - start_idx + 1
    feat_dir = out_features / qlib_code.lower()
    for field in FEATURE_FIELDS:
        arr = np.full(length, np.nan, dtype=np.float64)
        col = df[field].to_numpy(dtype=np.float64)
        for d, val in zip(dates, col, strict=True):
            arr[calendar_index[d] - start_idx] = val
        write_feature_bin(feat_dir / f"{field}.day.bin", start_idx, arr)
    return dates[0], dates[-1]


def dump_qlib_snapshot(
    session: Session,
    out_root: Path,
    *,
    snapshot_name: str | None = None,
    symbols: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    universe_symbols: list[str] | None = None,
) -> DumpResult:
    """从 daily_bars 导出一套 Qlib 兼容快照到 out_root/snapshot_name。"""
    out_root = Path(out_root)
    name = snapshot_name or f"qlib_cn_{date.today().strftime('%Y%m%d')}"
    out_dir = out_root / name
    calendars_dir = out_dir / "calendars"
    instruments_dir = out_dir / "instruments"
    features_dir = out_dir / "features"
    calendars_dir.mkdir(parents=True, exist_ok=True)
    instruments_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)

    syms = repo.list_symbols_with_bars(session, symbols=symbols, start=start, end=end)
    if not syms:
        raise ValueError("没有可导出的日线数据")

    calendar = repo.list_trade_dates(session, symbols=syms, start=start, end=end)
    if not calendar:
        raise ValueError("交易日历为空")
    cal_index = {d: i for i, d in enumerate(calendar)}
    (calendars_dir / "day.txt").write_text(
        "\n".join(d.isoformat() for d in calendar) + "\n", encoding="utf-8"
    )

    instrument_lines: list[str] = []
    for symbol in syms:
        bars = repo.get_bars(
            session,
            symbol,
            start or calendar[0],
            end or calendar[-1],
        )
        df = _bars_to_frame(bars)
        qcode = to_qlib_code(symbol)
        span = dump_symbol_features(features_dir, qcode, df, cal_index)
        if not span:
            continue
        instrument_lines.append(f"{qcode}\t{span[0].isoformat()}\t{span[1].isoformat()}")

    if not instrument_lines:
        raise ValueError("导出后无有效标的")

    (instruments_dir / "all.txt").write_text("\n".join(instrument_lines) + "\n", encoding="utf-8")

    if universe_symbols:
        uni = set(universe_symbols)
        uni_lines: list[str] = []
        for line in instrument_lines:
            qcode = line.split("\t", 1)[0]
            try:
                plat = from_qlib_code(qcode)
            except ValueError:
                continue
            if plat in uni:
                uni_lines.append(line)
        if uni_lines:
            (instruments_dir / "csi300.txt").write_text(
                "\n".join(uni_lines) + "\n", encoding="utf-8"
            )

    meta = {
        "schema": "qlib_dump_bin_v1",
        "snapshot_name": name,
        "created_at": datetime.now(UTC).isoformat(),
        "n_symbols": len(instrument_lines),
        "n_calendar_days": len(calendar),
        "fields": list(FEATURE_FIELDS),
        "adjust": "qfq",
        "note": "OHLC are raw*qfq_factor; factor column keeps original qfq_factor",
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(
        "qlib dump done: %s symbols=%s days=%s",
        out_dir,
        len(instrument_lines),
        len(calendar),
    )
    return DumpResult(
        snapshot_name=name,
        out_dir=out_dir,
        n_symbols=len(instrument_lines),
        n_calendar_days=len(calendar),
        fields=FEATURE_FIELDS,
    )
