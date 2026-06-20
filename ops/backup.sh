#!/usr/bin/env bash
# Terrane 备份(三件套之一:PG 逻辑备份)。pg_dump 双库 → 带时间戳目录 + manifest + sha256。
# 对象存储/异地与 git 快照由部署侧编排(rclone/restic + 该脚本)。RPO≤1h(cron 每小时)。
set -euo pipefail
PG_CONTAINER="${PG_CONTAINER:-terrane-pg}"
PG_USER="${PG_USER:-terrane_app}"
OUT_DIR="${BACKUP_DIR:-/tmp/terrane-backups}/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
for db in terrane_admin terrane_main; do
  docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -Fc "$db" > "$OUT_DIR/$db.dump"
  sha256sum "$OUT_DIR/$db.dump" 2>/dev/null || shasum -a 256 "$OUT_DIR/$db.dump"
done > "$OUT_DIR/SHA256SUMS"
cat > "$OUT_DIR/manifest.json" <<EOF
{"created_utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","databases":["terrane_admin","terrane_main"],"format":"pg_dump custom","tool":"terrane/ops/backup.sh"}
EOF
echo "BACKUP_OK $OUT_DIR"
