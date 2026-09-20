"""tracker:机构推荐胜率追踪(功能4)。

规则:
- sources / recommendations / rec_performance 三张表只有本包写入;
- 只依赖 signal_contracts,禁止 import datahub/papertrade 等业务包;
- 读行情通过注入的 BarsReader 协议,不直接 import datahub。
"""
