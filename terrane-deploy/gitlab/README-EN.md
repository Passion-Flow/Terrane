# Terrane deploy — GitLab CI/CD

Pipeline **build → (manual) push → (manual) Helm deploy**. Images are never pushed automatically; a
human triggers the push after verification.

## Stages

| Stage | What | Trigger |
|---|---|---|
| `lint` | backend ruff (advisory) + **frontend tsc+vite build** (hard gate) | auto |
| `build` | buildx multi-arch (amd64+arm64) for 7 images, **no push** | auto (branch) |
| `push` | registry login + multi-arch push of 7 images | **manual** |
| `deploy` | Helm upgrade --install onto K8s | **manual** |

7 images: terrane-server / terrane-admin-server / terrane-gateway / terrane-web / terrane-admin-web /
terrane-postgres / terrane-redis.

> Terrane runs no DB-touching test suite (dev-is-prod, verified by running the app); CI is a build gate only.

## Required CI variables (Protected/Masked)

```
REGISTRY / REGISTRY_NAMESPACE / REGISTRY_USER / REGISTRY_PASSWORD
# deploy only:
KUBECONFIG (File) / KUBE_NAMESPACE / TERRANE_KEK / TERRANE_FORGE_EDGE_URL
# external datastores (the chart defaults to external; PG must have age+vector):
EXTERNAL_DB_HOST / EXTERNAL_DB_PASSWORD / EXTERNAL_REDIS_HOST / EXTERNAL_REDIS_PASSWORD
```

> To make the CI deploy self-contained (bundled PG/Redis, demo) instead, replace the `external*` lines
> in `deploy:helm` with `--set postgres.enabled=true --set postgres.password=… --set redis.enabled=true --set redis.password=…`.

## Usage

1. Push the repo (with `.gitlab-ci.yml`) to GitLab — `build` runs automatically.
2. After verification, **manually run `push:images`**.
3. For K8s, **manually run `deploy:helm`** (uses `terrane-deploy/helm/terrane`).

Registry-login helpers in `Scripts/` (pick by runner type). The CI assumes the repo root contains
`Project-source/` and `Project-design/`; adjust build-context paths in `.gitlab-ci.yml` otherwise.
