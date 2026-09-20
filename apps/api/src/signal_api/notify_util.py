"""组装层通知工厂(业务包不依赖 signal_notify)。"""

from __future__ import annotations

from signal_notify import NotifyService, NotifySettings

from signal_api.config import ApiSettings


def get_notify(settings: ApiSettings | None = None) -> NotifyService:
    s = settings or ApiSettings()
    return NotifyService(
        NotifySettings(
            enabled=s.notify_enabled,
            channels=s.notify_channels,
            smtp_host=s.smtp_host,
            smtp_port=s.smtp_port,
            smtp_user=s.smtp_user,
            smtp_password=s.smtp_password,
            smtp_from=s.smtp_from,
            smtp_to=s.smtp_to,
            smtp_use_ssl=s.smtp_use_ssl,
            feishu_webhook_url=s.feishu_webhook_url,
        )
    )
