"""upsert 幂等性与同步服务容错(sqlite 内存库 + 假 provider,不依赖网络)。"""

from datetime import date

import pandas as pd
import pytest
from signal_datahub import repo
from signal_datahub.models import DailyBar, SyncRun
from signal_datahub.providers.base import BAR_COLUMNS, ProviderError
from signal_datahub.sync import SyncService
from sqlalchemy import func, select


def make_bars(dates: list[str], close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date.fromisoformat(d),
                "open": close - 0.5,
                "high": close + 0.5,
                "low": close - 1,
                "close": close,
                "volume": 100,
                "amount": 1e6,
                "qfq_factor": 1.0,
            }
            for d in dates
        ]
    ).loc[:, BAR_COLUMNS]


class FakeProvider:
    name = "fake"

    def __init__(self, fail_symbols: set[str] | None = None):
        self.fail_symbols = fail_symbols or set()
        self.calls: list[tuple] = []

    def fetch_daily_bars(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if symbol in self.fail_symbols:
            raise ProviderError(f"simulated failure for {symbol}")
        return make_bars(["2026-07-01", "2026-07-02"])

    def fetch_instruments(self):
        return pd.DataFrame({"symbol": ["600519.SH"], "name": ["贵州茅台"], "exchange": ["SH"]})

    def fetch_index_constituents(self, index_code):
        return ["600519.SH", "000001.SZ"]


class TestUpsertIdempotency:
    def test_daily_bars_rerun_no_duplicates(self, session):
        df = make_bars(["2026-07-01", "2026-07-02"])
        repo.upsert_daily_bars(session, "600519.SH", df, "fake")
        repo.upsert_daily_bars(session, "600519.SH", df, "fake")
        count = session.execute(select(func.count()).select_from(DailyBar)).scalar()
        assert count == 2

    def test_rerun_updates_values(self, session):
        repo.upsert_daily_bars(session, "600519.SH", make_bars(["2026-07-01"], 10.0), "fake")
        repo.upsert_daily_bars(session, "600519.SH", make_bars(["2026-07-01"], 99.0), "fake")
        bar = session.execute(select(DailyBar)).scalar_one()
        assert float(bar.close) == 99.0

    def test_instruments_idempotent(self, session):
        p = FakeProvider()
        repo.upsert_instruments(session, p.fetch_instruments())
        repo.upsert_instruments(session, p.fetch_instruments())
        assert len(repo.search_instruments(session, "茅台")) == 1


class TestSyncService:
    def test_partial_failure_continues(self, session):
        svc = SyncService([FakeProvider(fail_symbols={"000001.SZ"})])
        result = svc.sync_daily_bars(
            session,
            ["600519.SH", "000001.SZ", "300750.SZ"],
            date(2026, 7, 1),
            date(2026, 7, 2),
            incremental=False,
        )
        assert result == {"status": "partial", "ok": 2, "rows": 4, "failed": 1}
        run = session.execute(select(SyncRun)).scalars().all()[-1]
        assert run.status == "partial"
        assert run.detail["failures"][0]["symbol"] == "000001.SZ"

    def test_fallback_to_secondary_provider(self, session):
        primary = FakeProvider(fail_symbols={"600519.SH"})
        secondary = FakeProvider()
        svc = SyncService([primary, secondary])
        result = svc.sync_daily_bars(
            session, ["600519.SH"], date(2026, 7, 1), date(2026, 7, 2), incremental=False
        )
        assert result["status"] == "succeeded"
        assert secondary.calls  # 备源被使用

    def test_incremental_skips_existing(self, session):
        p = FakeProvider()
        svc = SyncService([p])
        svc.sync_daily_bars(
            session, ["600519.SH"], date(2026, 7, 1), date(2026, 7, 2), incremental=True
        )
        p.calls.clear()
        # 第二次:库内已有到 07-02,区间不扩,应该跳过拉取
        svc.sync_daily_bars(
            session, ["600519.SH"], date(2026, 7, 1), date(2026, 7, 2), incremental=True
        )
        assert p.calls == []

    def test_factor_drift_triggers_full_refresh(self, session):
        """除权后重叠日因子变化 → 全量重拉并刷新历史因子。"""

        class DriftProvider(FakeProvider):
            def fetch_daily_bars(self, symbol, start, end):
                self.calls.append((symbol, start, end))
                # 除权后全区间统一新因子
                factor = 0.5
                return pd.DataFrame(
                    [
                        {
                            "trade_date": date(2026, 7, 1),
                            "open": 10.0,
                            "high": 11.0,
                            "low": 9.0,
                            "close": 10.0,
                            "volume": 100,
                            "amount": 1e6,
                            "qfq_factor": factor,
                        },
                        {
                            "trade_date": date(2026, 7, 2),
                            "open": 10.0,
                            "high": 11.0,
                            "low": 9.0,
                            "close": 10.0,
                            "volume": 100,
                            "amount": 1e6,
                            "qfq_factor": factor,
                        },
                        {
                            "trade_date": date(2026, 7, 3),
                            "open": 10.0,
                            "high": 11.0,
                            "low": 9.0,
                            "close": 10.0,
                            "volume": 100,
                            "amount": 1e6,
                            "qfq_factor": factor,
                        },
                    ]
                ).loc[:, BAR_COLUMNS]

        # 先写入旧因子 1.0
        repo.upsert_daily_bars(
            session, "600519.SH", make_bars(["2026-07-01", "2026-07-02"], 10.0), "seed"
        )
        session.commit()
        p = DriftProvider()
        svc = SyncService([p])
        result = svc.sync_daily_bars(
            session, ["600519.SH"], date(2026, 7, 1), date(2026, 7, 3), incremental=True
        )
        assert result["status"] == "succeeded"
        # 至少两次拉取:重叠探测 + 全量
        assert len(p.calls) >= 2
        bar = repo.get_bar(session, "600519.SH", date(2026, 7, 1))
        assert bar is not None
        assert float(bar.qfq_factor) == pytest.approx(0.5)

    def test_daily_incremental_includes_benchmark(self, session):
        p = FakeProvider()
        svc = SyncService([p])
        # 打补丁 market_today
        from signal_datahub import sync as sync_mod

        original = sync_mod.market_today
        sync_mod.market_today = lambda: date(2026, 7, 2)
        try:
            result = svc.daily_incremental(session, lookback_days=5)
        finally:
            sync_mod.market_today = original
        assert result["status"] == "succeeded"
        symbols_called = {c[0] for c in p.calls}
        assert "000300.SH" in symbols_called
        assert "600519.SH" in symbols_called

    def test_sync_instruments_records_run(self, session):
        svc = SyncService([FakeProvider()])
        out = svc.sync_instruments(session)
        assert out["count"] == 1
        runs = repo.recent_sync_runs(session)
        assert runs[0].job_type == "instruments"
        assert runs[0].status == "succeeded"
