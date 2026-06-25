# Terrane deploy — docker-compose (single host / on-prem / offline)

Use when: a single Linux server, an appliance, or an air-gapped intranet. One command brings up the full
stack (incl. bundled PG18+AGE+pgvector and Redis).

## 0. Prerequisites

- One Linux host (2C4G min, 4C8G recommended; **CPU only, no GPU**) with Docker + the Docker Compose plugin.
- Access to the image registry (Aliyun ACR / internal Harbor), or images pre-loaded from tarballs.
- Your own model API key (not shipped — set it in the admin console on first run).
- A Forge-issued License activation code (online code or offline `.forge`).

## 1. Configure

```bash
cd terrane-deploy/docker-compose
cp .env.example .env
# Edit .env and fill every #REPLACE_ME#:
#   TERRANE_KEK          openssl rand -base64 32   ← back this up; lose it and existing ciphertext is unrecoverable
#   DATABASE_PASSWORD    strong random
#   CACHE_PASSWORD       strong random
#   TERRANE_FORGE_EDGE_URL  your Forge issuing edge (leave empty for offline activation)
#   SESSION_COOKIE_SECURE   set true for HTTPS deployment (keep false for an HTTP trial)
```

> Private registry login first: `bash Scripts/generate-image-repo-secret.sh <registry> <user> <pass>`

## 2. Start (bundled datastores, one command brings everything up)

docker-compose is the single-host appliance path: it **ships PG18+AGE+pgvector and Redis, started with the
stack by default** — no external services needed.

```bash
docker compose pull        # use registry images; to build on site: docker compose up -d --build
docker compose up -d
docker compose ps          # wait for 7 containers to become healthy
```

Containers that come up: `postgres` (PG18+AGE+pgvector) / `redis` / `terrane-server` (front-end API) /
`terrane-admin-server` (admin API, auto-runs migrations + bootstraps the super admin) / `terrane-gateway` /
`terrane-web` (front app) / `terrane-admin-web` (admin console).

> To connect to your **existing external PG/Redis** (instead of the bundled ones): point
> `DATABASE_HOST`/`CACHE_HOST` in `.env` at them (the PG must include the `age`+`vector` extensions) and
> comment out the `postgres`/`redis` services in `docker-compose.yaml`.
> (For cluster/enterprise, use Helm — it defaults to external databases; see `../helm/`.)

## 3. First-run, three steps (admin console at `http://<host>:8081`)

1. **Activate License** — enter the Forge activation code. The activation credential + install_id land on the
   shared `license` volume, so activation **persists across restarts and is shared by all three components**
   (anti-clone double-lock).
2. **Super-admin login + change password** — factory account `terrane@navtra.ai`, initial password = email,
   **forced change on first login**; then run the setup wizard (email / branding).
3. **Configure model channels** — admin console → "Model Channels" → add chat / embed / rerank / vl / asr / tts,
   **filling in your own API key** (ships with zero channels and zero keys). Once configured, the full front
   app (knowledge base / graph / Chat / Studio / memory) is ready.

Front app: `http://<host>:80`.

## 4. HTTPS (required for production)

Put an Nginx / Caddy reverse proxy in front, terminate 80 / 8081 onto 443 with certificates, then set
`SESSION_COOKIE_SECURE=true` in `.env` (otherwise the browser drops the cookie over HTTPS and the login
session won't stick). For an intranet private-CA certificate, set its CA bundle path in `TERRANE_CA_FILE`.

## 5. Operations

- **Logs**: `docker compose logs -f terrane-server`
- **Upgrade**: `docker compose pull && docker compose up -d` (pgdata / license volumes kept)
- **Backup / migrate**: see `../migration/README-CN.md` (`backup-terrane.sh` / `restore-terrane.sh`)
- ⚠ Don't lose the `license` volume — losing it means you must re-activate; back up `TERRANE_KEK` together with the data.

## 6. Offline / Xinchuang (domestic)

- Offline: on a connected machine `docker save` the 6 images → copy to the intranet → `docker load` →
  `docker compose up -d`; activate the License with an offline `.forge` (leave the edge URL empty).
- External Xinchuang (domestic) PG: must provide the `age` + `vector` extensions (hard dependency for the
  knowledge graph and vector retrieval); point `DATABASE_*` at it and comment out the bundled `postgres` service.
