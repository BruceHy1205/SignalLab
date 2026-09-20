"""papertrade:模拟盘。

规则:
- accounts/orders/positions/nav 只有本包写入;
- 通过 PriceReader 端口读行情,不 import datahub;
- 撮合:挂单 → 次一交易日开盘价成交;A 股整手;手续费/滑点可配。
"""
