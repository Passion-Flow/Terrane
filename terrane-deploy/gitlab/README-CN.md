# Terrane deploy — GitLab CI/CD

Use a GitLab pipeline to **build → (manually) push images → (manually) deploy via Helm**. Images are never
pushed automatically — pushing is triggered manually after human review.

## Pipeline stages

| Stage | What it does | Trigger |
|---|---|---|
| `lint` | backend ruff (advisory) + **front-end tsc+vite build** (hard gate) | automatic |
| `build` | buildx multi-arch (amd64+arm64) build of 7 images, **no push** | automatic (on branch) |
| `push` | log in to the registry + multi-arch push of the 7 images | **manual** |
| `deploy` | Helm upgrade --install to K8s | **manual** |

7 images: terrane-server / terrane-admin-server / terrane-gateway / terrane-web / terrane-admin-web / terrane-postgres / terrane-redis.

> Terrane rule: no tests that hit a real database — quality is validated by running the app; so CI contains no
> pytest, only build gates.

## Required CI variables (Settings → CI/CD → Variables, Protected/Masked)

```
REGISTRY            crpi-ew8juv9423tvogc4.cn-hongkong.personal.cr.aliyuncs.com
REGISTRY_NAMESPACE  navtra-mirror
REGISTRY_USER       <robot account>
REGISTRY_PASSWORD   <masked>
# Needed only for the deploy stage:
KUBECONFIG          <File type>
KUBE_NAMESPACE      terrane
TERRANE_KEK         <masked, openssl rand -base64 32>
TERRANE_FORGE_EDGE_URL  http://<your-forge-edge>:8081
# External database/cache (the chart defaults to bundled PG/Redis OFF, using external ones):
EXTERNAL_DB_HOST        <your PostgreSQL host, must include the age+vector extensions>
EXTERNAL_DB_PASSWORD    <masked>
EXTERNAL_REDIS_HOST     <your Redis host>
EXTERNAL_REDIS_PASSWORD <masked>
```

> To have CI deploy the bundled PG/Redis (demo) instead of external ones: in deploy:helm, replace the
> external* lines with
> `--set postgres.enabled=true --set postgres.password=… --set redis.enabled=true --set redis.password=…`.

## Usage

1. Push the repo (incl. `.gitlab-ci.yml`, at the repo root or with the path adjusted to your structure) to
   GitLab; `build` runs automatically.
2. After review passes, **manually click `push:images`** on the pipeline page to push the images.
3. When you need a K8s deployment, **manually click `deploy:helm`** (uses `terrane-deploy/helm/terrane`).

Image login scripts (choose by runner type):
- `Scripts/generate-image-repo-secret-docker.sh` — docker runner, `docker login`.
- `Scripts/generate-image-repo-secret-k8s.sh` — k8s target, creates the `terrane-image-repo-secret` pull secret.

> Path assumption: the repo root contains `Project-source/` and `Project-design/`. If your directory layout
> differs, adjust the build-context paths in `.gitlab-ci.yml`.
