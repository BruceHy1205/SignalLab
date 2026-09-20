"""runner 后端选择:stub(默认冒烟) / real(真实 AlphaAgent 或 RD-Agent CLI)。

主平台永不 import 本模块。环境变量:
- SIGNAL_RUNNER_BACKEND=stub|real
- SIGNAL_*_CMD 可覆盖官方 CLI 入口
"""

from __future__ import annotations

import os
import shutil
from typing import Literal

Backend = Literal["stub", "real"]


def resolve_backend(default: Backend = "stub") -> Backend:
    raw = (os.environ.get("SIGNAL_RUNNER_BACKEND") or default).strip().lower()
    if raw in ("real", "live", "prod"):
        return "real"
    return "stub"


def which_cmd(*candidates: str) -> str | None:
    for c in candidates:
        if not c:
            continue
        # 允许绝对路径
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None
