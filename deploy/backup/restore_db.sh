#!/usr/bin/env sh
# 从 gzip SQL 备份恢复(会覆盖目标库中的同名对象;演练前请确认)。
# 用法:
#   PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=... ./restore_db.sh /path/to/signal-XXX.sql.gz
set -eu

ARCHIVE="${1:-}"
if [ -z "${ARCHIVE}" ] || [ ! -f "${ARCHIVE}" ]; then
  echo "Usage: $0 <backup.sql.gz>" >&2
  exit 2
fi

echo "[restore] restoring ${ARCHIVE} into ${PGDATABASE:-?}@${PGHOST:-?}"
gunzip -c "${ARCHIVE}" | psql -v ON_ERROR_STOP=1
echo "[restore] done"
