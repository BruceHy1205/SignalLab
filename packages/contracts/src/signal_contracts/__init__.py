"""契约包:组件之间唯一允许共享的代码。

三份契约(见 docs/architecture.md §2):
- strategy_package: 策略生产者(RD-Agent/AlphaAgent/手写)与主平台的文件接口
- research_job:     研究任务规格,主平台下发给 runner
- runner_events:    runner 向主平台回报的心跳/进度/终态协议(含 HMAC 签名)

规则:本包不得 import 任何业务包;业务包之间禁止互相 import,只能共享本包。
"""

SCHEMA_VERSION = "1.0"
