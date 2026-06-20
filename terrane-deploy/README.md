# terrane-deploy

Production delivery artifacts for **Terrane** — a private-deployment AI knowledge base
(知识库 / 知识图谱 / Chat 助手 / Studio / 记忆). Built for **私有化 / on-prem / 信创** delivery.
Three independent paths — pick one. Each has bilingual guides.

> **5 app images + 2 datastore images** — `terrane-server` (前台业务 API) · `terrane-admin-server`
> (后台管理 API) · `terrane-gateway` (Go 数据面) · `terrane-web` (前台 SPA) · `terrane-admin-web`
> (后台 SPA) · `terrane-postgres` (PG18 + Apache AGE + pgvector) · `terrane-redis` (Redis 7).
> 全部进同一私有仓库,Multi-arch amd64+arm64, tag `v1.0.0`.

## Pick your path / 选择部署方式

| Artifact | Use when / 适用 | Guides 文档 |
|---|---|---|
| **docker-compose** (`docker-compose/`) | 单机 / 一体机 / 气隙离线 | [README-CN](docker-compose/README-CN.md) · [README-EN](docker-compose/README-EN.md) |
| **Helm** (`helm/`) | Kubernetes(含信创 K8s) | [README-CN](helm/README-CN.md) · [README-EN](helm/README-EN.md) |
| **GitLab CI/CD** (`gitlab/`) | 构建 + (手动)推镜像 + (手动)部署 | [README-CN](gitlab/README-CN.md) · [README-EN](gitlab/README-EN.md) |
| **Migration** (`migration/`) | 备份 / 整机迁移 / 灾备 | [README-CN](migration/README-CN.md) · [README-EN](migration/README-EN.md) |

## Directory layout

```
terrane-deploy/
├── docker-compose/
│   ├── docker-compose.yaml     # x-shared-env 锚 + 5 应用服务 + 自带 PG18-AGE + Redis(单机,默认随栈启动)
│   ├── .env.example            # 每项有注释,#REPLACE_ME# 占位,TERRANE_CA_FILE 私有 CA
│   ├── init/01-databases.sql   # 建双库 terrane_main + terrane_admin
│   ├── Scripts/generate-image-repo-secret.sh
│   └── README-CN.md / README-EN.md
├── helm/
│   ├── terrane/                # chart:values.yaml + templates(server/admin/gateway/web/admin-web/postgres/redis/ingress)
│   ├── Scripts/generate-image-repo-secret.sh
│   └── README-CN.md / README-EN.md
├── gitlab/
│   ├── .gitlab-ci.yml          # lint → build(多架构 6 镜像) → push(手动) → deploy(手动 Helm)
│   ├── Scripts/generate-image-repo-secret-docker.sh / -k8s.sh
│   └── README-CN.md / README-EN.md
└── migration/
    ├── Scripts/backup-terrane.sh / restore-terrane.sh
    └── README-CN.md / README-EN.md
```

## Common conventions / 通用约定

- **零配置出厂** — 出厂**不带任何模型渠道与 API key**;客户首启在后台「模型渠道」填自己的 key。
  数据库迁移里没有任何 seed key,代码里没有硬编码 key。
- **License 强制** — 出厂为锁定态,需 Forge 签发的激活码(在线码或离线 `.forge`)激活;激活凭据 +
  install_id 落共享卷,**重启持久、多组件共享部署身份**(反克隆双锁)。纯密码学校验,无后门。
- **出厂超管首登强制改密** — `terrane@navtra.ai`,初始密码=邮箱;首登强制改密(交付安全)。
- **私有 CA**(`TERRANE_CA_FILE` / `global.customCA`)— 信任自签/私有 CA 的 https 端点(信创内网)。
- **镜像手动发布** — CI 只构建,人工核验后手动触发推送。
- **PG18 + AGE + pgvector 是硬依赖** — 知识图谱(AGE)+ 向量检索(pgvector)。外接 DB 必须提供这两个扩展。
- **数据存储:按部署模式给默认** — **docker-compose(单机)默认自带 PG/Redis**,一把全起、开箱即用;
  **Helm / GitLab(集群·企业)默认走外部 PG/Redis**(`postgres.enabled/redis.enabled=false`,对接你已有的),
  自带库仅作单机/demo(Helm 置 `enabled=true`)。两边都能互换(compose 注释掉自带服务即用外部)。
- **必填项 `#REPLACE_ME#`** — KEK、DB/Redis 密码(及 Helm 的外部主机)出厂均为 `#REPLACE_ME#` 占位,不填不让过(Helm NOTES 会报警)。

## 首启三步(任一部署方式都一样)

1. **激活 License**(后台)→ 2. **超管改密 + 初始化向导** → 3. **配模型渠道(填自己的 key)**。
之后前台全功能(知识库 / 图谱 / Chat / Studio / 记忆)即可用。

---

先打开上表中对应方式的 README-CN / README-EN。Start with the guide for your chosen path above.
