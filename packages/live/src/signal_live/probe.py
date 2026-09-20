"""miniQMT 连通探测 CLI(仅 Windows host 有意义)。

用法:
  uv run python -m signal_live.probe
  LIVE_MINIQMT_ACCOUNT=xxx LIVE_MINIQMT_PATH=D:\\...\\userdata_mini \\
    uv run python -m signal_live.probe
"""

from __future__ import annotations

import json
import os

from signal_live.broker import MiniqmtBroker


def main() -> int:
    account = os.environ.get("LIVE_MINIQMT_ACCOUNT", "")
    path = os.environ.get("LIVE_MINIQMT_PATH", "")
    broker = MiniqmtBroker(account=account, path=path)
    info = broker.probe()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info.get("connected") else 1


if __name__ == "__main__":
    raise SystemExit(main())
