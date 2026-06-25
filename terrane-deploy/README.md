# terrane-deploy

Production delivery artifacts for **Terrane** — a private-deployment AI knowledge base
(knowledge base / knowledge graph / Chat assistant / Studio / memory). Built for
**private / on-prem / Xinchuang (domestic)** delivery.
Three independent paths — pick one. Each has bilingual guides.

> **5 app images + 2 datastore images** — `terrane-server` (front-end business API) · `terrane-admin-server`
> (admin API) · `terrane-gateway` (Go data plane) · `terrane-web` (front-end SPA) · `terrane-admin-web`
> (admin SPA) · `terrane-postgres` (PG18 + Apache AGE + pgvector) · `terrane-redis` (Redis 7).
> All in one private registry, multi-arch amd64+arm64, tag `v1.0.0`.

## Pick your path

| Artifact | Use when | Guides |
|---|---|---|
| **docker-compose** (`docker-compose/`) | single host / appliance / air-gapped | [README-CN](docker-compose/README-CN.md) · [README-EN](docker-compose/README-EN.md) |
| **Helm** (`helm/`) | Kubernetes (incl. Xinchuang (domestic) K8s) | [README-CN](helm/README-CN.md) · [README-EN](helm/README-EN.md) |
| **GitLab CI/CD** (`gitlab/`) | build + (manual) image push + (manual) deploy | [README-CN](gitlab/README-CN.md) · [README-EN](gitlab/README-EN.md) |
| **Migration** (`migration/`) | backup / whole-host migration / disaster recovery | [README-CN](migration/README-CN.md) · [README-EN](migration/README-EN.md) |

## Directory layout

```
terrane-deploy/
├── docker-compose/
│   ├── docker-compose.yaml     # x-shared-env anchor + 5 app services + bundled PG18-AGE + Redis (single host, started with the stack by default)
│   ├── .env.example            # every entry documented, #REPLACE_ME# placeholders, TERRANE_CA_FILE for a private CA
│   ├── init/01-databases.sql   # creates the two databases terrane_main + terrane_admin
│   ├── Scripts/generate-image-repo-secret.sh
│   └── README-CN.md / README-EN.md
├── helm/
│   ├── terrane/                # chart: values.yaml + templates (server/admin/gateway/web/admin-web/postgres/redis/ingress)
│   ├── Scripts/generate-image-repo-secret.sh
│   └── README-CN.md / README-EN.md
├── gitlab/
│   ├── .gitlab-ci.yml          # lint → build (multi-arch, 6 images) → push (manual) → deploy (manual Helm)
│   ├── Scripts/generate-image-repo-secret-docker.sh / -k8s.sh
│   └── README-CN.md / README-EN.md
└── migration/
    ├── Scripts/backup-terrane.sh / restore-terrane.sh
    └── README-CN.md / README-EN.md
```

## Common conventions

- **Zero-config out of the box** — ships with **no model channels or API keys**; on first run the customer
  enters their own key under "Model Channels" in the admin console.
  The database migrations contain no seed keys, and there are no hard-coded keys in the code.
- **License enforced** — ships locked; requires a Forge-issued activation code (online code or offline
  `.forge`) to activate. The activation credential + install_id land on the shared volume, so activation
  **persists across restarts and is shared across components** (anti-clone double-lock). Pure cryptographic
  verification, no backdoor.
- **Forced password change on the factory super admin's first login** — `terrane@navtra.ai`, initial
  password = email; forced change on first login (delivery security).
- **Private CA** (`TERRANE_CA_FILE` / `global.customCA`) — trust self-signed / private-CA https endpoints
  (Xinchuang (domestic) intranets).
- **Manual image publishing** — CI only builds; pushing is triggered manually after human review.
- **PG18 + AGE + pgvector are hard dependencies** — knowledge graph (AGE) + vector retrieval (pgvector).
  An external DB must provide both extensions.
- **Datastores: defaults per deployment mode** — **docker-compose (single host) ships PG/Redis by default**,
  one command brings everything up, ready to use; **Helm / GitLab (cluster · enterprise) default to external
  PG/Redis** (`postgres.enabled/redis.enabled=false`, connecting to your existing infrastructure), with the
  bundled DB reserved for single-host/demo use (set `enabled=true` in Helm). Both are interchangeable
  (comment out the bundled compose services to use external ones).
- **Required `#REPLACE_ME#` fields** — the KEK, DB/Redis passwords (and Helm's external hosts) all ship as
  `#REPLACE_ME#` placeholders and must be filled in (the Helm NOTES will warn otherwise).

## First-run, three steps (same for every deployment path)

1. **Activate the License** (admin console) → 2. **Super-admin password change + setup wizard** →
3. **Configure model channels (fill in your own key)**.
After that the full front app (knowledge base / graph / Chat / Studio / memory) is ready.

---

Start with the README-CN / README-EN for your chosen path in the table above.
