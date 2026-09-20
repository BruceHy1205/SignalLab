"""回报协议契约:runner → 主平台的心跳/进度/终态,以及 HMAC 签名。

可靠性设计(architecture.md §2.3):
- runner 先把事件追加写本地 events.jsonl,再 POST;发送失败留档,由主平台探测时拉回补账;
- 所有请求体用 HMAC-SHA256 签名,签名放 X-Signal-Signature 头。
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from signal_contracts import SCHEMA_VERSION

SIGNATURE_HEADER = "X-Signal-Signature"


class RunnerEventType(StrEnum):
    STARTED = "started"
    HEARTBEAT = "heartbeat"
    LOOP_DONE = "loop_done"
    ERROR = "error"


class RunnerEvent(BaseModel):
    """心跳与进度事件。POST {callback.base_url}/events"""

    schema_version: str = SCHEMA_VERSION
    job_id: UUID
    type: RunnerEventType
    ts: datetime
    seq: int = Field(ge=0, description="runner 内单调递增,用于补账去重")
    loop: int | None = None
    best_ic: float | None = None
    llm_cost_usd: float | None = Field(default=None, ge=0)
    message: str | None = None


class CompletionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


class CompletionReport(BaseModel):
    """终态汇报。POST {callback.base_url}/complete"""

    schema_version: str = SCHEMA_VERSION
    job_id: UUID
    status: CompletionStatus
    package_id: UUID | None = Field(default=None, description="成功上传的策略包 id")
    total_loops: int = 0
    total_llm_cost_usd: float = 0
    summary: dict[str, float | int | str] = Field(default_factory=dict)


def sign_payload(secret: str, body: bytes) -> str:
    """对请求体做 HMAC-SHA256,返回 hex。runner 发送与主平台校验共用。"""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, body), signature)
