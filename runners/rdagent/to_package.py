"""把 RD-Agent(fin_factor)原生产出转换成主平台策略包 zip。

真实 RD-Agent 产出通常为 hypothesis/expression/metrics 目录结构;
本转换器接受一个简化中间 JSON(或 stub 生成的同等结构),写出合法策略包。
主平台永不 import 本模块。
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4


def rdagent_result_to_package(
    result: dict[str, Any],
    *,
    package_id: str | None = None,
    data_snapshot: str = "qlib_cn_stub",
    universe: str = "csi300",
) -> bytes:
    """result 期望字段:
    - factors: [{name, expression, description?, hypothesis?}, ...]
    - metrics: {ic, icir?, arr, mdd, turnover?}
    - backtest_start / backtest_end (可选)
    """
    factors_in = result.get("factors") or []
    if not factors_in:
        raise ValueError("rdagent result 缺少 factors")
    metrics = result.get("metrics") or {}
    ic = float(metrics.get("ic", -0.02))
    # 与 stub 一致:声称 IC 与反转类因子方向对齐时可为负
    pkg_id = package_id or str(uuid4())
    factors = []
    for f in factors_in:
        factors.append(
            {
                "name": f["name"],
                "expression": f["expression"],
                "description": f.get("description", ""),
                "hypothesis": f.get("hypothesis", ""),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "package_id": pkg_id,
        "producer": result.get("producer", "rdagent@stub"),
        "created_at": datetime.now(UTC).isoformat(),
        "data_snapshot": data_snapshot,
        "universe": universe,
        "backtest_start": result.get("backtest_start", "2024-01-01"),
        "backtest_end": result.get("backtest_end", "2024-12-31"),
        "metrics_summary": {
            "ic": ic,
            "icir": metrics.get("icir", 0.4),
            "arr": float(metrics.get("arr", 0.1)),
            "mdd": float(metrics.get("mdd", -0.1)),
            "turnover": metrics.get("turnover", 0.25),
        },
        "signal_protocol": "qlib_expression",
        "factors": factors,
    }
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("README.md", "# rdagent package\n")
        zf.writestr(
            "report/metrics.json",
            json.dumps(manifest["metrics_summary"], ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "report/rdagent_raw.json",
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )
    return buf.getvalue()


def load_result_dir(path: Path) -> dict[str, Any]:
    """从目录读取 stub/真实转换中间结果 result.json。"""
    p = path / "result.json"
    if not p.exists():
        raise FileNotFoundError(p)
    return json.loads(p.read_text(encoding="utf-8"))
