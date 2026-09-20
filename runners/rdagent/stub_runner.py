"""兼容入口:转发到统一 runner(默认 stub 后端)。"""

from __future__ import annotations

from runner import main

if __name__ == "__main__":
    raise SystemExit(main())
