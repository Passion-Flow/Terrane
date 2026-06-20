# Terrane 部署 — docker-compose(单机 / 私有化 / 离线)

适用:单台 Linux 服务器、一体机、内网气隙环境。一条命令拉起全栈(含自带 PG18+AGE+pgvector 与 Redis)。

## 0. 前置

- 一台 Linux(2C4G 起,推荐 4C8G;**纯 CPU,无需 GPU**),装好 Docker + Docker Compose 插件。
- 能访问镜像仓库(阿里云 ACR / 内网 Harbor),或已离线导入镜像 tar。
- 你自己的模型 API key(出厂不带,首启在后台填)。
- 一张 Forge 签发的 License 激活码(在线码或离线 `.forge`)。

## 1. 配置

```bash
cd terrane-deploy/docker-compose
cp .env.example .env
# 编辑 .env,逐个填掉 #REPLACE_ME#:
#   TERRANE_KEK          openssl rand -base64 32   ← 务必备份,丢了既有密文解不开
#   DATABASE_PASSWORD    强随机
#   CACHE_PASSWORD       强随机
#   TERRANE_FORGE_EDGE_URL  你的 Forge 发证 edge(离线激活可留空)
#   SESSION_COOKIE_SECURE   HTTPS 部署设 true(HTTP 试用保持 false)
```

> 私有仓库需先登录:`bash Scripts/generate-image-repo-secret.sh <registry> <user> <pass>`

## 2. 启动(自带库,一把全起)

docker-compose 是单机一体机:**自带 PG18+AGE+pgvector 与 Redis,默认随栈启动**,无需外接。

```bash
docker compose pull        # 用仓库镜像;若现场构建则 docker compose up -d --build
docker compose up -d
docker compose ps          # 等 7 个容器 healthy
```

起来的容器:`postgres`(PG18+AGE+pgvector)/ `redis` / `terrane-server`(前台 API)/
`terrane-admin-server`(后台 API,自动跑迁移+建超管)/ `terrane-gateway` / `terrane-web`(前台)/
`terrane-admin-web`(后台)。

> 想对接**已有的外部 PG/Redis**(而非自带):在 `.env` 把 `DATABASE_HOST`/`CACHE_HOST` 指过去
> (PG 须含 `age`+`vector` 扩展),并把 `docker-compose.yaml` 里的 `postgres`/`redis` 服务注释掉。
> (集群/企业级走 Helm,默认就是外部库 —— 见 `../helm/`。)

## 3. 首次开机三步(后台 `http://<host>:8081`)

1. **激活 License** —— 输入 Forge 发的激活码。激活凭据 + install_id 落共享 `license` 卷,**重启持久、三组件共享部署身份**(反克隆双锁)。
2. **超管登录 + 改密** —— 出厂账号 `terrane@navtra.ai`,初始密码=邮箱,**首登强制改密**;随后走初始化向导(邮件 / 品牌)。
3. **配模型渠道** —— 后台「模型渠道」新建 chat / embed / rerank / vl / asr / tts,**填你自己的 API key**(出厂零渠道、零 key)。配完前台全功能(知识库 / 图谱 / Chat / Studio / 记忆)即可用。

前台访问:`http://<host>:80`。

## 4. HTTPS(生产必做)

前面挂一层 Nginx / Caddy 反代,把 80 / 8081 收到 443 并配证书,然后 `.env` 设 `SESSION_COOKIE_SECURE=true`(否则 HTTPS 下浏览器丢 cookie,登录态保不住)。内网私有 CA 证书:把 CA bundle 路径填 `TERRANE_CA_FILE`。

## 5. 运维

- **日志**:`docker compose logs -f terrane-server`
- **升级**:`docker compose pull && docker compose up -d`(pgdata / license 卷保留)
- **备份 / 迁移**:见 `../migration/README-CN.md`(`backup-terrane.sh` / `restore-terrane.sh`)
- ⚠ `license` 卷别丢 —— 丢了要重新激活;`TERRANE_KEK` 跟数据一起备份。

## 6. 离线 / 信创

- 离线:在有网机器 `docker save` 6 个镜像 → 拷进内网 `docker load` → `docker compose up -d`;License 用离线 `.forge` 激活(edge URL 留空)。
- 外接信创 PG:必须提供 `age` + `vector` 扩展(知识图谱与向量检索强依赖),把 `DATABASE_*` 指过去并注释掉自带 `postgres` 服务。
