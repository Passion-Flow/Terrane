#!/usr/bin/env bash
# Terrane migration/restore — run on the new server. Prerequisites: Docker + Compose installed, the
# deployment package unpacked and cd'd into the docker-compose directory, and registry login configured.
# Usage: bash migration/Scripts/restore-terrane.sh /path/to/terrane-migration-<timestamp>.tar.gz
set -euo pipefail

ARCHIVE="${1:-}"
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || { echo "Usage: $0 <terrane-migration-*.tar.gz>"; exit 1; }
[[ -f docker-compose.yaml ]] || { echo "✗ Run this from inside Terrane's docker-compose deployment directory"; exit 1; }

echo "→ 1/6 Unpacking…"; WORK=$(mktemp -d); tar xzf "$ARCHIVE" -C "$WORK"
SRC=$(find "$WORK" -maxdepth 1 -type d -name "terrane-migration-*" | head -1)
[[ -n "$SRC" ]] || { echo "✗ Unexpected backup archive structure"; exit 1; }

echo "→ 2/6 Verifying integrity (SHA256)…"
( cd "$SRC" && (shasum -a 256 -c SHA256SUMS 2>/dev/null || sha256sum -c SHA256SUMS 2>/dev/null) ) \
  || { echo "✗ Checksum verification failed, aborting restore"; exit 1; }

echo "→ 3/6 Putting .env in place (the KEK MUST match the old host exactly)…"
cp "$SRC/.env" .env && chmod 600 .env

echo "→ 4/6 Pulling images + starting PostgreSQL alone (runs the DB-creation script on first boot)…"
docker compose pull
docker compose up -d postgres
echo -n "   Waiting for postgres to be ready"
for i in $(seq 1 60); do docker compose exec -T postgres pg_isready -q && break || { echo -n "."; sleep 2; }; done; echo ""
DB_USER=$(grep -E '^DATABASE_USERNAME=' .env | cut -d= -f2-); DB_USER=${DB_USER:-terrane_app}

echo "→ 5/6 Restoring both databases (pg_restore --clean)…"
docker compose exec -T postgres pg_restore -U "$DB_USER" -d terrane_main  --clean --if-exists --no-owner < "$SRC/terrane_main.dump"
docker compose exec -T postgres pg_restore -U "$DB_USER" -d terrane_admin --clean --if-exists --no-owner < "$SRC/terrane_admin.dump"

echo "→ 6/6 Restoring the License volume + starting the full stack…"
[[ -f "$SRC/license.tar.gz" ]] && docker run --rm -v terrane_license:/lic -v "$SRC":/in alpine sh -c "tar xzf /in/license.tar.gz -C /lic" 2>/dev/null || true
docker compose up -d
echo -n "   Waiting for terrane-server to become healthy"
for i in $(seq 1 60); do
  st=$(docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep terrane-server | awk '{print $2}')
  [[ "$st" == "healthy" ]] && break || { echo -n "."; sleep 3; }
done; echo ""

rm -rf "$WORK"
echo ""
echo "✓ Restore complete. Verify: admin login works (with the post-change-password account), front-end knowledge-base/memory data is present, License status is active."
echo "  Until everything checks out, do NOT switch traffic over and do NOT shut down the old server. If the License drops because the deployment fingerprint changed, just re-activate with the activation code in the admin console."
