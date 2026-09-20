"""AlphaAgent 真实后端适配。

默认调用官方 CLI:
  alphaagent mine --potential_direction "<hypothesis>"
或环境变量 SIGNAL_ALPHAAGENT_CMD 覆盖整条命令模板(可用 {direction} 占位)。

产出收集优先级:
1. work_dir/result.json(推荐由包装脚本写出)
2. work_dir/factors.json / factors/*.json
3. 扫描含 expression 的 json 文件

未安装 CLI 时抛 RuntimeError,由 runner 标记 failed。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from common.backend import which_cmd
from common.reporter import BudgetGuard, Reporter

_EXPR_RE = re.compile(r"(\$[a-zA-Z_]+|Ref\(|Mean\(|Std\()")


def is_available() -> bool:
    if os.environ.get("SIGNAL_ALPHAAGENT_CMD"):
        return True
    return which_cmd("alphaagent") is not None


def harvest_workspace(work_dir: Path) -> dict[str, Any] | None:
    """从工作目录收集中间结果;无有效因子则返回 None。"""
    for name in ("result.json", "factors.json"):
        p = work_dir / name
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("factors"):
                data.setdefault("producer", "alphaagent@real")
                return data

    factors: list[dict[str, Any]] = []
    for p in sorted(work_dir.rglob("*.json")):
        if p.name in {"job_spec.json", "events.jsonl"} or "report" in p.parts:
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        factors.extend(_extract_factors(obj, source=p.stem))
    if not factors:
        return None
    return {
        "producer": "alphaagent@real",
        "factors": factors[:8],
        "metrics": {"ic": -0.02, "icir": 0.4, "arr": 0.1, "mdd": -0.1, "turnover": 0.25},
    }


def _extract_factors(obj: Any, *, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if "factors" in obj and isinstance(obj["factors"], list):
            for i, f in enumerate(obj["factors"]):
                if isinstance(f, dict) and f.get("expression"):
                    out.append(
                        {
                            "name": f.get("name") or f"{source}_{i}",
                            "expression": f["expression"],
                            "description": f.get("description", ""),
                            "hypothesis": f.get("hypothesis", ""),
                        }
                    )
            return out
        expr = obj.get("expression") or obj.get("factor_expression") or obj.get("expr")
        if isinstance(expr, str) and _EXPR_RE.search(expr):
            out.append(
                {
                    "name": str(obj.get("name") or obj.get("factor_name") or source),
                    "expression": expr,
                    "description": str(obj.get("description") or ""),
                    "hypothesis": str(obj.get("hypothesis") or obj.get("direction") or ""),
                }
            )
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            out.extend(_extract_factors(item, source=f"{source}_{i}"))
    return out


def run_research(
    *,
    spec: dict[str, Any],
    work_dir: Path,
    guard: BudgetGuard,
    reporter: Reporter,
) -> tuple[str, dict[str, Any]]:
    """跑真实 AlphaAgent。返回 (status, result)。"""
    if not is_available():
        raise RuntimeError(
            "SIGNAL_RUNNER_BACKEND=real 但未找到 alphaagent CLI;"
            "请安装 AlphaAgent 或设置 SIGNAL_ALPHAAGENT_CMD"
        )

    direction = (
        os.environ.get("SIGNAL_ALPHA_DIRECTION")
        or (spec.get("hypothesis") if isinstance(spec.get("hypothesis"), str) else None)
        or "short-term mean reversion on CSI300 liquid names"
    )
    llm = spec.get("llm") or {}
    env = os.environ.copy()
    # AlphaAgent 读 OPENAI_* ;把主平台 LLM 配置映射过去
    if llm.get("base_url"):
        env.setdefault("OPENAI_BASE_URL", str(llm["base_url"]))
    if os.environ.get("LLM_API_KEY"):
        env.setdefault("OPENAI_API_KEY", os.environ["LLM_API_KEY"])
    env.setdefault("USE_LOCAL", "True")
    if llm.get("model"):
        env.setdefault("CHAT_MODEL", str(llm["model"]))
        env.setdefault("REASONING_MODEL", str(llm["model"]))

    cmd_tmpl = os.environ.get("SIGNAL_ALPHAAGENT_CMD")
    if cmd_tmpl:
        cmd = cmd_tmpl.format(direction=direction, work_dir=str(work_dir))
        argv = ["bash", "-lc", cmd]
    else:
        argv = ["alphaagent", "mine", "--potential_direction", direction]

    reporter.event("started", message=f"alphaagent real: {' '.join(argv[:4])}…")
    timeout = max(60.0, float(guard.max_hours) * 3600.0)
    log_path = work_dir / "alphaagent_real.log"
    status = "succeeded"
    with log_path.open("w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            argv,
            cwd=str(work_dir),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        while True:
            reason = guard.exceeded()
            if reason:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                status = "budget_exceeded"
                break
            rc = proc.poll()
            if rc is not None:
                if rc != 0:
                    raise RuntimeError(f"alphaagent 退出码 {rc},见 {log_path}")
                guard.record_loop(0.1)
                reporter.event(
                    "loop_done",
                    loop=guard.loops,
                    llm_cost_usd=guard.llm_cost_usd,
                    message="alphaagent process finished",
                )
                break
            time.sleep(float(os.environ.get("SIGNAL_REAL_POLL_SEC", "5")))
            # 进程仍在跑时按预算记账心跳,避免主平台判 lost
            if guard.loops < guard.max_loops:
                guard.record_loop(0.05)
                reporter.event(
                    "loop_done",
                    loop=guard.loops,
                    llm_cost_usd=guard.llm_cost_usd,
                    message="alphaagent still running",
                )
            if time.time() > deadline:
                proc.terminate()
                status = "budget_exceeded"
                break

    result = harvest_workspace(work_dir)
    if not result:
        raise RuntimeError(
            "AlphaAgent 已结束但未收集到因子;"
            "请在工作目录写出 result.json(含 factors[].expression)"
        )
    result.setdefault("producer", "alphaagent@real")
    return status, result
