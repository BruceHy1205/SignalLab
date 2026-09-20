#!/usr/bin/env sh
# 备份 PostgreSQL/TimescaleDB 到本地目录,可选上传 S3 兼容存储。
# 用法:
#   PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=... ./backup_db.sh
#   BACKUP_S3_URI=s3://bucket/prefix ./backup_db.sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/var/backups/signal}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/signal-${STAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"
echo "[backup] dumping to ${OUT}"
pg_dump --no-owner --format=plain | gzip -c >"${OUT}"
ls -lh "${OUT}"

if [ -n "${BACKUP_S3_URI:-}" ]; then
  if command -v aws >/dev/null 2>&1; then
    DEST="${BACKUP_S3_URI%/}/signal-${STAMP}.sql.gz"
    echo "[backup] uploading ${DEST}"
    if [ -n "${S3_ENDPOINT_URL:-}" ]; then
      aws --endpoint-url "${S3_ENDPOINT_URL}" s3 cp "${OUT}" "${DEST}"
    else
      aws s3 cp "${OUT}" "${DEST}"
    fi
  else
    echo "[backup] aws cli not found; skip upload (install aws-cli in image if needed)" >&2
  fi
fi

# 清理过期本地备份
find "${BACKUP_DIR}" -type f -name 'signal-*.sql.gz' -mtime "+${BACKUP_KEEP_DAYS}" -print -delete || true
echo "[backup] done"
