# Terrane 部署 — Helm(Kubernetes,含信创 K8s)

自带 PostgreSQL18+AGE+pgvector 与 Redis(均在 chart 内,不依赖 bitnami 子 chart,**离线友好**)。
5 个应用组件 + 数据面网关。

## 0. 前置

- 一个 K8s 集群(1.24+),有默认 StorageClass(给 PG/Redis 的 RWO 卷)。
- **若控制面要多副本或跨节点**:License 共享卷需 **ReadWriteMany** 存储类(NFS/CephFS);否则保持单副本(默认)。
- Ingress Controller(默认 nginx)。
- 镜像仓库可达 + 拉取密钥。
- Forge 激活码 + 你自己的模型 key。

## 1. 拉取密钥

```bash
bash Scripts/generate-image-repo-secret.sh <robot用户> '<密码>' terrane https://crpi-xxx.cr.aliyuncs.com
```

## 2. 安装(release 名必须是 `terrane`)

> 前端 nginx 把 `/api` 反代到固定服务名 `terrane-server` / `terrane-admin-server`,所以 **release 必须叫 `terrane`**。

私有化默认:**自带 PG/Redis 关闭(`postgres.enabled=false`/`redis.enabled=false`),用你自己的外部
数据库与缓存**(externalDatabase / externalRedis)。values.yaml 里所有 `#REPLACE_ME#` 必须填掉。

```bash
helm upgrade --install terrane terrane-deploy/helm/terrane -n terrane --create-namespace \
  --set secret.kek=$(openssl rand -base64 32) \
  --set externalDatabase.host=<你的PG主机> --set externalDatabase.password=<PG密码> \
  --set externalRedis.host=<你的Redis主机> --set externalRedis.password=<Redis密码> \
  --set license.forgeEdgeUrl=http://<your-forge-edge>:8081 \
  --set global.domain=terrane.example.com \
  --set global.adminDomain=admin.terrane.example.com
# ⚠ 外部 PostgreSQL 必须提供 age + vector 扩展,并可访问 terrane_main / terrane_admin 两个库。
```

单机快速起(用自带 PG/Redis,非生产):额外加
`--set postgres.enabled=true --set postgres.password=$(openssl rand -base64 24) --set redis.enabled=true --set redis.password=$(openssl rand -base64 24)`。

> KEK 务必单独备份;丢失则既有密文(SMTP/2FA/凭据)永久解不开。

## 3. 等待 + 首启

```bash
kubectl -n terrane get pods -w     # admin-server 自动迁移 + 建超管
```
1. 后台 `https://admin.terrane.example.com` **激活 License**。
2. 超管 `terrane@navtra.ai`(初始密码=邮箱)**首登强制改密** + 向导。
3.「模型渠道」填**你自己的 key**(出厂零渠道)。前台 `https://terrane.example.com` 即用。

## 4. 关键 values

| key | 说明 |
|---|---|
| `secret.kek` | **必填**,字段加密主密钥 |
| `postgres.enabled` | false 用外部 PG(必须有 `age`+`vector` 扩展),填 `externalDatabase.*` |
| `redis.enabled` | false 用外部 Redis,填 `externalRedis.*` |
| `license.accessMode` | 多副本/跨节点设 `ReadWriteMany` + RWX storageClass |
| `global.useTLS` | false=HTTP 试用(cookie 非 Secure);生产 true |
| `global.customCA` | 内网私有 CA(信创)证书信任 |
| `ingress.*` | 前台/后台双域名 + TLS secret |

## 5. 升级 / 卸载

```bash
# 升级:改 values.yaml 里各组件的 image.tag,或逐个 --set:
helm upgrade terrane terrane-deploy/helm/terrane -n terrane --reuse-values \
  --set server.image.tag=v1.0.1 --set adminServer.image.tag=v1.0.1 \
  --set gateway.image.tag=v1.0.1 --set web.image.tag=v1.0.1 \
  --set adminWeb.image.tag=v1.0.1 --set postgres.image.tag=v1.0.1 \
  --set redis.image.tag=v1.0.1
helm uninstall terrane -n terrane     # PVC(pgdata/redis/license)默认保留,按需手动清
```

## 6. 信创 / 离线

- 镜像 `docker save`→内网 `docker load`→推内网 Harbor→把各组件 `image.repository` 指过去(values.yaml 里每个服务一个)。
- 离线 License:`license.forgeEdgeUrl` 留空,后台贴离线 `.forge`。
- 外部信创 PG:必须提供 `age`+`vector`(知识图谱+向量检索强依赖)。
- 多架构镜像已含 arm64,兼容鲲鹏/飞腾。
