#!/usr/bin/env bash
# 容器入口:统一走 runner.py;SIGNAL_RUNNER_BACKEND 控制 stub/real。
set -euo pipefail
exec python /opt/runner/runner.py
