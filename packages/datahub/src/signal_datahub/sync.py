"""同步服务:主备数据源自动降级,单票失败不中断,失败清单记入 sync_runs.detail。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from signal_datahub import repo
from signal_datahub.providers.base import BarProvider, ProviderError
from signal_datahub.symbols import BENCHMARK_SYMBOL, is_index_symbol

logger = logging.getLogger(__name__)

CSI300 = "000300"
CN = ZoneInfo("Asia/Shanghai")
# 因子漂移判定阈值(相对误差)
_FACTOR_DRIFT_EPS = 1e-4


def market_today() -> date:
    """A 股日历日(上海时区),避免 UTC 主机上 date.today() 错日。"""
    from datetime import datetime

    return datetime.now(CN).date()


class SyncService:
    def __init__(self, providers: list[BarProvider]) -> None:
        """providers 按优先级排列,第一个是主源。"""
        if not providers:
            raise ValueError("至少需要一个数据源")
        self._providers = providers

    def _try_each(self, fn_name: str, *args):
        last_err: Exception | None = None
        for p in self._providers:
            try:
                return getattr(p, fn_name)(*args), p.name
            except ProviderError as e:
                logger.warning("数据源 %s 调用 %s 失败,尝试下一个: %s", p.name, fn_name, e)
                last_err = e
        raise last_err or ProviderError("所有数据源均失败")

    def sync_instruments(self, session: Session) -> dict:
        run = repo.start_sync_run(session, "instruments", {})
        try:
            df, source = self._try_each("fetch_instruments")
            n = repo.upsert_instruments(session, df)
            repo.finish_sync_run(session, run, "succeeded", {"count": n, "source": source})
            session.commit()
            return {"count": n, "source": source}
        except Exception as e:
            session.rollback()
            repo.finish_sync_run(session, run, "failed", {"error": str(e)})
            session.commit()
            raise

    def sync_index_constituents(self, session: Session, index_code: str = CSI300) -> list[str]:
        symbols, _ = self._try_each("fetch_index_constituents", index_code)
        return symbols

    def _factor_drifted(self, session: Session, symbol: str, overlap_date: date, df) -> bool:
        """比较重叠日的 qfq_factor:除权后锚点漂移则需全量重拉。指数恒为 1,跳过。"""
        if is_index_symbol(symbol) or df is None or df.empty:
            return False
        row = df.loc[df["trade_date"] == overlap_date]
        if row.empty:
            return False
        new_factor = float(row.iloc[0]["qfq_factor"])
        old = repo.get_bar(session, symbol, overlap_date)
        if old is None or old.qfq_factor is None or float(old.qfq_factor) == 0:
            return False
        old_factor = float(old.qfq_factor)
        return abs(new_factor - old_factor) / abs(old_factor) > _FACTOR_DRIFT_EPS

    def sync_daily_bars(
        self,
        session: Session,
        symbols: list[str],
        start: date,
        end: date,
        incremental: bool = True,
    ) -> dict:
        """区间日线同步。incremental=True 时每票从库内最后交易日续拉。

        幂等:upsert 按 (symbol, trade_date) 冲突更新,重跑安全。
        容错:单票失败记入 failures,继续下一票;全部失败才算 failed。
        复权:增量拉取时用重叠日检测 qfq_factor 漂移,一旦除权则对该票全量重拉。
        """
        run = repo.start_sync_run(
            session,
            "daily_bars",
            {"symbols": len(symbols), "start": str(start), "end": str(end)},
        )
        session.commit()
        ok, rows_total, failures = 0, 0, []
        for symbol in symbols:
            try:
                last = repo.last_trade_date(session, symbol) if incremental else None
                full_refresh = False
                if last is not None:
                    if last >= end:
                        ok += 1
                        continue
                    # 从 last 起拉(含重叠日)以便比对因子
                    df, source = self._try_each("fetch_daily_bars", symbol, last, end)
                    if self._factor_drifted(session, symbol, last, df):
                        logger.info("%s qfq_factor 漂移,全量重拉 %s→%s", symbol, start, end)
                        full_refresh = True
                        df, source = self._try_each("fetch_daily_bars", symbol, start, end)
                    else:
                        # 仅入库新日期
                        df = df.loc[df["trade_date"] > last] if not df.empty else df
                else:
                    df, source = self._try_each("fetch_daily_bars", symbol, start, end)

                n = repo.upsert_daily_bars(session, symbol, df, source)
                session.commit()
                ok += 1
                rows_total += n
                if full_refresh:
                    logger.info("%s 全量刷新 %s 行", symbol, n)
            except Exception as e:
                session.rollback()
                logger.warning("同步 %s 失败: %s", symbol, e)
                failures.append({"symbol": symbol, "error": str(e)[:200]})
        status = "succeeded" if not failures else ("partial" if ok else "failed")
        repo.finish_sync_run(
            session, run, status, {"ok": ok, "rows": rows_total, "failures": failures}
        )
        session.commit()
        return {"status": status, "ok": ok, "rows": rows_total, "failed": len(failures)}

    def daily_incremental(self, session: Session, lookback_days: int = 10) -> dict:
        """每日收盘后的增量任务:沪深300 成分 + 基准指数近 N 天补齐。"""
        symbols = self.sync_index_constituents(session)
        # 基准指数必须入库,否则 excess_return / bench_nav 恒为空
        if BENCHMARK_SYMBOL not in symbols:
            symbols = [BENCHMARK_SYMBOL, *symbols]
        end = market_today()
        start = end - timedelta(days=lookback_days)
        return self.sync_daily_bars(session, symbols, start, end, incremental=True)
