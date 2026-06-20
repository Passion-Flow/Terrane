# Terrane 部署 — GitLab CI/CD

用 GitLab 流水线**构建 → (手动)推镜像 → (手动)Helm 部署**。镜像绝不自动推,人工核验后手动触发。

## 流水线阶段

| Stage | 做什么 | 触发 |
|---|---|---|
| `lint` | 后端 ruff(advisory)+ **前端 tsc+vite build**(硬门) | 自动 |
| `build` | buildx 多架构(amd64+arm64)构建 7 个镜像,**不推** | 自动(分支) |
| `push` | 登录仓库 + 多架构推 7 个镜像 | **手动** |
| `deploy` | Helm upgrade --install 到 K8s | **手动** |

7 个镜像:terrane-server / terrane-admin-server / terrane-gateway / terrane-web / terrane-admin-web / terrane-postgres / terrane-redis。

> Terrane 铁律:不跑碰真实库的测试,质量靠跑应用验证;所以 CI 不含 pytest,只做构建门禁。

## 必填 CI 变量(Settings → CI/CD → Variables,Protected/Masked)

```
REGISTRY            crpi-ew8juv9423tvogc4.cn-hongkong.personal.cr.aliyuncs.com
REGISTRY_NAMESPACE  navtra-mirror
REGISTRY_USER       <robot 账号>
REGISTRY_PASSWORD   <masked>
# 仅 deploy 阶段需要:
KUBECONFIG          <File 类型>
KUBE_NAMESPACE      terrane
TERRANE_KEK         <masked, openssl rand -base64 32>
TERRANE_FORGE_EDGE_URL  http://<your-forge-edge>:8081
# 外部数据库/缓存(chart 默认自带 PG/Redis 关闭,走外部):
EXTERNAL_DB_HOST        <你的 PostgreSQL 主机,须含 age+vector 扩展>
EXTERNAL_DB_PASSWORD    <masked>
EXTERNAL_REDIS_HOST     <你的 Redis 主机>
EXTERNAL_REDIS_PASSWORD <masked>
```

> 想让 CI 部署自带 PG/Redis(demo)而非外部:把 deploy:helm 里 external* 行换成
> `--set postgres.enabled=true --set postgres.password=… --set redis.enabled=true --set redis.password=…`。

## 用法

1. 把仓库(含 `.gitlab-ci.yml`,放仓库根或按你的结构调路径)推到 GitLab,`build` 自动跑。
2. 核验通过后,在流水线页**手动点 `push:images`** 推镜像。
3. 需要 K8s 部署时,**手动点 `deploy:helm`**(走 `terrane-deploy/helm/terrane`)。

镜像登录脚本(按 runner 类型选):
- `Scripts/generate-image-repo-secret-docker.sh` — docker runner,`docker login`。
- `Scripts/generate-image-repo-secret-k8s.sh` — k8s 目标,建 `terrane-image-repo-secret` 拉取密钥。

> 路径假设仓库根包含 `Project-source/` 与 `Project-design/`。若目录层级不同,改 `.gitlab-ci.yml` 里的构建上下文路径。
