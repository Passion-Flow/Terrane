#!/usr/bin/env bash
# Terrane 迁移/恢复 — 新服务器执行。前置:已装 Docker+Compose、已解压部署包并 cd 进 docker-compose 目录、
# 已配镜像仓库登录。用法:bash migration/Scripts/restore-terrane.sh /path/to/terrane-migration-<时间戳>.tar.gz
set -euo pipefail

ARCHIVE="${1:-}"
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || { echo "用法: $0 <terrane-migration-*.tar.gz>"; exit 1; }
[[ -f docker-compose.yaml ]] || { echo "✗ 请在 Terrane 的 docker-compose 部署目录内执行"; exit 1; }

echo "→ 1/6 解包…"; WORK=$(mktemp -d); tar xzf "$ARCHIVE" -C "$WORK"
SRC=$(find "$WORK" -maxdepth 1 -type d -name "terrane-migration-*" | head -1)
[[ -n "$SRC" ]] || { echo "✗ 备份包结构不对"; exit 1; }

echo "→ 2/6 校验完整性(SHA256)…"
( cd "$SRC" && (shasum -a 256 -c SHA256SUMS 2>/dev/null || sha256sum -c SHA256SUMS 2>/dev/null) ) \
  || { echo "✗ 校验失败,停止恢复"; exit 1; }

echo "→ 3/6 落位 .env(KEK 必须与旧机逐字一致)…"
cp "$SRC/.env" .env && chmod 600 .env

echo "→ 4/6 拉镜像 + 单独启动 PostgreSQL(首启执行建库脚本)…"
docker compose pull
docker compose up -d postgres
echo -n "   等待 postgres 就绪"
for i in $(seq 1 60); do docker compose exec -T postgres pg_isready -q && break || { echo -n "."; sleep 2; }; done; echo ""
DB_USER=$(grep -E '^DATABASE_USERNAME=' .env | cut -d= -f2-); DB_USER=${DB_USER:-terrane_app}

echo "→ 5/6 恢复双库(pg_restore --clean)…"
docker compose exec -T postgres pg_restore -U "$DB_USER" -d terrane_main  --clean --if-exists --no-owner < "$SRC/terrane_main.dump"
docker compose exec -T postgres pg_restore -U "$DB_USER" -d terrane_admin --clean --if-exists --no-owner < "$SRC/terrane_admin.dump"

echo "→ 6/6 恢复 License 卷 + 启动全栈…"
[[ -f "$SRC/license.tar.gz" ]] && docker run --rm -v terrane_license:/lic -v "$SRC":/in alpine sh -c "tar xzf /in/license.tar.gz -C /lic" 2>/dev/null || true
docker compose up -d
echo -n "   等待 terrane-server 健康"
for i in $(seq 1 60); do
  st=$(docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep terrane-server | awk '{print $2}')
  [[ "$st" == "healthy" ]] && break || { echo -n "."; sleep 3; }
done; echo ""

rm -rf "$WORK"
echo ""
echo "✓ 恢复完成。验证:后台能登(改密后账号)、前台知识库/记忆数据在、License 状态 active。"
echo "  验证全过前,不要切流量、不要关旧服务器。License 若因部署指纹变化掉证,在后台用激活码重激活即可。"
