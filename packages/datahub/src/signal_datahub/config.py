"""datahub 配置(环境变量,前缀 DATAHUB_)。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/datahub/src/signal_datahub/config.py → 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


class DatahubSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATAHUB_",
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        extra="ignore",
    )

    tushare_token: str = ""  # 为空则不启用 tushare 备源
    akshare_request_interval_sec: float = 0.5
    sync_start_years: int = 3  # 首次全量回补年数


def build_providers(settings: DatahubSettings) -> list:
    from signal_datahub.providers.akshare_provider import AkshareProvider

    providers: list = [AkshareProvider(settings.akshare_request_interval_sec)]
    if settings.tushare_token:
        from signal_datahub.providers.tushare_provider import TushareProvider

        providers.append(TushareProvider(settings.tushare_token))
    return providers
