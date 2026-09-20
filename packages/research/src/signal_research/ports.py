"""研究模块端口(避免直接依赖 datahub)。"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class MarketBarsPort(Protocol):
    def get_qfq_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...

    def list_universe_symbols(self, universe: str = "csi300", limit: int = 30) -> list[str]: ...
