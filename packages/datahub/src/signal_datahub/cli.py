"""命令行入口:uv run python -m signal_datahub.cli ..."""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from signal_datahub.config import DatahubSettings, build_providers
from signal_datahub.qlib_dump import dump_qlib_snapshot
from signal_datahub.symbols import BENCHMARK_SYMBOL, normalize_symbol
from signal_datahub.sync import CSI300, SyncService, market_today


def _session(database_url: str) -> Session:
    return Session(create_engine(database_url, pool_pre_ping=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal-datahub")
    parser.add_argument(
        "--database-url",
        default=None,
        help="默认读 DATABASE_URL 或 postgresql+psycopg://signal:signal@localhost:5432/signal",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync-instruments", help="全市场股票列表入库")

    p_bars = sub.add_parser("sync-bars", help="日线入库")
    p_bars.add_argument("--symbols", nargs="+", help="股票代码,不传则拉沪深300成分+基准")
    p_bars.add_argument("--days", type=int, default=30, help="回补天数")
    p_bars.add_argument("--no-incremental", action="store_true")

    p_dump = sub.add_parser("dump-qlib", help="导出 Qlib dump_bin 兼容快照(不安装 qlib)")
    p_dump.add_argument(
        "--out-root",
        default=None,
        help="快照根目录;默认 RESEARCH_DATA_SNAPSHOTS_DIR 或 ./data/qlib_snapshots",
    )
    p_dump.add_argument(
        "--name",
        default=None,
        help="快照子目录名,默认 qlib_cn_YYYYMMDD",
    )
    p_dump.add_argument("--symbols", nargs="+", help="限定标的;默认库内全部有日线的")
    p_dump.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    p_dump.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    p_dump.add_argument(
        "--csi300",
        action="store_true",
        help="额外写 instruments/csi300.txt(按当前成分接口)",
    )

    args = parser.parse_args(argv)
    url = (
        args.database_url
        or os.environ.get("DATABASE_URL")
        or "postgresql+psycopg://signal:signal@localhost:5432/signal"
    )
    svc = SyncService(build_providers(DatahubSettings()))
    with _session(url) as session:
        if args.cmd == "sync-instruments":
            print(svc.sync_instruments(session))
        elif args.cmd == "sync-bars":
            if args.symbols:
                symbols = [normalize_symbol(s) for s in args.symbols]
            else:
                symbols = svc.sync_index_constituents(session, CSI300)
                if BENCHMARK_SYMBOL not in symbols:
                    symbols = [BENCHMARK_SYMBOL, *symbols]
            end = market_today()
            print(
                svc.sync_daily_bars(
                    session,
                    symbols,
                    end - timedelta(days=args.days),
                    end,
                    incremental=not args.no_incremental,
                )
            )
        elif args.cmd == "dump-qlib":
            out_root = Path(
                args.out_root
                or os.environ.get("RESEARCH_DATA_SNAPSHOTS_DIR")
                or "data/qlib_snapshots"
            )
            symbols = [normalize_symbol(s) for s in args.symbols] if args.symbols else None
            start = date.fromisoformat(args.start) if args.start else None
            end = date.fromisoformat(args.end) if args.end else None
            universe = None
            if args.csi300:
                universe = svc.sync_index_constituents(session, CSI300)
            result = dump_qlib_snapshot(
                session,
                out_root,
                snapshot_name=args.name,
                symbols=symbols,
                start=start,
                end=end,
                universe_symbols=universe,
            )
            print(
                {
                    "snapshot_name": result.snapshot_name,
                    "out_dir": str(result.out_dir),
                    "n_symbols": result.n_symbols,
                    "n_calendar_days": result.n_calendar_days,
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
