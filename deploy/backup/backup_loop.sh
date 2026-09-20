#!/usr/bin/env sh
# compose backup 服务入口:按间隔执行 backup_db.sh
set -eu
INTERVAL="${BACKUP_INTERVAL_SEC:-86400}"
echo "[backup-loop] interval=${INTERVAL}s"
# 启动后稍等 DB 稳定,先跑一轮
sleep 15
while true; do
  /bin/sh /backup/backup_db.sh || echo "[backup-loop] backup failed" >&2
  sleep "${INTERVAL}"
done
