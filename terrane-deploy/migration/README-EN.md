# Terrane backup / migration (docker-compose)

Move a whole Terrane host to a new server, or run routine DR. Scripts in `Scripts/`.

> These scripts target the docker-compose **bundled-database** deployment (the default; they `docker
> compose exec postgres pg_dump`). If you switched to an **external database**, your DB team owns the
> database backup; this script then only needs to capture the `license` volume + `.env` (the KEK).

## Backup (old host, inside the docker-compose deploy dir)

```bash
bash migration/Scripts/backup-terrane.sh           # hot backup (no downtime)
bash migration/Scripts/backup-terrane.sh --final    # final backup (stop app tier, for cutover day)
```
Produces `terrane-migration-<ts>.tar.gz`: **both DB dumps** (terrane_main + terrane_admin), the
**License volume** (active.forge + install_id), **.env** (with the KEK), and a SHA256 manifest.

> The archive contains the KEK + all data — transfer over an encrypted channel only; delete relays after.

## Restore (new host)

Prereqs: Docker+Compose installed; same-version deploy bundle unpacked, `cd docker-compose/`; registry
login configured.

```bash
scp terrane-migration-*.tar.gz user@new-host:/path/terrane-deploy/docker-compose/
bash migration/Scripts/restore-terrane.sh /path/terrane-migration-<ts>.tar.gz
```
It verifies → drops .env → starts PG → restores both DBs → restores the License volume → starts the
full stack → waits for health.

## Verify before cutover

1. Admin login works; front-end KB / memory / conversation data all present.
2. License status `active`.
3. Model channels present; Chat answers.

## Rules

- The **KEK must match byte-for-byte** between old and new `.env`, or encrypted fields are unrecoverable.
- Don't stop the old server or switch DNS/traffic until verification passes.
- If the License drops due to a changed deployment fingerprint, just **re-activate** in the admin with
  the code (install_id migrates with the volume; usually seamless).
- The volume is assumed to be `terrane_license`; if your compose project name differs (`docker volume ls`),
  adjust the script's volume name.
