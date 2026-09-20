#!/usr/bin/env bash
# 迁移后启动 API。DATABASE_URL 由 compose/.env 注入。
set -euo pipefail
cd /app/apps/api
echo "[api] alembic upgrade head"
alembic upgrade head
echo "[api] starting uvicorn"
exec uvicorn signal_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
