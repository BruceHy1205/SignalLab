"""聊天记录切分为消息。支持微信导出 txt 与纯粘贴文本。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# 微信导出常见格式:
#   张三 2026-07-15 09:21:03
#   今天重点关注茅台...
# 或:
#   张三:
#   2026/7/15 9:21
#   今天重点关注茅台...
_WECHAT_HEADER = re.compile(
    r"^(?P<speaker>.+?)\s+(?P<ts>\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s*$"
)
_WECHAT_HEADER_ALT = re.compile(r"^(?P<speaker>.+?)[:：]\s*$")
_TS_ONLY = re.compile(r"^(?P<ts>\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s*$")


@dataclass(frozen=True)
class ChatMessage:
    speaker: str
    message_time: datetime | None
    text: str
    raw_block: str


def _parse_ts(s: str) -> datetime:
    s = s.replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {s!r}")


def parse_wechat_txt(content: str) -> list[ChatMessage]:
    """解析微信导出 txt。空行分隔消息块。"""
    lines = content.replace("\r\n", "\n").split("\n")
    messages: list[ChatMessage] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue
        speaker: str | None = None
        ts: datetime | None = None
        if m := _WECHAT_HEADER.match(line):
            speaker = m.group("speaker").strip()
            ts = _parse_ts(m.group("ts"))
            i += 1
        elif (m := _WECHAT_HEADER_ALT.match(line)) and i + 1 < len(lines):
            speaker = m.group("speaker").strip()
            nxt = lines[i + 1].strip()
            if tm := _TS_ONLY.match(nxt):
                ts = _parse_ts(tm.group("ts"))
                i += 2
            else:
                i += 1
        else:
            # 无法识别头部,整行当作匿名消息
            messages.append(ChatMessage("unknown", None, line, line))
            i += 1
            continue

        body_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            # 碰到下一条消息头就停
            if _WECHAT_HEADER.match(lines[i]) or _WECHAT_HEADER_ALT.match(lines[i]):
                break
            body_lines.append(lines[i].rstrip())
            i += 1
        text = "\n".join(body_lines).strip()
        if text:
            raw = f"{speaker} {ts}\n{text}" if ts else f"{speaker}\n{text}"
            messages.append(ChatMessage(speaker or "unknown", ts, text, raw))
    return messages


def parse_paste(content: str, default_speaker: str = "paste") -> list[ChatMessage]:
    """手动粘贴:按空行切块,每块一条消息;若块首行是时间戳则解析。"""
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip())
    out: list[ChatMessage] = []
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        ts: datetime | None = None
        body = lines
        if tm := _TS_ONLY.match(lines[0].strip()):
            ts = _parse_ts(tm.group("ts"))
            body = lines[1:]
        text = "\n".join(body).strip()
        if text:
            out.append(ChatMessage(default_speaker, ts, text, block.strip()))
    return out
