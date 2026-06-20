# 系统架构设计：Terrane 个人知识库平台

状态：**v1.1 定稿**（2026-06-13，终审 28 项修订后定稿——用户授权"按照你的理解来"） ｜ 依据：PRD v1.0.3（已定稿） ｜ 上游：`../prd/v1.0-terrane-platform.md`

---

## 1. 目标

**业务目标**（摘自 PRD §2）：
- 开箱即用：`docker compose up` → 首次问答 ≤ 10 分钟；onboarding 四幕剧
- 知识复利：问答回填、30 天生成页/原始源 ≥ 3:1、Lint 周报
- 单机↔集群同一镜像功能等价，数据无损迁移
- MCP 双向：Claude Code/Cursor 实测接入
- 私有化交付完整：三交付物 + 全离线包双档 + 信创

**非功能性需求**：
- 性能：检索 P95 ≤ 2s（CPU 档基线条件见 PRD §11）；双栏 SSE ≤ 2s；图谱 1 万节点 ≥ 30fps
- 可用性：控制面 API ≥ 99.9%；备份 RPO ≤ 1h / RTO ≤ 4h（三位一体一致性快照）
- 安全：R10 提示注入防护分层；vault 凭据；private 库 ACL；审计仅元数据
- 合规：GDPR + PIPL 完整档；许可合规义务（MinerU 标注/FunASR 署名/THIRD-PARTY-NOTICES/红线清单）

---

## 2. 架构总览

### 2.1 系统上下文（C4 L1）

```
                          ┌─────────────────────────────────────────────┐
  P1/P2 用户(浏览器) ───→ │                                             │
  P3 管理员(浏览器) ───→  │                Terrane 系统                  │
  MCP 客户端              │  (单机 compose / 集群 Helm，同一镜像)        │
   (Claude Code/Cursor)─→ │                                             │
  Terrane Clipper ──────→ │                                             │ ──→ 模型上游(六路)：OpenAI 兼容/
  Terrane Sync ─────────→ │                                             │      Anthropic/Gemini/国产/内网 vLLM/
                          └─────────────┬───────────────────────────────┘      离线 llama.cpp(系统内)
                                        │
                 ┌──────────────────────┼──────────────────────────┐
                 ↓                      ↓                          ↓
        连接器外部源                Forge edge                 Web 搜索源
   (Notion/语雀/B站/微信读书/      (License 在线租约,          (Agent 任务,
    RSS/IMAP/WebDAV/S3/           离线 .forge 免联)            域名白名单)
    飞书/企微存档)
```

### 2.2 容器图（C4 L2）

```
浏览器 ──HTTPS──→ [terrane-web  nginx SPA]        [terrane-admin-web  nginx SPA]
                        │ /api/v1 + SSE                  │ /admin-api/v1
                        ↓                                ↓
                 [terrane-api  FastAPI]          [terrane-admin-api  FastAPI]
                  ├── /mcp (MCP Server, ASGI mount, 无状态)
                  ├── /clipper (插件/Sync 摄入端点, API Key)
                  │
                  ├──── 任务入队 ────→ [Redis  队列/缓存/SSE pubsub/限流]
                  │                         ↑↓
                  │                  [terrane-worker  Celery]
                  │                   摄入编译·图构建·嵌入·wiki 投影·
                  │                   记忆四段式·webhook·邮件·git 落盘
                  │                  [terrane-scheduler  Celery beat]
                  │                   定时 Agent·Lint·记忆整理·连接器轮询·
                  │                   预算重置·备份状态
                  │
                  ├──── 模型调用(全部) ──→ [terrane-gateway  Go 数据面]
                  │                          六路收口·协议转换·SSE 转发·
                  │                          failover·用量计量·License 验签②
                  │                              └──→ 上游 / [terrane-inference
                  │                                    llama.cpp×3 + MeloTTS + SenseVoice]
                  │
                  └──→ [terrane-postgres  PG18+AGE+pgvector+zhparser  单库]
                        业务表 + 图(AGE) + 向量(pgvector) + 全文(zhparser)
                       [SeaweedFS  对象存储] 附件/解析资产/产物/备份
                       [git 镜像卷]  Wiki 层 Markdown 物化(每库一仓)
```

**要点**：
- 镜像规划 **8+1**（含 terrane-inference 与自建 terrane-postgres，超越 PRD §6 "七镜像"预估），权威表在 `.agent.md`[镜像规划]
- **同一镜像双拓扑**：compose 单机 = 上述容器各 1 副本同宿主机；Helm 集群 = api/worker/gateway 水平扩，PG/Redis/对象存储走集群版或客户自备——无任何代码分叉（PRD 4.13.1）
- **MCP Server 随 api 镜像**（ASGI mount，无独立端口）；无状态，任意副本可答
- **terrane-inference 仅离线包/有本地推理需求时部署**；网关将"离线引擎"视为一路普通渠道
- 控制面（Python）与数据面（Go）双 License Verifier，fail-closed（多点防绕过）

### 2.3 知识引擎核心数据流

**Ingest（摄入即编译，全异步管线，Celery chain）**：
```
源进入(上传/剪藏/Sync/连接器/对话沉淀/Agent抓取)
 → ① RawSource 落库+对象存储(不可变,版本链)        [api, 同步,含估价+预算闸门]
 → ② 解析路由: MinerU(中文PDF)/Docling(Office)/      [worker, 队列 ingest.parse]
      PP-OCRv5+VLM(图)/FunASR(音视频)/tree-sitter(代码)
 → ③ markdown-aware 分块(+contextual 前缀,GPU档)    [worker]
 → ④ 嵌入(向量档)+zhparser 全文索引                  [worker, 经 gateway]
 → ⑤ LightRAG 实体/关系抽取 → AGE 增量子图           [worker, 经 gateway 低价模型]
 → ⑥ wiki 物化投影: 受影响实体页重渲染→WikiPage      [worker]
      +git commit(镜像卷)
 → ⑦ index 更新 + ActivityLog 追加 + SSE 事件        [worker→Redis pubsub→api SSE]
```
失败语义：任一步失败 → 源停在 Raw 层 + 错误标注 + 可重试；步骤幂等（chunk/实体以内容哈希去重）。CPU 档约束：②与 LLM 推理互斥排队（Redis 信号量），MinerU 子进程用完即杀。

**Query（检索→回答→回填）**：
```
问题 → 档位判断(chunk数≥5万?) → 多路召回:
        [小库档] zhparser词法 + AGE 1-2跳 + 时间线          (并行)
        [向量档] + pgvector HNSW                            (并行)
      → RRF(k=60) → rerank top-20(BGE/Qwen3, 经 gateway)
      → LLM 生成(带引用角标, SSE 流式)
      → [用户/Agent 触发] 回填: 答案→WikiPage 编译(走 Ingest ⑥⑦)
```

**双引擎单真相源（核心创新，R1 PoC ✅ 已通过 2026-06-13，见 ../poc/poc-results.md）**：AGE 图 = 唯一权威源；WikiPage = 物化投影（持久+git 落盘）；图增量变更 → 受影响页重渲染；`[[链接]]` 由边生成；接管编辑段落 → 人工事实标记回写图（冲突人工优先，diff 审计）。**兜底**：回写闭环 PoC 失败 → wiki 页降级缓存渲染（只读投影，编辑仅 frontmatter 批注），单真相源不变。

**记忆四段式（异步，不阻塞对话）**：对话结束事件 → worker 抽取（schema 结构化）→ ADD/UPDATE/DELETE/NOOP 消解 → 写 Memory（per-user）→（用户开启时序层时）AGE 双时态边 + episode 表 → 周期整理（scheduler）→ 面板可见。检索按需工具式 + 近期摘要轻注入。
**"对话结束"判定（D3 收口）**：① 用户显式关闭会话 → api 即发事件；② scheduler 每 15min 扫描 idle>30min 的 active 会话 → 发事件；conversation 状态机 `active→settled` 保证幂等（settled 后新消息重回 active）。
**记忆唤回流（4.6.4 收口）**：摄入管线 ⑦ 后挂钩——新 chunk 嵌入与该库可见用户的记忆向量批量相似度查询（阈值/上限走用户 memory settings）→ 命中暂存 → scheduler 每日 08:00（部署时区）聚合去重 → notifications（类型 memory.recall）。

**摄入估价口径（D4 收口）**：`est_tokens = parsed_bytes/4 × lang_coef(中文1.35) × tier_coef`；tier_coef：小库档=抽取系数 2.5（LightRAG 单轮+gleaning1）；向量档 +0.1（嵌入）；GPU/外接档 +0.4（contextual 前缀）。展示为区间（±40%）；R2 实测后系数表存 settings 可热调，每次摄入完成用实耗回归校准（滑动平均）。

**git 外部变更检测（B3 收口）**：scheduler 每 5min 对开启镜像的库跑 `git status --porcelain`（worker 执行，库级锁内）→ 有外部修改 → 入 `ingest` 队列走"导入合并"任务（外部文件作为新版本源进 Raw，diff 提示走 pages 冲突合并界面）→ 站内通知。

### 2.4 模型网关角色路由

控制面维护 ModelRole 表：`chat`（旗舰）/ `extract`（低价，图抽取）/ `embed` / `rerank` / `transcribe` / `tts` / `vision` / `council-*`（议会成员）。每角色绑定渠道+模型+参数；页面可配；数据面只按快照执行。用量逐请求计量（上游 usage 为准）→ UsageRecord → TokenBudget 闸门。

---

## 3. 关键决策

| # | 决策 | 选择 | 依据/取舍 |
|---|------|------|----------|
| D1 | 服务形态 | **前后台分离双 FastAPI 单体 + Go 网关数据面 + Celery worker/scheduler**，非微服务 | b2b-architecture §1；知识引擎模块间强一致需求（同事务图+向量）；微服务收益不抵运维成本；网关独立是性能/语言边界而非业务拆分 |
| D2 | 存储 | **PG18 + AGE 1.7.0 + pgvector 单库**（版本三元组锁死，自建 terrane-postgres 镜像） | PRD §6.1，用户拍板；LightRAG 官方基线；单事务图+向量+关系+全文；零法务摩擦 |
| D3 | 同步 vs 异步 | 摄入/图构建/嵌入/投影/记忆/Lint/webhook **全异步**（Celery + Redis）；问答同步 SSE；库事件 Redis pubsub → SSE | 摄入管线长耗时；CPU 档互斥约束需要队列做执行权仲裁 |
| D4 | LLM 调用收口 | **一切模型调用过 terrane-gateway**（含嵌入/重排/转写/TTS），控制面零直连上游 | 计量/预算/failover/审计单点；离线引擎与云端渠道同构 |
| D5 | wiki 物化 | 物化投影而非按需渲染 | PRD 4.4.2；git 落盘/Obsidian 直开/页面历史需要持久载体 |
| D6 | 时序记忆 | **自研双时态**（边 t_valid/t_invalid + episode 表）落 AGE，不引 Graphiti 库 | Graphiti 无 AGE driver（v1.0.2 核验）；保单库+许可干净 |
| D7 | MCP | mcp≥1.27 / 2025-11-25 协议 / stateless_http / ASGI mount 进 api | 官方推荐生产形态；集群免粘性路由 |
| D8 | 缓存策略 | Redis db 切分（caching.md）：session / 业务缓存 / 限流 / Celery broker+result / SSE pubsub / 检索缓存(查询哈希,短 TTL) / CPU 档执行权信号量 | 检索缓存仅缓存召回集不缓存生成（引用准确性） |
| D9 | git 落盘 | 每库一个裸仓于镜像卷；worker 串行化单库写（库级 git 锁）；删除同步 commit；DSR history-rewrite | 硬删除一致性（PRD 4.1.5）；并发写 git 不安全故单库串行 |
| D10 | 全文检索 | PG 内建：zhparser（中文主路）+ tsvector + pg_trgm（模糊辅路），不引 ES/OpenSearch | 项目级覆盖（.agent.md）；单库原则 |
| D11 | 桌面触达 | Terrane Sync（Go 单二进制）走摄入 API，不做服务端代理拉取 | 集群/NAS 形态服务端摸不到桌面（PRD 4.9.6）；推模型比拉模型安全边界清晰 |
| D12 | Agent 执行 | Agent 运行于 worker 进程内（LLM 工具循环），工具白名单+vault+出口域名白名单；只写 Wiki 层；**第三方 MCP server 工具经 mcp_server_configs 在任务启动时注入工具箱**（mcp client 会话随 run 生命周期） | R10；不引入独立 Agent 运行时（v1 范围） |
| D13 | Web 搜索 | 后台渠道类型 `web-search`（SearXNG 自托管 / Bing/Brave/博查 API），页面化配置；Agent 经 gateway 调用；无渠道/离线 → 功能置灰 `TRN_OFFLINE_FEATURE_UNAVAILABLE` | B4 收口；搜索也走渠道抽象=可计量可审计 |
| D14 | 抽取角色默认档（PRD §13.10 收口） | `extract` 角色默认绑定渠道中标记 `tier=economy` 的模型（向导引导选择）；离线包默认 Qwen3-4B；`chat`=旗舰、`council-*`=用户显式配置 | 成本控制；R2 校准依赖稳定的抽取档 |

---

## 4. Workspace 多租户隔离方案

- **共享 DB + workspace_id 列**（默认，database.md §5）；SQLAlchemy 四层强制租户过滤
- **库级 ACL 叠加**：KnowledgeBase.visibility（private/shared/workspace）+ KbMember（viewer/editor）；实际权限 = Workspace 角色 ∩ 库级角色（矩阵在 02-database.md §8）
- **private 边界**（PRD 4.1.6）：应用层 ACL——检索/图谱/记忆/Lint 聚合查询全部带库 ACL 过滤；Lint 全局视图对 private 仅计数；审计仅元数据；**不做密码学承诺**——部署指引要求镜像卷与备份加密（密钥部署方持有）
- AGE 图按库分 graph（`kb_<uuid>` 命名空间）天然隔离；向量/全文查询强制 kb_id 过滤
- 集群版资源隔离：per-Workspace 存储/token 配额（tenant-quota 三类型）+ TokenBudget

---

## 5. 安全架构

**信任边界**：
```
[不可信] 浏览器/插件/Sync/MCP 客户端 ──边界1: Session/API Key+scope──→ [api]
[不可信] 外部抓取内容/连接器文档/上传文件 ──边界2: 内容通道──→ 摄入管线
[半可信] Agent 工具循环 ──边界3: 工具白名单+vault+域名白名单──→ 外部
[可信]   worker/scheduler/gateway/PG/Redis ──内网──
```
- **边界 2 = R10 主防线**：外部内容永远作为"数据"进 prompt（标注不可信源），绝不拼接进系统指令；Agent 读到的库内容若源自外部抓取，保留不可信标记传播
- **边界 3**：凭据 vault（Agent 只见占位符，gateway/连接器出口替换注入，仅白名单域名）；写类 MCP 工具默认关；Agent 写库全 diff 审计可回滚
- **加密链**：传输 TLS（交付物 customCA 支持）；静态——L5 字段级加密（连接器凭据/渠道 Key，envelope encryption，主密钥 env 注入）、备份 AES-256、镜像卷加密为部署指引
- **鉴权流**：浏览器 = Session Cookie（HttpOnly/Secure/SameSite）+ CSRF；插件/Sync/MCP = API Key（scope 四档 + per-Key 限速 60 req/min 默认）；后台 = 独立 Session + 2FA 强制（超管）
- **License**：双 Verifier（api/admin-api Python + gateway Go）fail-closed；锁定态中间件在认证之前

---

## 6. 可观测性

- **Metrics**（Prometheus `/metrics`，全容器）：检索延迟直方图（按档位标签）、摄入管线各阶段耗时/失败率、队列深度、gateway 渠道成功率/failover 次数/token 计量、SSE 连接数、git 落盘滞后、预算消耗速率
- **Logs**：structlog JSON；request_id 贯穿 api→worker→gateway；审计独立表
- **Traces**：OTel SDK 全容器；Data Push（后台可配 OTLP exporter，4.12.1）
- **SLI/SLO**：PRD §11 全文承诺 + 报警规则（检索 P95 突破、队列积压 > 阈值、渠道全断、预算 100%、git 落盘滞后 > 5min、备份失败）
- 三探针：`/livez`（进程）`/readyz`（DB+Redis+快照就绪）`/healthz`（聚合）——api/admin-api/gateway/inference 各自实现

---

## 7. 跨平台支持

- 6 组合等级表与 multi-arch 策略见 `.agent.md`[跨平台支持声明]（Tier 1 = linux amd64/arm64 + macOS 开发；Tier 2 = Windows Server Linux 容器）
- **自建 terrane-postgres**：`pgvector/pgvector:pg18-trixie` 基底 + AGE `release/PG18/1.7.0` 源码编译 + zhparser 编译 + `shared_preload_libraries=age`；`docker buildx --platform linux/amd64,linux/arm64`
- **terrane-inference**：llama.cpp 按目标架构编译（amd64 AVX2 基线 + arm64 NEON）；GPU 档 CUDA 变体镜像
- Terrane Sync：Go 交叉编译三平台五目标（win/mac/linux × amd64/arm64，mac 通用二进制可选）
- 信创：openEuler 系基础镜像优先；openGauss/PolarDB-PG 适配器（database provider 层），金仓走 R3 PoC 结论

---

## 8. 风险与取舍

| 风险 | 应对（承接 PRD R1-R17） |
|------|------------------------|
| wiki 投影回写闭环（R1）✅ PoC 通过 | 风险降为低；兜底保留预期不触发；cypher 函数边界约定入查询层封装（poc-results §知识1） |
| PG 单库多负载争用（R12） | 连接池分池（api/worker/检索独立池）；HNSW 构建低峰队列；CPU 档执行权信号量；混合压测验收；集群版预留 PG 读写分离（worker 读副本） |
| AGE VLE 深度遍历性能（R6） | 图查询统一走查询层封装（超时+深度上限 3 跳）；超界用 SQL 邻接表补齐；PoC 基准 |
| 离线 CPU 档体验（R14） | 互斥队列+prompt cache+ctx≤2K+关 thinking 为系统默认而非可选；性能表发布 |
| Celery 任务风暴（大批量摄入） | 队列分级（ingest/graph/memory/agent 独立队列+并发上限）；预算闸门前置 |
| git 仓库膨胀（高频 commit） | 单库串行+批量 commit 合并窗口（5s 防抖）；定期 gc；DSR rewrite 工具化 |
| SSE 跨副本（集群） | Redis pubsub 扇出，任意 api 副本可服务任意订阅（无粘性） |
| 取舍：不做实时协同编辑 | 页级乐观锁+diff 合并够用（编辑是低频接管动作）；CRDT 复杂度不值（v1） |

---

## 历史变更

**[2026-06-13] v1.0 草案**：依据 PRD v1.0.3 产出；D1-D12 关键决策全部可溯源至 PRD 技术决策与两轮核验结论。

**[2026-06-13] v1.1 终审修订定稿**：交叉终审 3 阻塞+14 重要全部修复（MCP client 端点与页面/音频概览表与 UI/admin_readable 写扩权矫正/配额表/队列清单/SSE 枚举/对话结束判定/估价口径/唤回流/外部变更检测/web-search 渠道/伴读章节端点/埋点载体/锁定页轮询/Helm PG 自写模板/NetworkPolicy admin-api 放行等）；建议项已并入。
