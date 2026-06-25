# Terrane deploy — Helm (Kubernetes, incl. Xinchuang (domestic) K8s)

Ships with PostgreSQL 18 + AGE + pgvector and Redis bundled (all inside the chart, no bitnami subcharts —
**air-gap friendly**). 5 app components + the data-plane gateway.

## 0. Prerequisites

- A K8s cluster (1.24+) with a default StorageClass (RWO volumes for PG/Redis).
- **If the control plane needs multiple replicas or cross-node scheduling**: the shared License volume needs
  a **ReadWriteMany** storage class (NFS/CephFS); otherwise keep it single-replica (default).
- An Ingress controller (nginx by default).
- Registry access + image-pull secret.
- A Forge activation code + your own model key.

## 1. Image-pull secret

```bash
bash Scripts/generate-image-repo-secret.sh <robot-user> '<pass>' terrane https://crpi-xxx.cr.aliyuncs.com
```

## 2. Install (release name MUST be `terrane`)

> The web nginx reverse-proxies `/api` to the fixed Service names `terrane-server` / `terrane-admin-server`,
> so the **release must be named `terrane`**.

Private-deployment default: **the bundled PG/Redis are OFF (`postgres.enabled=false`/`redis.enabled=false`);
use your own external database + cache** (externalDatabase / externalRedis). Replace every `#REPLACE_ME#`
in values.yaml.

```bash
helm upgrade --install terrane terrane-deploy/helm/terrane -n terrane --create-namespace \
  --set secret.kek=$(openssl rand -base64 32) \
  --set externalDatabase.host=<your-pg-host> --set externalDatabase.password=<pg-pass> \
  --set externalRedis.host=<your-redis-host> --set externalRedis.password=<redis-pass> \
  --set license.forgeEdgeUrl=http://<your-forge-edge>:8081 \
  --set global.domain=terrane.example.com \
  --set global.adminDomain=admin.terrane.example.com
# ⚠ The external PostgreSQL MUST provide the age + vector extensions and be able to reach the two databases terrane_main / terrane_admin.
```

Single-host quick start (bundled PG/Redis, non-production): also add
`--set postgres.enabled=true --set postgres.password=$(openssl rand -base64 24) --set redis.enabled=true --set redis.password=$(openssl rand -base64 24)`.

> Back up the KEK separately; losing it makes existing ciphertext (SMTP/2FA/credentials) permanently unrecoverable.

## 3. Wait + first-run

```bash
kubectl -n terrane get pods -w     # admin-server auto-migrates + bootstraps the super admin
```
1. Admin console `https://admin.terrane.example.com` → **Activate License**.
2. Super admin `terrane@navtra.ai` (initial password = email) → **forced password change on first login** + wizard.
3. Model Channels → fill in **your own key** (ships with zero channels). Front app `https://terrane.example.com` is live.

## 4. Key values

| key | meaning |
|---|---|
| `secret.kek` | **required**, field-encryption master key |
| `postgres.enabled` | false → external PG (must have `age`+`vector` extensions), fill `externalDatabase.*` |
| `redis.enabled` | false → external Redis, fill `externalRedis.*` |
| `license.accessMode` | set `ReadWriteMany` + RWX storageClass for multi-replica/cross-node |
| `global.useTLS` | false = HTTP trial (cookie not Secure); true for production |
| `global.customCA` | trust an intranet private-CA (Xinchuang (domestic)) certificate |
| `ingress.*` | front/admin dual hosts + TLS secrets |

## 5. Upgrade / uninstall

```bash
# Upgrade: bump each component's image.tag in values.yaml, or per-service --set:
helm upgrade terrane terrane-deploy/helm/terrane -n terrane --reuse-values \
  --set server.image.tag=v1.0.1 --set adminServer.image.tag=v1.0.1 \
  --set gateway.image.tag=v1.0.1 --set web.image.tag=v1.0.1 \
  --set adminWeb.image.tag=v1.0.1 --set postgres.image.tag=v1.0.1 \
  --set redis.image.tag=v1.0.1
helm uninstall terrane -n terrane     # PVCs (pgdata/redis/license) kept by default; clean up manually as needed
```

## 6. Xinchuang (domestic) / offline

- Images: `docker save` → `docker load` on the intranet → push to an internal Harbor → point each component's
  `image.repository` at it (one per service in values.yaml).
- Offline License: leave `license.forgeEdgeUrl` empty and paste an offline `.forge` in the admin console.
- External Xinchuang (domestic) PG: must provide `age`+`vector` (hard dependency for the knowledge graph + vector retrieval).
- Multi-arch images already include arm64, compatible with Kunpeng/Phytium.
