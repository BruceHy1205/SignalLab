"""runners/rdagent/to_package 转换器冒烟(动态加载,不进主平台依赖)。"""

from __future__ import annotations

import importlib.util
import json
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RD_TO_PACKAGE = ROOT / "runners" / "rdagent" / "to_package.py"


def _load_to_package():
    spec = importlib.util.spec_from_file_location("rdagent_to_package", RD_TO_PACKAGE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rdagent_to_package_zip():
    mod = _load_to_package()
    data = mod.rdagent_result_to_package(
        {
            "producer": "rdagent@stub",
            "factors": [
                {
                    "name": "rd_rev_1d",
                    "expression": "Ref($close, 1) / $close - 1",
                    "hypothesis": "h",
                }
            ],
            "metrics": {"ic": -0.02, "arr": 0.1, "mdd": -0.08},
        }
    )
    with zipfile.ZipFile(BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["producer"] == "rdagent@stub"
    assert manifest["factors"][0]["name"] == "rd_rev_1d"
    assert manifest["signal_protocol"] == "qlib_expression"
