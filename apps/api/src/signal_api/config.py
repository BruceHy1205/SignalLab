from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/src/signal_api/config.py → 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://signal:signal@localhost:5432/signal"
    scheduler_enabled: bool = False
    scheduler_cron_hour: int = 17
    scheduler_cron_minute: int = 30
    scheduler_timezone: str = "Asia/Shanghai"
    # 可选鉴权:非空时要求 Authorization: Bearer <token>
    api_token: str = ""
    # LLM(tracker 抽取 + agents);为空则走规则
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    # 自选股,逗号分隔,如 600519.SH,300750.SZ
    watchlist: str = ""
    agent_max_candidates: int = 10
    agent_max_llm_cost_usd: float = 2.0
    # research(M4/M5)
    runner_callback_secret: str = "dev-secret"
    research_callback_host: str = "http://127.0.0.1:8000"
    research_default_max_loops: int = 3
    research_artifacts_dir: str = "/tmp/signal-artifacts"
    research_heartbeat_timeout_sec: int = 600
    research_data_snapshots_dir: str = ""
    research_remote_image: str = "signal-rdagent:stub"
    research_alphaagent_image: str = "signal-alphaagent:stub"
    research_rdagent_image: str = "signal-rdagent:stub"
    research_runner_backend: str = "stub"  # stub | real
    research_remote_work_root: str = "/tmp/signal-jobs"
    research_ssh_port: int = 22
    research_remote_reverse_tunnel: bool = False
    research_cleanup_remote_on_complete: bool = True
    # notify(邮件 + 飞书)
    notify_enabled: bool = False
    notify_channels: str = "email,feishu"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_use_ssl: bool = True
    feishu_webhook_url: str = ""
    # live / miniqmt
    live_broker: str = "stub"  # stub | miniqmt
    live_miniqmt_account: str = ""
    live_miniqmt_path: str = ""
