"""agents:多智能体决策层。

规则:
- signals / agent_runs 只有本包写入;
- 通过 ToolPorts 访问行情/胜率/持仓/下单,不 import 其他业务包;
- 无 LLM key 时走规则决策兜底(可单测)。
"""
