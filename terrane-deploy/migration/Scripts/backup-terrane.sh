#!/usr/bin/env bash
# Terrane migration/backup — run from inside the docker-compose deployment directory (where
# docker-compose.yaml and .env live).
#   bash migration/Scripts/backup-terrane.sh           # hot backup (no downtime)
#   bash migration/Scripts/backup-terrane.sh --final    # final backup (stops the app layer to freeze writes; for the actual cutover)
# Output: terrane-migration-<timestamp>.tar.gz (both DB dumps + license volume + .env + checksum manifest)
set -euo pipefail

FINAL=0
[[ "${1:-}" == "--final" ]] && FINAL=1
[[ -f docker-compose.yaml && -f .env ]] || { echo "✗ Run this from inside Terrane's docker-compose deployment directory"; exit 1; }

DB_USER=$(grep -E '^DATABASE_USERNAME=' .env | cut -d= -f2- || true); DB_USER=${DB_USER:-terrane_app}

# KEK presence check — without it, SMTP/2FA/credential ciphertext can never be decrypted after restore
KEK=$(grep -E '^TERRANE_KEK=' .env | cut -d= -f2- || true)
[[ -n "$KEK" && "$KEK" != "#REPLACE_ME#" ]] || { echo "✗ TERRANE_KEK is missing/unset in .env — fix that first"; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S); WORK="terrane-migration-${STAMP}"; mkdir -p "$WORK"

if [[ $FINAL -eq 1 ]]; then
  echo "→ Final backup: stopping the app layer (postgres/redis stay up) to freeze writes…"
  docker compose stop terrane-server terrane-admin-server terrane-gateway terrane-web terrane-admin-web
fi

echo "→ 1/4 Dumping both databases (terrane_main + terrane_admin, pg_dump -Fc)…"
docker compose exec -T postgres pg_dump -U "$DB_USER" -d terrane_main  -Fc > "$WORK/terrane_main.dump"
docker compose exec -T postgres pg_dump -U "$DB_USER" -d terrane_admin -Fc > "$WORK/terrane_admin.dump"

echo "→ 2/4 Backing up the shared License volume (active.forge + install_id, anti-clone deployment identity)…"
docker run --rm -v terrane_license:/lic -v "$PWD/$WORK":/out alpine tar czf /out/license.tar.gz -C /lic . 2>/dev/null \
  || echo "  (License volume not using the default name? Find it with 'docker volume ls' (*_license) and back it up manually.)"

echo "→ 3/4 Copying .env (contains the KEK — the most sensitive file)…"
cp .env "$WORK/.env"; chmod 600 "$WORK/.env"

echo "→ 4/4 Generating the checksum manifest and archiving…"
( cd "$WORK" && (shasum -a 256 * .env 2>/dev/null || sha256sum * .env 2>/dev/null) ) > "$WORK/SHA256SUMS" || true
tar czf "${WORK}.tar.gz" "$WORK"; rm -rf "$WORK"; chmod 600 "${WORK}.tar.gz"

[[ $FINAL -eq 1 ]] && { echo "→ Bringing the app layer back up…"; docker compose up -d; }

echo ""
echo "✓ Backup complete: ${WORK}.tar.gz"
echo "  ⚠ Contains the KEK and all data: transfer only over an encrypted channel (scp/sftp) and delete the intermediate copy as soon as possible."
echo "  Next: scp it to the new server → restore-terrane.sh (see migration/README.md)"
