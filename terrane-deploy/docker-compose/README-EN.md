# Terrane deploy — docker-compose (single host / on-prem / air-gapped)

One command brings up the full stack incl. bundled PostgreSQL 18 (+ Apache AGE + pgvector) and Redis.

## 0. Prerequisites

- One Linux host (2C4G min, 4C8G recommended; **CPU only, no GPU**) with Docker + Compose plugin.
- Access to the image registry (Aliyun ACR / internal Harbor), or pre-loaded image tarballs.
- Your own model API key (not shipped — set it in the admin console on first run).
- A Forge-issued License activation code (online code or offline `.forge`).

## 1. Configure

```bash
cd terrane-deploy/docker-compose
cp .env.example .env
# Fill every #REPLACE_ME# in .env:
#   TERRANE_KEK         openssl rand -base64 32   ← back this up; lost = existing ciphertext unrecoverable
#   DATABASE_PASSWORD   strong random
#   CACHE_PASSWORD      strong random
#   TERRANE_FORGE_EDGE_URL  your Forge edge (leave empty for offline activation)
#   SESSION_COOKIE_SECURE   true behind HTTPS (false for a plain-HTTP trial)
```

Private registry login: `bash Scripts/generate-image-repo-secret.sh <registry> <user> <pass>`

## 2. Start (bundled datastores — one command)

docker-compose is the single-host appliance path: it ships **PostgreSQL 18 + AGE + pgvector and Redis,
started with the stack by default** — no external services needed.

```bash
docker compose pull        # or: docker compose up -d --build to build on site
docker compose up -d
docker compose ps          # wait for 7 containers healthy
```

> To use your own EXTERNAL PG/Redis instead: set `DATABASE_HOST` / `CACHE_HOST` in `.env` (the PG must
> have the `age`+`vector` extensions) and comment out the `postgres` / `redis` services in
> docker-compose.yaml. (For cluster/enterprise, use Helm — it defaults to external; see `../helm/`.)

## 3. First-run (admin at `http://<host>:8081`)

1. **Activate License** — paste the Forge code. Credential + install_id persist on the shared
   `license` volume (survives restart; all components share one deployment identity / anti-clone lock).
2. **Super-admin login + change password** — factory account `terrane@navtra.ai`, initial password =
   email, **forced change on first login**; then run the setup wizard.
3. **Configure model channels** — admin → Model Channels → add chat/embed/rerank/vl/asr/tts with
   **your own API key** (ships with zero channels / zero keys). The front app then works fully.

Front app: `http://<host>:80`.

## 4. HTTPS (production)

Put Nginx/Caddy in front, terminate TLS on 443, then set `SESSION_COOKIE_SECURE=true` (else the
browser drops the cookie over HTTPS). For a private-CA intranet, set `TERRANE_CA_FILE` to your CA bundle.

## 5. Operations

- Logs: `docker compose logs -f terrane-server`
- Upgrade: `docker compose pull && docker compose up -d` (pgdata / license volumes kept)
- Backup / migrate: see `../migration/README-EN.md`
- Keep the `license` volume; back up `TERRANE_KEK` with the data.

## 6. Offline / domestic (信创)

- Offline: `docker save` the 6 images on a connected host → `docker load` on the intranet → up. Use an
  offline `.forge` license (leave the edge URL empty).
- External domestic PG must provide the `age` + `vector` extensions (hard requirement for the graph +
  vector retrieval); point `DATABASE_*` at it and comment out the bundled `postgres` service.
