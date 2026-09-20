"""通知服务:邮件 + 飞书。业务包不依赖本包;由 API 组装层调用。"""

from __future__ import annotations

import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger(__name__)


class NotifyChannel(Protocol):
    name: str

    def send(self, title: str, body: str) -> None: ...


@dataclass
class NotifySettings:
    enabled: bool = False
    # 逗号分隔: email,feishu
    channels: str = "email,feishu"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""  # 逗号分隔多个收件人
    smtp_use_ssl: bool = True
    feishu_webhook_url: str = ""


@dataclass
class EmailChannel:
    name: str = "email"
    host: str = ""
    port: int = 465
    user: str = ""
    password: str = ""
    mail_from: str = ""
    mail_to: list[str] = field(default_factory=list)
    use_ssl: bool = True

    def send(self, title: str, body: str) -> None:
        if not self.host or not self.mail_to:
            raise RuntimeError("email 渠道未配置 SMTP_HOST / SMTP_TO")
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = self.mail_from or self.user or "signal@localhost"
        msg["To"] = ", ".join(self.mail_to)
        msg.set_content(body)
        if self.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30) as smtp:
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)


@dataclass
class FeishuChannel:
    """飞书自定义机器人 webhook。"""

    name: str = "feishu"
    webhook_url: str = ""

    def send(self, title: str, body: str) -> None:
        if not self.webhook_url:
            raise RuntimeError("feishu 渠道未配置 FEISHU_WEBHOOK_URL")
        import json

        text = f"{title}\n{body}".strip()
        payload = json.dumps(
            {"msg_type": "text", "content": {"text": text[:4000]}},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if resp.status >= 300:
                    raise RuntimeError(f"feishu HTTP {resp.status}: {raw}")
                data = json.loads(raw) if raw else {}
                # 飞书成功一般 StatusCode/code == 0
                code = data.get("StatusCode", data.get("code", 0))
                if code not in (0, "0", None):
                    raise RuntimeError(f"feishu error: {raw}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"feishu 请求失败: {e}") from e


class NotifyService:
    def __init__(
        self,
        settings: NotifySettings | None = None,
        channels: list[NotifyChannel] | None = None,
    ) -> None:
        self._settings = settings or NotifySettings()
        if channels is not None:
            self._channels = channels
        else:
            self._channels = self._build_channels(self._settings)

    @staticmethod
    def _build_channels(settings: NotifySettings) -> list[NotifyChannel]:
        wanted = {c.strip().lower() for c in settings.channels.split(",") if c.strip()}
        out: list[NotifyChannel] = []
        if "email" in wanted and settings.smtp_host and settings.smtp_to:
            out.append(
                EmailChannel(
                    host=settings.smtp_host,
                    port=settings.smtp_port,
                    user=settings.smtp_user,
                    password=settings.smtp_password,
                    mail_from=settings.smtp_from or settings.smtp_user,
                    mail_to=[x.strip() for x in settings.smtp_to.split(",") if x.strip()],
                    use_ssl=settings.smtp_use_ssl,
                )
            )
        if "feishu" in wanted and settings.feishu_webhook_url:
            out.append(FeishuChannel(webhook_url=settings.feishu_webhook_url))
        return out

    def send(self, title: str, body: str) -> dict:
        """向已启用渠道发送;单渠道失败不阻断其它渠道。"""
        if not self._settings.enabled:
            return {"sent": False, "reason": "disabled", "results": {}}
        if not self._channels:
            return {"sent": False, "reason": "no_channels", "results": {}}
        results: dict[str, str] = {}
        ok = 0
        for ch in self._channels:
            try:
                ch.send(title, body)
                results[ch.name] = "ok"
                ok += 1
            except Exception as e:
                logger.warning("notify %s failed: %s", ch.name, e)
                results[ch.name] = f"error:{e}"
        return {"sent": ok > 0, "results": results}

    def notify_research_complete(self, job_id: str, status: str, summary: str = "") -> dict:
        return self.send(
            f"[signal] 研究任务 {status}",
            f"job_id={job_id}\nstatus={status}\n{summary}".strip(),
        )

    def notify_agent_run(self, run_id: str, status: str, n_signals: int, summary: str = "") -> dict:
        return self.send(
            f"[signal] Agent 运行 {status}",
            f"run_id={run_id}\nstatus={status}\nsignals={n_signals}\n{summary}".strip(),
        )

    def notify_live_intent(self, intent_id: str, event: str, detail: str = "") -> dict:
        return self.send(
            f"[signal] 实盘意图 {event}",
            f"intent_id={intent_id}\nevent={event}\n{detail}".strip(),
        )
