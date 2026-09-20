"""notify 渠道单测(假 SMTP / 假 webhook)。"""

from __future__ import annotations

import json
from email.message import EmailMessage

from signal_notify import EmailChannel, FeishuChannel, NotifyService, NotifySettings


class FakeSMTP:
    last = None

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        self.user = user

    def send_message(self, msg: EmailMessage):
        FakeSMTP.last = msg

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass


def test_email_channel(monkeypatch):
    import signal_notify as n

    monkeypatch.setattr(n.smtplib, "SMTP_SSL", FakeSMTP)
    ch = EmailChannel(
        host="smtp.example.com",
        port=465,
        user="u",
        password="p",
        mail_from="from@ex.com",
        mail_to=["a@ex.com"],
        use_ssl=True,
    )
    ch.send("hello", "world")
    assert FakeSMTP.last is not None
    assert FakeSMTP.last["Subject"] == "hello"
    assert "world" in FakeSMTP.last.get_content()


def test_feishu_channel(monkeypatch):
    captured = {}

    class Resp:
        status = 200

        def read(self):
            return b'{"StatusCode":0}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return Resp()

    import signal_notify as n

    monkeypatch.setattr(n.urllib.request, "urlopen", fake_urlopen)
    FeishuChannel(webhook_url="https://example.com/hook").send("t", "b")
    assert captured["body"]["msg_type"] == "text"
    assert "t" in captured["body"]["content"]["text"]


def test_notify_service_disabled():
    svc = NotifyService(NotifySettings(enabled=False))
    r = svc.send("a", "b")
    assert r["sent"] is False
    assert r["reason"] == "disabled"


def test_notify_service_multi_channel():
    class Ok:
        name = "x"

        def send(self, title, body):
            return None

    class Bad:
        name = "y"

        def send(self, title, body):
            raise RuntimeError("boom")

    svc = NotifyService(NotifySettings(enabled=True), channels=[Ok(), Bad()])
    r = svc.send("t", "b")
    assert r["sent"] is True
    assert r["results"]["x"] == "ok"
    assert r["results"]["y"].startswith("error:")
