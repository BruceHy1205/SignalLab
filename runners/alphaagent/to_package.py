"""把 AlphaAgent 原生产出转换成主平台策略包 zip。

接受与 RD-Agent 同构的中间 JSON:
  {producer, factors:[{name,expression,...}], metrics:{ic,...}, ...}
主平台永不 import 本模块。
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from uuid import uuid4


def alphaagent_result_to_package(
    result: dict[str, Any],
    *,
    package_id: str | None = None,
    data_snapshot: str = "qlib_cn_stub",
    universe: str = "csi300",
) -> bytes:
    factors_in = result.get("factors") or []
    if not factors_in:
        raise ValueError("alphaagent result 缺少 factors")
    metrics = result.get("metrics") or {}
    ic = float(metrics.get("ic", -0.02))
    pkg_id = package_id or str(uuid4())
    factors = [
        {
            "name": f["name"],
            "expression": f["expression"],
            "description": f.get("description", ""),
            "hypothesis": f.get("hypothesis", ""),
        }
        for f in factors_in
    ]
    manifest = {
        "schema_version": "1.0",
        "package_id": pkg_id,
        "producer": result.get("producer", "alphaagent@stub"),
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
        zf.writestr("README.md", "# alphaagent package\n")
        zf.writestr(
            "report/metrics.json",
            json.dumps(manifest["metrics_summary"], ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "report/alphaagent_raw.json",
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )
    return buf.getvalue()
