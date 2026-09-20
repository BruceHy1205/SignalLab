"""研究任务规格契约:主平台 research 模块下发给 runner 的 job spec。

secrets 一律不直接出现在 spec 中,只允许 `env:VAR_NAME` 形式的引用,
由供给器在拉起 runner 时解析并经环境变量注入容器。
"""

from __future__ import annotations

import os
import re
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from signal_contracts import SCHEMA_VERSION

_KEY_REF_RE = re.compile(r"^env:[A-Z][A-Z0-9_]*$")


def resolve_key_ref(key_ref: str) -> str:
    """把 `env:VAR` 形式的引用解析成真实值。只在供给器/runner 进程内调用。"""
    if not _KEY_REF_RE.match(key_ref):
        raise ValueError(f"非法 key_ref: {key_ref!r},只支持 env:VAR_NAME 形式")
    var = key_ref.removeprefix("env:")
    value = os.environ.get(var)
    if not value:
        raise KeyError(f"环境变量 {var} 未设置或为空")
    return value


def _validate_key_ref(v: str) -> str:
    if not _KEY_REF_RE.match(v):
        raise ValueError(f"非法 key_ref: {v!r},只支持 env:VAR_NAME 形式")
    return v


class RunnerTargetType(StrEnum):
    LOCAL_DOCKER = "local_docker"
    REMOTE_SSH = "remote_ssh"


class RunnerTarget(BaseModel):
    type: RunnerTargetType
    host: str | None = None
    user: str | None = None
    ssh_key_ref: str | None = Field(default=None, description="env:VAR,私钥内容或路径")

    @model_validator(mode="after")
    def _remote_requires_host(self) -> RunnerTarget:
        if self.type is RunnerTargetType.REMOTE_SSH and not (self.host and self.user):
            raise ValueError("remote_ssh 必须提供 host 与 user")
        return self

    @field_validator("ssh_key_ref")
    @classmethod
    def _key_ref_format(cls, v: str | None) -> str | None:
        return None if v is None else _validate_key_ref(v)


class LlmConfig(BaseModel):
    provider: str = Field(description="deepseek / qwen / openai / ...")
    model: str
    base_url: str | None = None
    api_key_ref: str = Field(description="env:VAR")

    @field_validator("api_key_ref")
    @classmethod
    def _key_ref_format(cls, v: str) -> str:
        return _validate_key_ref(v)


class Budget(BaseModel):
    """硬预算,runner 内 budget guard 超限即优雅终止并打包已有成果。"""

    max_loops: int = Field(gt=0, le=200)
    max_hours: float = Field(gt=0, le=72)
    max_llm_cost_usd: float = Field(gt=0, le=200)


class CallbackConfig(BaseModel):
    base_url: str = Field(
        description="主平台该 job 的回调根,如 https://host/api/research/jobs/<id>"
    )
    hmac_key_ref: str = Field(description="env:VAR,回报签名密钥")

    @field_validator("hmac_key_ref")
    @classmethod
    def _key_ref_format(cls, v: str) -> str:
        return _validate_key_ref(v)


class ArtifactUploadType(StrEnum):
    HTTP_PUT = "http_put"
    SCP = "scp"


class ArtifactUpload(BaseModel):
    type: ArtifactUploadType
    url: str


class ResearchJobSpec(BaseModel):
    """一次研究任务的完整规格,下发后不可变。"""

    schema_version: str = SCHEMA_VERSION
    job_id: UUID
    producer: str = Field(description="rdagent / alphaagent / ...")
    scenario: str = Field(description="生产者内部场景名,如 fin_factor")
    runner_target: RunnerTarget
    llm: LlmConfig
    budget: Budget
    data_snapshot: str
    callback: CallbackConfig
    artifact_upload: ArtifactUpload
