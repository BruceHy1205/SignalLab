"""BarsReader:tracker 读取行情的唯一接口。

组装层(apps/api)注入一个实现(通常包一层 datahub.repo),tracker 不 import datahub。
返回的 DataFrame 列约定:trade_date, open, high, low, close(前复权)。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

BAR_COLS = ["trade_date", "open", "high", "low", "close"]


class BarsReader(Protocol):
    def get_qfq_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """前复权日线,按 trade_date 升序。空 DataFrame 表示无数据。"""
        ...

    def resolve_symbol(self, name: str) -> list[tuple[str, str]]:
        """名称/别名 → [(symbol, name), ...]。0 个=未匹配,1 个=唯一,多个=歧义。"""
        ...

    def list_aliases(self) -> dict[str, str]:
        """别名/名称 → symbol 的全量映射(消歧用)。"""
        ...
