"""runners/common — reporter + budget guard(stdlib + urllib,不依赖主平台包)。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def _utcnow() -> datetime:
    return datetime.now(UTC)


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@dataclass
class BudgetGuard:
    max_loops: int
    max_hours: float
    max_llm_cost_usd: float
    started_at: float = field(default_factory=time.time)
    loops: int = 0
    llm_cost_usd: float = 0.0

    def record_loop(self, cost_usd: float = 0.0) -> None:
        self.loops += 1
        self.llm_cost_usd += cost_usd

    def exceeded(self) -> str | None:
        if self.loops >= self.max_loops:
            return "max_loops"
        if (time.time() - self.started_at) / 3600.0 >= self.max_hours:
            return "max_hours"
        if self.llm_cost_usd >= self.max_llm_cost_usd:
            return "max_llm_cost_usd"
        return None


class Reporter:
    """先写 events.jsonl,再 POST/PUT;失败留档。"""

    def __init__(
        self,
        *,
        job_id: str,
        base_url: str,
        hmac_secret: str,
        artifact_url: str,
        work_dir: Path,
    ) -> None:
        self.job_id = job_id
        self.base_url = base_url.rstrip("/")
        self.hmac_secret = hmac_secret
        self.artifact_url = artifact_url
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self.work_dir / "events.jsonl"
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _append_local(self, payload: dict) -> None:
        with self._events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _post(self, path: str, payload: dict) -> bool:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        sig = sign_payload(self.hmac_secret, body)
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Signal-Signature": sig,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError) as e:
            self._append_local({"_send_error": str(e), "path": path, "payload": payload})
            return False

    def event(
        self,
        type: str,
        *,
        loop: int | None = None,
        best_ic: float | None = None,
        llm_cost_usd: float | None = None,
        message: str | None = None,
    ) -> None:
        payload = {
            "schema_version": "1.0",
            "job_id": self.job_id,
            "type": type,
            "ts": _utcnow().isoformat(),
            "seq": self._next_seq(),
            "loop": loop,
            "best_ic": best_ic,
            "llm_cost_usd": llm_cost_usd,
            "message": message,
        }
        self._append_local(payload)
        self._post("/events", payload)

    def upload_artifact(self, data: bytes) -> bool:
        sig = sign_payload(self.hmac_secret, data)
        req = urllib.request.Request(
            self.artifact_url,
            data=data,
            method="PUT",
            headers={
                "Content-Type": "application/zip",
                "X-Signal-Signature": sig,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError) as e:
            (self.work_dir / "artifact_upload_error.txt").write_text(str(e), encoding="utf-8")
            # 落盘保留产物
            (self.work_dir / "package.zip").write_bytes(data)
            return False

    def complete(
        self,
        status: str,
        *,
        package_id: str | None = None,
        total_loops: int = 0,
        total_llm_cost_usd: float = 0.0,
        summary: dict | None = None,
    ) -> None:
        payload = {
            "schema_version": "1.0",
            "job_id": self.job_id,
            "status": status,
            "package_id": package_id,
            "total_loops": total_loops,
            "total_llm_cost_usd": total_llm_cost_usd,
            "summary": summary or {},
        }
        self._append_local({"_complete": payload})
        self._post("/complete", payload)
