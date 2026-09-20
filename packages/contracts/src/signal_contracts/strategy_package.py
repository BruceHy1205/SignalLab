"""策略包契约:策略生产者(RD-Agent/AlphaAgent/手写)与主平台之间的唯一文件接口。

一个策略包是一个 zip/目录:
    manifest.json + factors/*.json + model/(可选) + report/metrics.json + README.md
主平台导入器只认本文件定义的格式,不关心生产者是谁。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from signal_contracts import SCHEMA_VERSION


class SignalProtocol(StrEnum):
    """策略入库后,主平台执行日常信号计算所用的协议。"""

    QLIB_EXPRESSION = "qlib_expression"  # 因子表达式,主平台用轻量解释器在 pandas 上求值
    PYTHON_MODULE = "python_module"  # 独立 python 文件,受限子进程执行(默认禁用)


class MetricsSummary(BaseModel):
    """runner 侧回测的关键指标摘要(主平台导入时还会独立复算交叉验证)。"""

    ic: float = Field(description="信息系数(日频 rank IC 均值)")
    icir: float | None = Field(default=None, description="IC 信息比率")
    arr: float = Field(description="年化收益率,如 0.14 表示 14%")
    mdd: float = Field(le=0, description="最大回撤,负数,如 -0.07")
    turnover: float | None = Field(default=None, description="日均换手率")


class FactorSpec(BaseModel):
    """单个因子的描述,expression 与 code_file 二选一。"""

    name: str = Field(min_length=1, max_length=64)
    expression: str | None = Field(default=None, description="Qlib 风格因子表达式")
    code_file: str | None = Field(default=None, description="包内相对路径,python_module 协议用")
    description: str = ""
    hypothesis: str = Field(default="", description="产生该因子的研究假设(可解释性)")

    @model_validator(mode="after")
    def _exactly_one_impl(self) -> FactorSpec:
        if (self.expression is None) == (self.code_file is None):
            raise ValueError("expression 与 code_file 必须恰好提供一个")
        return self


class StrategyManifest(BaseModel):
    """策略包根目录的 manifest.json。"""

    schema_version: str = SCHEMA_VERSION
    package_id: UUID
    producer: str = Field(description="生产者标识,如 rdagent@0.8.0 / alphaagent@0.1 / manual")
    created_at: datetime
    data_snapshot: str = Field(description="训练/回测所用数据快照版本,如 qlib_cn_20260718")
    universe: str = Field(description="股票池,如 csi300")
    backtest_start: str = Field(description="回测区间起点 YYYY-MM-DD")
    backtest_end: str = Field(description="回测区间终点 YYYY-MM-DD")
    metrics_summary: MetricsSummary
    signal_protocol: SignalProtocol
    factors: list[FactorSpec] = Field(min_length=1)
