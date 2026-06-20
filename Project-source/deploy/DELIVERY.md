# Terrane 交付指南（单机 docker-compose）

集群版见 `helm/`。同一镜像,双规格。

## 一、出厂启动

```bash
cd deploy
cp .env.example .env        # 改强密码:POSTGRES_PASSWORD / REDIS_PASSWORD / TERRANE_KEK(32+随机)
                            # HTTPS 部署设 SESSION_COOKIE_SECURE=true;HTTP 测试设 false
docker compose up -d --build
```

起来后 6 个容器:postgres / redis / terrane-server(前台 API)/ terrane-admin-server(后台 API)/
terrane-web(前台 :8080)/ terrane-admin-web(后台 :8081)/ terrane-gateway(数据面)。

- 出厂**自动建超管**:`terrane@navtra.ai` / 初始密码=邮箱,**首登强制改密**。
- 出厂为 **License 锁定态**:前台仅 livez/branding 可达,业务全 403,直到激活。

## 二、首启三步(后台 :8081)

1. **激活 License** —— 后台激活页输入厂方签发的激活码(在线码或离线 .forge);
   激活凭据 + install_id 落 `license` 共享卷,**重启持久、三组件共享部署身份**(反克隆双锁)。
2. **首登改密 + 初始化向导** —— 超管首登强制改密;向导走 License→超管→邮件→Branding。
3. **配置模型渠道** —— 后台「模型渠道」新建 chat/embed/rerank/vl/asr/tts 渠道,
   **填客户自己的 API key**(出厂不带任何 key,零配置、零泄露)。配好后前台全功能可用。

## 三、依赖说明（镜像已内置）

- terrane-server 镜像含 **ffmpeg**(视频解析抽帧/抽音轨)、PyMuPDF/python-docx/openpyxl/**python-pptx**(解析+幻灯导出)、httpx(所有模型调用)。
- postgres 为自带 **PG18 + AGE + pgvector** 镜像(知识图谱 + 向量检索)。
- 纯 CPU,无 GPU 依赖。

## 四、升级 / 备份

- 升级:`docker compose pull && docker compose up -d`(数据卷 pgdata/redisdata/license 保留)。
- 备份:`docker compose exec postgres pg_dump ...` + 卷快照。
