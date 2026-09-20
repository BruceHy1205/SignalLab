"""AlphaAgent 统一入口:stub(默认) 或 real。

环境变量 SIGNAL_RUNNER_BACKEND=stub|real
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

_RUNNERS_ROOT = Path(__file__).resolve().parents[1]
_HERE = Path(__file__).resolve().parent
for p in (_RUNNERS_ROOT, _HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common.backend import resolve_backend  # noqa: E402
from common.reporter import BudgetGuard, Reporter  # noqa: E402
from to_package import alphaagent_result_to_package  # noqa: E402


def _run_stub(guard: BudgetGuard, reporter: Reporter) -> tuple[str, float]:
    best_ic = 0.01
    while True:
        reason = guard.exceeded()
        if reason:
            return "budget_exceeded", best_ic
        time.sleep(float(os.environ.get("SIGNAL_STUB_LOOP_SLEEP", "0.2")))
        guard.record_loop(0.05)
        best_ic = round(best_ic + 0.005, 4)
        reporter.event(
            "loop_done",
            loop=guard.loops,
            best_ic=best_ic,
            llm_cost_usd=guard.llm_cost_usd,
            message=f"alphaagent stub loop {guard.loops}",
        )
        if guard.loops >= guard.max_loops:
            return "budget_exceeded", best_ic


def _stub_result(best_ic: float) -> dict:
    claimed = -abs(float(best_ic))
    return {
        "producer": "alphaagent@stub",
        "factors": [
            {
                "name": "aa_rev_1d",
                "expression": "Ref($close, 1) / $close - 1",
                "description": "1日反转(alphaagent stub)",
                "hypothesis": "stub hypothesis",
            }
        ],
        "metrics": {
            "ic": claimed,
            "icir": 0.5,
            "arr": 0.12,
            "mdd": -0.08,
            "turnover": 0.2,
        },
    }


def main() -> int:
    spec_path = Path(os.environ["SIGNAL_JOB_SPEC"])
    work_dir = Path(os.environ.get("SIGNAL_JOB_WORKDIR", spec_path.parent))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    job_id = str(spec["job_id"])
    callback = spec["callback"]
    budget_cfg = spec["budget"]
    artifact_url = spec["artifact_upload"]["url"]
    data_snapshot = spec.get("data_snapshot") or "qlib_cn_stub"

    hmac_ref = callback["hmac_key_ref"]
    assert hmac_ref.startswith("env:")
    hmac_var = hmac_ref.removeprefix("env:")
    hmac_secret = os.environ.get(hmac_var) or os.environ.get("CALLBACK_HMAC_SECRET") or "dev-secret"

    reporter = Reporter(
        job_id=job_id,
        base_url=callback["base_url"],
        hmac_secret=hmac_secret,
        artifact_url=artifact_url,
        work_dir=work_dir,
    )
    guard = BudgetGuard(
        max_loops=int(budget_cfg["max_loops"]),
        max_hours=float(budget_cfg["max_hours"]),
        max_llm_cost_usd=float(budget_cfg["max_llm_cost_usd"]),
    )

    backend = resolve_backend()
    try:
        if backend == "real":
            from real_backend import run_research

            status, result = run_research(
                spec=spec, work_dir=work_dir, guard=guard, reporter=reporter
            )
        else:
            reporter.event("started", message="alphaagent stub runner started")
            status, best_ic = _run_stub(guard, reporter)
            result = _stub_result(best_ic)
    except Exception as e:
        reporter.event("error", message=str(e)[:200])
        reporter.complete("failed", total_loops=guard.loops, total_llm_cost_usd=guard.llm_cost_usd)
        return 1

    (work_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    package_id = str(uuid4())
    data = alphaagent_result_to_package(
        result, package_id=package_id, data_snapshot=data_snapshot
    )
    (work_dir / "package.zip").write_bytes(data)
    uploaded = reporter.upload_artifact(data)
    if not uploaded:
        reporter.complete(
            "failed",
            package_id=package_id,
            total_loops=guard.loops,
            total_llm_cost_usd=guard.llm_cost_usd,
            summary={"error": "artifact upload failed"},
        )
        return 2

    reporter.complete(
        status,
        package_id=package_id,
        total_loops=guard.loops,
        total_llm_cost_usd=guard.llm_cost_usd,
        summary={"backend": backend, "producer": result.get("producer")},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
