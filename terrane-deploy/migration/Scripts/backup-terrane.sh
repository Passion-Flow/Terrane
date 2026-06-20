#!/usr/bin/env bash
# Terrane 迁移/备份 — 在 docker-compose 部署目录内执行(docker-compose.yaml 与 .env 所在目录)。
#   bash migration/Scripts/backup-terrane.sh           # 热备份(不停服)
#   bash migration/Scripts/backup-terrane.sh --final    # 终备份(停应用层冻结写入,正式割接用)
# 产物:terrane-migration-<时间戳>.tar.gz(双库 dump + license 卷 + .env + 校验清单)
set -euo pipefail

FINAL=0
[[ "${1:-}" == "--final" ]] && FINAL=1
[[ -f docker-compose.yaml && -f .env ]] || { echo "✗ 请在 Terrane 的 docker-compose 部署目录内执行"; exit 1; }

DB_USER=$(grep -E '^DATABASE_USERNAME=' .env | cut -d= -f2- || true); DB_USER=${DB_USER:-terrane_app}

# KEK 在场校验 —— 没有它,恢复后 SMTP/2FA/凭据密文永远解不开
KEK=$(grep -E '^TERRANE_KEK=' .env | cut -d= -f2- || true)
[[ -n "$KEK" && "$KEK" != "#REPLACE_ME#" ]] || { echo "✗ .env 中 TERRANE_KEK 缺失/未填,先修复"; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S); WORK="terrane-migration-${STAMP}"; mkdir -p "$WORK"

if [[ $FINAL -eq 1 ]]; then
  echo "→ 终备份:停应用层(postgres/redis 保持运行)冻结写入…"
  docker compose stop terrane-server terrane-admin-server terrane-gateway terrane-web terrane-admin-web
fi

echo "→ 1/4 导出双库(terrane_main + terrane_admin,pg_dump -Fc)…"
docker compose exec -T postgres pg_dump -U "$DB_USER" -d terrane_main  -Fc > "$WORK/terrane_main.dump"
docker compose exec -T postgres pg_dump -U "$DB_USER" -d terrane_admin -Fc > "$WORK/terrane_admin.dump"

echo "→ 2/4 备份 License 共享卷(active.forge + install_id,反克隆部署身份)…"
docker run --rm -v terrane_license:/lic -v "$PWD/$WORK":/out alpine tar czf /out/license.tar.gz -C /lic . 2>/dev/null \
  || echo "  (license 卷名非默认?用 docker volume ls 查 *_license 后手动备份)"

echo "→ 3/4 复制 .env(含 KEK —— 最敏感文件)…"
cp .env "$WORK/.env"; chmod 600 "$WORK/.env"

echo "→ 4/4 生成校验清单并打包…"
( cd "$WORK" && (shasum -a 256 * .env 2>/dev/null || sha256sum * .env 2>/dev/null) ) > "$WORK/SHA256SUMS" || true
tar czf "${WORK}.tar.gz" "$WORK"; rm -rf "$WORK"; chmod 600 "${WORK}.tar.gz"

[[ $FINAL -eq 1 ]] && { echo "→ 重新拉起应用层…"; docker compose up -d; }

echo ""
echo "✓ 备份完成:${WORK}.tar.gz"
echo "  ⚠ 含 KEK 与全部数据:仅经加密通道(scp/sftp)传输,落地后尽快删中转副本。"
echo "  下一步:scp 到新服务器 → restore-terrane.sh(见 migration/README-CN.md)"
