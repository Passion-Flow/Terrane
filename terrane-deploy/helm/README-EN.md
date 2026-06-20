# Terrane deploy — Helm (Kubernetes, incl. domestic K8s)

Self-contained: bundled PostgreSQL 18 + AGE + pgvector and Redis live in the chart (no bitnami
subcharts — air-gap friendly). 5 app components + the data-plane gateway.

## 0. Prerequisites

- A K8s cluster (1.24+) with a default StorageClass (RWO for PG/Redis).
- If the control plane needs >1 replica or cross-node scheduling, the shared License volume needs a
  **ReadWriteMany** class (NFS/CephFS); otherwise keep it single-replica (default).
- An Ingress controller (nginx by default).
- Registry access + image-pull secret. A Forge activation code + your own model key.

## 1. Image-pull secret

```bash
bash Scripts/generate-image-repo-secret.sh <robot-user> '<pass>' terrane https://crpi-xxx.cr.aliyuncs.com
```

## 2. Install (release name MUST be `terrane`)

The web nginx proxies `/api` to fixed Service names `terrane-server` / `terrane-admin-server`, so the
release must be named `terrane`.

Private-deployment default: the bundled PG/Redis are OFF (`postgres.enabled=false`/`redis.enabled=false`);
you point at your own external database + cache. Replace every `#REPLACE_ME#` in values.yaml.

```bash
helm upgrade --install terrane terrane-deploy/helm/terrane -n terrane --create-namespace \
  --set secret.kek=$(openssl rand -base64 32) \
  --set externalDatabase.host=<your-pg-host> --set externalDatabase.password=<pg-pass> \
  --set externalRedis.host=<your-redis-host> --set externalRedis.password=<redis-pass> \
  --set license.forgeEdgeUrl=http://<forge-edge>:8081 \
  --set global.domain=terrane.example.com \
  --set global.adminDomain=admin.terrane.example.com
# The external PostgreSQL MUST provide the age + vector extensions and reach terrane_main / terrane_admin.
```

Single-host quick start (bundled PG/Redis, non-production): also add
`--set postgres.enabled=true --set postgres.password=... --set redis.enabled=true --set redis.password=...`.

Back up the KEK separately; losing it makes existing ciphertext unrecoverable.

## 3. First-run

```bash
kubectl -n terrane get pods -w     # admin-server auto-migrates + bootstraps the super admin
```
1. Admin `https://admin.terrane.example.com` → **Activate License**.
2. Super admin `terrane@navtra.ai` (initial password = email) → **forced password change** + wizard.
3. Model Channels → fill **your own key**. Front app `https://terrane.example.com` is live.

## 4. Key values

| key | meaning |
|---|---|
| `secret.kek` | **required** field-encryption master key |
| `postgres.enabled` | false → external PG (must have `age`+`vector`), fill `externalDatabase.*` |
| `redis.enabled` | false → external Redis (`externalRedis.*`) |
| `license.accessMode` | `ReadWriteMany` + RWX class for multi-replica/cross-node |
| `global.useTLS` | false = HTTP trial (cookie not Secure); true for production |
| `global.customCA` | trust a private-CA (信创 intranet) |
| `ingress.*` | front/admin hosts + TLS secrets |

## 5. Upgrade / uninstall

```bash
# Upgrade: bump each component's image.tag in values.yaml, or per-service --set:
helm upgrade terrane terrane-deploy/helm/terrane -n terrane --reuse-values \
  --set server.image.tag=v1.0.1 --set adminServer.image.tag=v1.0.1 \
  --set gateway.image.tag=v1.0.1 --set web.image.tag=v1.0.1 \
  --set adminWeb.image.tag=v1.0.1 --set postgres.image.tag=v1.0.1 \
  --set redis.image.tag=v1.0.1
helm uninstall terrane -n terrane   # PVCs kept by default
```

## 6. Domestic / offline

`docker save` → `docker load` → internal Harbor → point each component's `image.repository` (one per
service in values.yaml). Offline License: leave
`license.forgeEdgeUrl` empty and paste an offline `.forge`. External domestic PG must provide
`age`+`vector`. Images are multi-arch (arm64 included — Kunpeng/Phytium).
