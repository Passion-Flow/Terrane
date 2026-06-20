# Service 集成设计：Terrane 个人知识库平台

状态：**v1.1 定稿**（2026-06-13，终审 28 项修订后定稿——用户授权"按照你的理解来"） ｜ 依据：`.agent.md`[Service 使用情况] + 02-database.md ｜ 对齐：`../../../Project-Docs/03-Services/overview.md`

---

## 1. 5 大分类选型

| 分类 | 启用 | 默认 Provider | 必出 Provider | 备注 |
|------|------|--------------|--------------|------|
| Object Storage | ✅ | `local`（自托管默认 SeaweedFS） | 通用 boto3 S3 兼容（s3+aliyun-oss/tencent-cos/huawei-obs/volcengine-tos/baidu-bos/jd/ks3/us3+SeaweedFS/Garage/Ceph/MinIO 遗留）+ azure-blob + google-storage + local 双模（8） | 附件/解析资产/音频产物/导出包/备份 |
| Database | ✅ | `postgres`（自建 terrane-postgres：PG18+AGE+pgvector+zhparser） | **项目级覆盖：PG 引擎家族**——postgres / opengauss（官方 AGE 插件，`enable_thread_pool=off`）/ polardb-pg（polar_age 兼容差异验证）/ kingbase（R3 PoC：图存储 provider 替换路径） | 非 PG 方言不适用（.agent.md §覆盖2） |
| Vector DB / Search | ❌（**项目级覆盖**） | — | —（pgvector+tsvector/zhparser/pg_trgm PG 内建承担；`services/vector-db/` 不创建） | 架构根基，不可适配器化 |
| Cache | ✅ | `redis` | redis + valkey | db 切分见 §2 |
| Email | ✅ | `smtp`（开发期 Mailpit） | smtp / aws_ses / sendgrid / aliyun_dm / tencent_ses / volcengine_dm（6） | 认证/通知/告警/共享邀请 |

## 2. 各 Service 用法

**Object Storage**（file-upload.md）：bucket `terrane-{sources,assets,artifacts,exports,backups}`；上传走签名 URL + 病毒扫描钩子 + 类型/大小白名单；解析产物（Markdown/图片本地化）写 assets；音频概览/导出包写 artifacts（保留策略可配）；**git 镜像卷不是对象存储**（本地卷/PVC，备份纳入三位一体快照）。

**Database**：见 02-database.md。AGE/pgvector/zhparser 扩展由 terrane-postgres 镜像出厂自带（页面化零配置铁律——客户不装扩展）；信创 provider 的扩展差异在适配器层吸收：`graph_store` 接口（AGE 实现 / polar_age 实现 / 金仓替换实现【R3 PoC 决定：SQL 邻接表方案】）+ `fulltext` 接口（zhparser / 信创库对应分词）。

**Cache（Redis db 切分，caching.md）**：
| db | 用途 |
|----|------|
| 0 | Session |
| 1 | 业务缓存（渠道快照/能力标签/Schema 缓存，TTL+主动失效） |
| 2 | 限流（Key rpm/登录锁定/SSE 连接计数） |
| 3 | Celery broker ｜ 4 | Celery result |
| 5 | SSE pubsub（库事件扇出，集群任意副本可服务） |
| 6 | 检索缓存（查询哈希→召回集，TTL 5min，写库事件主动清 kb 维度） |
| 7 | CPU 档执行权信号量（解析×推理互斥）+ 分布式锁（库级 git 锁/owner 转移锁） |

**Email**（email-service.md）：认证三件套/共享邀请/预算与配额告警/License 过期提醒（30/7 天）/Lint 周报摘要（可选订阅）；SPF/DKIM/DMARC 指引进部署文档。

**模型上游（非五大分类，项目特有）**：一切经 terrane-gateway 六路收口（OpenAI 兼容/Anthropic/Gemini/国产/内网 vLLM/Ollama/离线 llama.cpp）；渠道凭据 [L5-ENC] + vault 占位符；角色路由表（chat/extract/embed/rerank/transcribe/tts/vision/council）。

**Web 搜索渠道（D13）**：渠道类型 `web-search`——SearXNG（自托管，离线内网亦可选部署）/ Bing / Brave / 博查 API；Agent 经 gateway 统一调用计量；适配器在 gateway 侧（协议族之一）。

**连接器源（项目特有，三梯队）**：适配器目录 `terrane-server/app/connectors/<type>/`；统一接口 `pull()/push_webhook()/test()/sync_state`；凭据走 vault；限速内置（坚果云 600 次/30min、Notion 3 rps、语雀 5000/h）；微信导入器 = 纯文件格式解析器（无凭据无网络）。**企微会话存档连接器（PIPL 三件套交付物）**：①员工告知文案模板（文档+后台可下载）②采集范围最小化默认配置（仅指定部门/会话类型，显式扩大需二次确认）③同步行为完整审计（audit_logs 事件）。

## 2.5 Celery 队列清单（D1 收口，worker 分组与 KEDA 扩缩依据）

| 队列 | 任务 | 并发上限（CPU 档/集群档） | 优先级 |
|------|------|--------------------------|--------|
| `ingest` | 解析路由/分块/导入合并（git 外部变更） | 1（与推理互斥信号量）/ 4 | 高 |
| `embed` | 嵌入批处理 + HNSW 低峰构建 | 1 / 4 | 中（低峰窗口加权） |
| `graph` | LightRAG 抽取/子图重算/wiki 投影渲染 | 1 / 4 | 中 |
| `memory` | 记忆四段式/唤回相似度批查/整理 | 1 / 2 | 低 |
| `agent` | 任务型+定时 Agent 工具循环 | 1 / 2 | 中 |
| `media` | 音频概览 TTS/转写长任务 | 1 / 2 | 低 |
| `io` | webhook 投递/邮件/git 落盘批 commit/导出打包/对象存储转存 | 4 / 8 | 高 |
| `beat`（scheduler） | 定时 Agent 触发/Lint cron/整理/连接器轮询/预算重置/备份状态/git 扫描/会话 idle 扫描 | 单活 | — |

CPU 档：`ingest/embed/graph/agent/media` 共享"推理互斥"Redis 信号量（解析×LLM 不并行）；集群档 worker 按 {ingest+embed+graph} / {memory+agent+media} / {io} 三组 Deployment（06 §5）。

## 3. 适配器实现位置

```
terrane-server/app/adapters/
  object_storage/{s3_compat,azure_blob,google_storage,local}/
  database/{postgres,opengauss,polardb_pg,kingbase}/   # 含 graph_store/fulltext 子接口
  cache/{redis,valkey}/
  email/{smtp,aws_ses,sendgrid,aliyun_dm,tencent_ses,volcengine_dm}/
terrane-admin-server/app/adapters/   # 独立拷贝（项目内双 server 也不共享 import，各自一份）
```

## 4. 凭证管理

- 开箱默认见 `.agent.md`[Service 凭证]（客户必须改，初始化向导提示）；env 注入，compose/GitLab/Helm 三交付物字段名一一对应
- 业务凭据（连接器/渠道）≠ 基础设施凭据：前者 DB 内 [L5-ENC]+vault，后者 env/Secret（K8s Sealed Secrets/ESO 指引）

## 5. Service 故障降级矩阵

见 `.agent.md`[弹性/降级矩阵]（DB 只读/Redis 拒新+检索直查/对象存储重试队列/Email 暂存/渠道 failover/llama.cpp 自动重启/git 卷重试告警/Forge 宽限/MinerU OOM 降级）——resilience.md §5 落地，开发期每条配混沌测试用例。

---

## 历史变更
**[2026-06-13] v1.0 草案**：两处项目级覆盖落地为适配器目录决策；graph_store/fulltext 子接口为信创差异吸收层。

**[2026-06-13] v1.1 终审修订定稿**：交叉终审 3 阻塞+14 重要全部修复（MCP client 端点与页面/音频概览表与 UI/admin_readable 写扩权矫正/配额表/队列清单/SSE 枚举/对话结束判定/估价口径/唤回流/外部变更检测/web-search 渠道/伴读章节端点/埋点载体/锁定页轮询/Helm PG 自写模板/NetworkPolicy admin-api 放行等）；建议项已并入。
