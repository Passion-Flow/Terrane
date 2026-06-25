# Terrane backup / migration (docker-compose deployment)

Move a whole Terrane host to a new server, or run routine disaster recovery. Scripts are in `Scripts/`.

> Applies to docker-compose deployments **using the bundled database** (the default — the scripts use
> `docker compose exec postgres pg_dump` to dump the databases).
> If you switched to an **external database**, the database backup is handled on your PG side; these scripts
> only need to back up the `license` volume + `.env` (KEK), and you use your DBA's dump/restore process for
> the database.

## Backup (old server, run inside the docker-compose deployment directory)

```bash
bash migration/Scripts/backup-terrane.sh           # hot backup (no downtime; good for drills/routine)
bash migration/Scripts/backup-terrane.sh --final    # final backup (stops the app layer to freeze writes; for the actual cutover day)
```
Output `terrane-migration-<timestamp>.tar.gz`, containing: **both DB dumps** (terrane_main + terrane_admin),
the **License volume** (active.forge + install_id), **.env** (with the KEK), and a SHA256 checksum manifest.

> ⚠ The archive contains the KEK and all data. Transfer only over an encrypted channel (scp/sftp), and delete
> the intermediate copy as soon as possible after landing.

## Restore (new server)

Prerequisites: Docker + Compose installed; the same-version deployment package unpacked and `cd`'d into
`docker-compose/`; registry login configured.

```bash
scp terrane-migration-*.tar.gz user@new-host:/path/terrane-deploy/docker-compose/
# On the new server:
bash migration/Scripts/restore-terrane.sh /path/terrane-migration-<timestamp>.tar.gz
```
The script will: verify → put .env in place → start PG → restore both databases → restore the License volume
→ start the full stack → wait for health.

## Verification checklist (must pass before switching traffic)

1. Admin login works (with the post-change-password super-admin account); the front-end knowledge base / memory
   / conversation-history data is all present.
2. License status is `active` (License card in the admin console).
3. Model channels are present and Chat answers normally.

## Key rules

- **The KEK must match exactly**: the new host's `.env` `TERRANE_KEK` must equal the old host's, otherwise the
  SMTP/2FA/credential ciphertext cannot be decrypted.
- **Do not shut down the old server and do not switch DNS/traffic until everything has been verified.**
- License dropped because the deployment fingerprint changed: this is normal — just **re-activate** in the admin
  console with the activation code (install_id has migrated with the volume, so in most cases it's seamless).
- The volume name is assumed to be the default `terrane_license`; if your compose project name differs
  (check with `docker volume ls`), adjust the scripts to the actual volume name.
