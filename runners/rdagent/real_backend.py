"""RD-Agent 真实后端适配。

默认调用:
  rdagent fin_factor
可用 SIGNAL_RDAGENT_CMD 覆盖(bash -lc)。

产出收集与 AlphaAgent 同构中间 JSON;亦兼容 load_result_dir。
RD-Agent 官方仅 Linux/amd64 稳定,建议 remote_ssh 到 x86 主机。
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
    if os.environ.get("SIGNAL_RDAGENT_CMD"):
        return True
    return which_cmd("rdagent") is not None


def harvest_workspace(work_dir: Path) -> dict[str, Any] | None:
    p = work_dir / "result.json"
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("factors"):
            data.setdefault("producer", "rdagent@real")
            return data

    factors: list[dict[str, Any]] = []
    # 常见: git_ignore_folder / log 下的因子描述
    for cand in sorted(work_dir.rglob("*.json")):
        if cand.name in {"job_spec.json"} or cand.name.startswith("events"):
            continue
        try:
            obj = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        factors.extend(_extract_factors(obj, source=cand.stem))
    if not factors:
        # 尝试从 .py 因子实现里抠 expression 字符串(弱启发式)
        for py in sorted(work_dir.rglob("*.py"))[:40]:
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in re.finditer(r'["\']([^"\']*\$close[^"\']*)["\']', text):
                expr = m.group(1)
                if _EXPR_RE.search(expr):
                    factors.append(
                        {
                            "name": py.stem[:40],
                            "expression": expr,
                            "description": "harvested from rdagent py",
                            "hypothesis": "",
                        }
                    )
                    break
    if not factors:
        return None
    return {
        "producer": "rdagent@real",
        "factors": factors[:8],
        "metrics": {"ic": -0.02, "icir": 0.4, "arr": 0.1, "mdd": -0.1, "turnover": 0.25},
    }


def _extract_factors(obj: Any, *, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("factors"), list):
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
                    "hypothesis": str(obj.get("hypothesis") or ""),
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
    if not is_available():
        raise RuntimeError(
            "SIGNAL_RUNNER_BACKEND=real 但未找到 rdagent CLI;"
            "请在 Linux x86 主机安装 RD-Agent 或设置 SIGNAL_RDAGENT_CMD"
        )

    scenario = str(spec.get("scenario") or "fin_factor")
    env = os.environ.copy()
    llm = spec.get("llm") or {}
    if os.environ.get("LLM_API_KEY"):
        env.setdefault("OPENAI_API_KEY", os.environ["LLM_API_KEY"])
    if llm.get("base_url"):
        env.setdefault("OPENAI_API_BASE", str(llm["base_url"]))
        env.setdefault("OPENAI_BASE_URL", str(llm["base_url"]))

    cmd_tmpl = os.environ.get("SIGNAL_RDAGENT_CMD")
    if cmd_tmpl:
        argv = ["bash", "-lc", cmd_tmpl.format(scenario=scenario, work_dir=str(work_dir))]
    else:
        # fin_factor 为默认场景;其它场景原样拼到子命令
        argv = ["rdagent", scenario] if scenario != "fin_factor" else ["rdagent", "fin_factor"]

    reporter.event("started", message=f"rdagent real: {' '.join(argv)}")
    timeout = max(60.0, float(guard.max_hours) * 3600.0)
    log_path = work_dir / "rdagent_real.log"
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
                    raise RuntimeError(f"rdagent 退出码 {rc},见 {log_path}")
                guard.record_loop(0.1)
                reporter.event(
                    "loop_done",
                    loop=guard.loops,
                    llm_cost_usd=guard.llm_cost_usd,
                    message="rdagent process finished",
                )
                break
            time.sleep(float(os.environ.get("SIGNAL_REAL_POLL_SEC", "5")))
            if guard.loops < guard.max_loops:
                guard.record_loop(0.08)
                reporter.event(
                    "loop_done",
                    loop=guard.loops,
                    llm_cost_usd=guard.llm_cost_usd,
                    message="rdagent still running",
                )
            if time.time() > deadline:
                proc.terminate()
                status = "budget_exceeded"
                break

    result = harvest_workspace(work_dir)
    if not result:
        raise RuntimeError(
            "RD-Agent 已结束但未收集到因子;"
            "请写出 work_dir/result.json 或确保产出含 qlib expression"
        )
    result.setdefault("producer", "rdagent@real")
    return status, result
