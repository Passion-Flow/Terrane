# API 设计：Terrane 个人知识库平台

状态：**v1.1 定稿**（2026-06-13，终审 28 项修订后定稿——用户授权"按照你的理解来"） ｜ 依据：PRD §8 + 02-database.md ｜ 规范：api-design.md（统一信封/分页/版本/Idempotency-Key）

**通用**：统一响应 `{code, message, details, request_id}`；游标分页；`POST` 变更类支持 `Idempotency-Key`；错误码 `TRN_*`（基础码全局对齐，含 `VALIDATION_FAILED` 信封——继承 OpenRelay 教训，FastAPI RequestValidationError 必须映射）；i18n：后端只回 code。

---

## 1. API 总览

| 面 | 前缀 | 鉴权 | 消费者 |
|----|------|------|--------|
| 前台业务 | `/api/v1/...` | Session Cookie（+CSRF） | terrane-web |
| 摄入/集成 | `/api/v1/clipper/...`、`/api/v1/kb/{id}/sources:push`（唯一写法，嵌套式） | **API Key**（scope） | Clipper / Sync / 第三方 |
| MCP Server | `/mcp` | API Key（scope） | Claude Code / Cursor 等 |
| 后台管理 | `/admin-api/v1/...` | 独立 Session + 2FA | terrane-admin-web |
| 网关内部 | `/v1/...`（gateway，内网） | 内部 service token | api/worker 专用，**不对外** |

## 2. 资源清单（前台 `/api/v1`）

| 资源 | 路径（代表性端点） | 鉴权/scope | 限流 |
|------|--------------------|-----------|------|
| Auth | `auth/{login,logout,register,reset,2fa}` | 公开/Session | 登录限速+锁定 |
| KB | `kb` CRUD；`kb/{id}/schema`（版本链）；`kb/{id}/share`（邀请/角色）；`kb/{id}/export`（全量导出任务）；`kb/{id}:transfer-owner`；删除需 body 带 `confirm_name` | Session×权限矩阵(02 §8) | 默认 |
| Sources | `kb/{id}/sources`（上传 multipart/URL）；`sources/{id}`（GET/DELETE/版本链）；`kb/{id}/sources:estimate`（摄入估价）；`kb/{id}/sources:push`（Sync/插件推送，**API Key ingest_write**） | Session 或 Key | push 按 Key rpm |
| Ingest | `kb/{id}/ingest-jobs`（列表/重试/取消）；`ingest-jobs/{id}`（阶段详情+账单） | Session | — |
| Pages | `kb/{id}/pages`；`pages/{id}`（GET/接管编辑 PUT）；`pages/{id}/revisions`+`:diff`；`pages/{id}/backlinks`；`pages/{id}:takeover` / `:release`（乐观锁 `If-Match: rev`，冲突 409 `TRN_PAGE_EDIT_LOCKED` + diff 载荷） | Session×矩阵 | — |
| Search | `search`（body：query/kb_ids[]/filters；返回融合命中+定位 locator） | Session 或 Key(search_read) | 默认 |
| Chat | `conversations` CRUD；`conversations/{id}/messages`（POST→**SSE 流**：tokens/citations/kb-events）；`messages/{id}:distill`（回填，返回 page 草案→确认落库）；`conversations/{id}:council`（议会模式） | Session | LLM 并发额度 |
| Graph | `kb/{id}/graph/overview`（预布局坐标分页）；`graph/neighborhood?entity=&hops≤3`；`kb/{id}/graph:export` | Session×矩阵 | 深度上限 3 跳 |
| Memory | `memory`（三类列表/编辑/删除/置顶）；`memory/timeline`；`memory/settings`（唤回阈值/上限/开关/时序层） | Session（仅本人） | — |
| Agents | `agent-tasks` CRUD（即时/cron）；`agent-tasks/{id}/runs`；`runs/{id}`（步骤流 SSE）/`:cancel`；`runs/{id}/diff`（写库审计） | Session×矩阵 | 预算闸门前置 |
| Lint | `kb/{id}/lint-reports`；`lint-reports/{id}`；`lint-items/{id}:fix`（diff 预览→确认，lint_items 子表寻址）；`kb/{id}/lint:run` | Session×矩阵 | 预算闸门 |
| Connectors | `connectors`（类型目录/实例 CRUD/`:test`/`:sync-now`/状态页数据） | Session（WS Editor+） | 各源内置限速 |
| Audio | `kb/{id}/audio-overviews`（脚本预览→生成任务→产物下载） | Session | 预算闸门 |
| Keys | `keys` CRUD（明文仅创建响应一次；scope/rpm） | Session | — |
| MCP Servers | `mcp-servers` CRUD + `:test`（第三方 MCP client 配置，页面化；工具注入 Agent 工具箱见 01 D12） | Session（WS Editor+） | — |
| Reader | `sources/{id}/toc`、`sources/{id}/chapters/{n}`（伴读章节结构/正文；伴读会话 = conversations 带 `context.chapter_locator`） | Session×矩阵 | — |
| Activity | `kb/{id}/activity`（log 时间线分页查询） | Session×矩阵 | — |
| Usage | `usage`（明细/按 purpose/kb 聚合报表） | Session | — |
| Capabilities | `capabilities`（只读脱敏：各角色路由可用性/模型数/TTS 配置态——议会入口隐藏与置灰的数据源） | Session | — |
| Track | `events:track`（本地埋点→product_events，永不外发） | Session | 突发桶 |
| License | `license/status`（**锁定态例外路由**，前台锁定页轮询 3s/激活 8s；激活动作仅 admin 面） | 公开（仅状态码） | 轮询限速 |
| Notifications | `notifications`（Bell 列表/已读）；`notifications/stream`（SSE）；`notification-preferences` | Session | — |
| Budget | `budget`（库/WS 级查看；预算设置需 WS Admin） | Session | — |
| Events | `kb/{id}/events`（SSE：页面/图谱/摄入实时事件——双栏右栏数据源，≤2s） | Session | 连接数上限 |

## 3. MCP Server 工具集（`/mcp`，streamable HTTP，2025-11-25 协议）

| 工具 | scope | 说明 |
|------|-------|------|
| `terrane_search` | search_read | 混合检索（kb_ids 限 Key 可见范围），返回命中+引用 locator |
| `terrane_read_page` / `terrane_list_pages` | search_read | wiki 页读取/索引 |
| `terrane_graph_neighborhood` | search_read | 实体邻域（≤3 跳） |
| `terrane_memory_search` / `terrane_memory_write` | memory_rw | 记忆读 / 写（写默认关，需 Key 显式带 scope） |
| `terrane_distill` | ingest_write | 回填：内容→知识页（走 Ingest 规则，diff 审计） |
| `terrane_ingest_url` / `terrane_ingest_text` | ingest_write | 摄入源 |
| `terrane_lint_run` | ingest_write | 触发体检（预算闸门） |

实现：`stateless_http=True, json_response=True`；任意副本可答；工具错误同样走 `TRN_*` 映射进 MCP error。

## 3.5 SSE 事件类型枚举（三通道，Zod/Pydantic 同源 schema）

| 通道 | event type | payload 要点 |
|------|-----------|--------------|
| chat 流 | `token` / `citation` / `tool_step` / `distill_suggest` / `done` / `error` | delta 文本/引用 locator/工具步骤/回填建议 |
| `kb/{id}/events` | `page.created` / `page.updated` / `page.deleted` / `graph.node_added` / `graph.edge_added` / `ingest.stage` / `lint.ready` | 资源 id + rev——前端 invalidateQueries 定向失效映射表随枚举出 |
| `notifications/stream` | `notification.new` | Notification 实体 |

**网关内部鉴权（D5）**：api/worker → gateway 用静态 service token（部署期 Secret 注入 env，轮换 = 改 Secret 滚动重启；不做动态签发，内网 NetworkPolicy 为主防线）。

## 4. 后台管理 API（`/admin-api/v1`）

`workspaces` / `members` / `seats`（用量看板）/ `channels`（六路渠道 + **web-search 渠道类型**【SearXNG 自托管/Bing/Brave/博查 API，Agent Web 搜索数据源，离线无渠道时该功能置灰】CRUD+`:test`——`:test` 经 gateway 真实试探，NetworkPolicy 已放行 admin-api→gateway）/ `model-roles` / `connectors-credentials`（vault 管理）/ `ingest-monitor`（全局队列）/ `quota`（三类型配置）/ `budget` / `backup-status` / `webhooks` / `data-push`（OTel 配置）/ `audit-logs`（查询页数据）/ `settings/*`（System Users/2FA/Login/Password Policy/Data Retention/Branding/Notifications）/ `license`（状态卡/粘贴激活/seat）/ `wizard`（初始化向导状态机）/ `lint-overview`（private 仅计数）。

## 5. 错误码扩展（`terrane-shared/error-codes.yaml`）

`TRN_KB_NOT_FOUND` `TRN_KB_NAME_CONFIRM_MISMATCH`（删库确认）`TRN_INGEST_PARSE_FAILED` `TRN_INGEST_DEGRADED` `TRN_BUDGET_EXHAUSTED`(402 语义) `TRN_QUOTA_EXCEEDED`(429+`TENANT_QUOTA_EXCEEDED` 信封) `TRN_PAGE_EDIT_LOCKED`(409) `TRN_PAGE_REV_CONFLICT`(409+diff) `TRN_GRAPH_QUERY_TIMEOUT` `TRN_GRAPH_DEPTH_EXCEEDED` `TRN_CONNECTOR_AUTH_EXPIRED` `TRN_CONNECTOR_RATE_LIMITED` `TRN_MCP_SCOPE_DENIED` `TRN_NO_AVAILABLE_CHANNEL`(503) `TRN_OFFLINE_FEATURE_UNAVAILABLE` `TRN_MEMORY_NOT_OWNER`(403) `TRN_SOURCE_IMMUTABLE` `TRN_LICENSE_SEAT_EXHAUSTED`（软门控拒新）。

## 6. 鉴权矩阵 / 限流

- 端点 × 角色映射 = 02-database.md §8 权限矩阵直译（OpenAPI `x-required-permission` 注解，代码层装饰器对齐 rbac.md）
- 限流（security.md §8）：登录 5/min+锁定；API Key 默认 60 rpm（Key 可调）；SSE 每用户并发 ≤5；search 30 rpm/用户；LLM 类端点走预算闸门+渠道并发额度；摄入 push 每 Key 突发桶 2×rpm

## 7. Webhook 事件目录

见 `.agent.md`[Webhook 事件目录]（ingest.completed/failed、agent.task_completed/failed、lint.report_ready、memory.recall、budget.threshold/exhausted、quota.storage_full、kb.shared/deleted、license.expiring + 基线事件）。Payload 信封：`{event_id, event_type, occurred_at, workspace_id, data}`，HMAC-SHA256 签名头 + 重试（指数退避 5 次）+ DLQ（webhook.md §7）。

## 8. OpenAPI

`openapi.yaml` 同目录手写 stub（资源/信封/错误码/鉴权 scheme），开发期由 FastAPI 自动生成并与 stub 做 CI diff 校验；Admin APIs 含 Postman Collection 导出（b2b 基线）。

---

## 历史变更
**[2026-06-13] v1.0 草案**：覆盖 PRD §8 全部 API 面 + MCP 工具集 + 乐观锁/确认删除/预算闸门等边界语义。

**[2026-06-13] v1.1 终审修订定稿**：交叉终审 3 阻塞+14 重要全部修复（MCP client 端点与页面/音频概览表与 UI/admin_readable 写扩权矫正/配额表/队列清单/SSE 枚举/对话结束判定/估价口径/唤回流/外部变更检测/web-search 渠道/伴读章节端点/埋点载体/锁定页轮询/Helm PG 自写模板/NetworkPolicy admin-api 放行等）；建议项已并入。
