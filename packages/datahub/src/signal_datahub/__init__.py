"""datahub:行情数据的唯一所有者。

规则:
- instruments / daily_bars / sync_runs 三张表只有本包写入,其他模块只读;
- 所有行情先入库后使用,外部 API 的不稳定被隔离在同步任务里;
- 只依赖 signal_contracts,禁止 import 其他业务包。
"""
