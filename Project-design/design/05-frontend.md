# 前端架构设计：Terrane 个人知识库平台

状态：**v1.1 定稿**（2026-06-13，终审 28 项修订后定稿——用户授权"按照你的理解来"） ｜ 依据：PRD 4.11 + taste-skill 体系 + `.agent.md`[浏览器兼容声明]

---

## 1. 技术栈

- React 19 + TypeScript + **Vite 8** SPA ×2（terrane-web 工作台 / terrane-admin-web 后台，独立部署）
- Tailwind v4（**`@tailwindcss/vite` 插件**，OKLCH 三层 token）+ **shadcn/ui（Base UI 底座**，`npx shadcn init --base base-ui`）
- TanStack Query（server state）/ Zustand（少量 client state：双栏布局/编辑器草稿）/ React Router（URL 路径式 i18n）
- 图谱：sigma.js v3 + graphology（前端仅渲染，坐标服务端 NetworkX 预算）
- 编辑器：Markdown 阅读渲染（remark 系+`[[wikilink]]` 插件）+ 接管编辑 CodeMirror 6
- SSE：原生 EventSource 封装（重连+心跳）；Zod 跨层 schema（与 Pydantic 对齐）
- 字体 Geist + 思源黑体（自托管 `font-display:swap`，禁 Google Fonts link）；图标 Phosphor

## 2. 路由结构（`/<lang>/...`，根路径 Accept-Language 302）

```
/<lang>/login | /register | /reset | /locked(License 锁定提示页：轮询 license/status 3s，副描述按 verdict 区分，指引到 admin 激活——激活动作仅 admin-web)
/<lang>/onboarding              # 四幕剧(向导完成后)
/<lang>/kb                      # 库列表(我的/共享/Workspace)
/<lang>/kb/<slug>               # 库工作台(双栏:对话+知识库,默认视图)
/<lang>/kb/<slug>/pages/<page>  # 知识页(阅读/接管编辑/历史/反链)
/<lang>/kb/<slug>/graph         # 图谱宇宙视图
/<lang>/kb/<slug>/sources       # Raw 源/摄入队列/估价/导出任务
/<lang>/kb/<slug>/audio         # 音频概览（脚本预览编辑→生成→产物;TTS 未配置时整页置灰引导,数据源 capabilities）
/<lang>/kb/<slug>/lint          # 体检报告
/<lang>/kb/<slug>/settings      # Schema/共享/git 镜像/检索档位/预算
/<lang>/reader/<source>         # 伴读模式
/<lang>/agents | /agents/<id>/runs/<run>
/<lang>/memory                  # 记忆面板(三类+时间线)
/<lang>/settings/{profile,keys,notifications,connectors,mcp-servers}
/<lang>/admin/...               # admin-web：License/向导/Workspaces/Members/seat/渠道(含 web-search)/model-roles/
                                #   连接器凭据/摄入监控/配额/预算/备份/Webhooks/Data Push/审计/Settings 簇/lint-overview
```

## 3. 状态管理

- Server state 一律 TanStack Query（key 规范 `[kb, id, resource, params]`；SSE 事件到达 → `invalidateQueries` 定向失效——双栏右栏 ≤2s 的实现机制）
- 长流（聊天 token/Agent 步骤流）：SSE 直写本地 reducer，结束后回写 Query 缓存
- 编辑器乐观锁：`If-Match: rev`，409 时弹 diff 合并界面（PRD 4.11.3）

## 4. 关键页面组件树（线框级）

- **库工作台（旗舰视图）**：`<KbWorkbench>` = 左 `<ChatPane>`（消息流/引用角标→右栏定位/回填按钮/议会模式切换）+ 右 `<KnowledgePane>`（Tab：页面树|图谱迷你图|摄入活动流；SSE 高亮新增）+ 顶 `<KbHeader>`（检索框/档位徽标/预算环形指示）
- **图谱**：`<GraphCosmos>`（sigma WebGL 容器 + LOD 控制 + 社区/度数/时间过滤器 + 节点点击→页面抽屉）；检索结果内嵌 `<SubgraphView>`（1-2 跳）
- **知识页**：`<WikiPage>`（frontmatter 卡/正文/推断标注样式/引用悬浮预览/反链面板/历史 diff 视图/接管编辑切换）
- **记忆面板**：`<MemoryBoard>`（三类分栏+时间线+置顶/编辑/硬删确认）
- **Onboarding**：`<FourActs>` 分幕组件，每幕埋点+可跳过
- 后台：对齐 b2b-architecture 模块清单（License 状态卡=粘贴激活弹窗固定高度不抖动，继承 OpenRelay v1.0.4）

## 5. 主题 / Branding（taste-skill 落地）

- **设计规范 = taste-skill v2 + minimalist-skill 主基调**（SKILL.md 在 `terrane-shared/skills/`，出码 Agent 自动遵守）；应用界面旋钮 VARIANCE 3-4 / MOTION 3-4 / DENSITY 5-7
- Token 体系：骨白画布 `#FBFBFA`/暗色对应、off-black `#111`、1px `#EAEAEA` 边框无阴影、哑光粉彩四色对（Notion 标签系）做实体类型/状态色、单强调色一致性锁、圆角 ≤8/12px
- 动效：入场 600ms cubic-bezier(0.16,1,0.3,1)、交错 80ms、只动 transform/opacity、prefers-reduced-motion 全包裹；图谱"知识长出来"动画 = 节点 scale+opacity 入场（MOTION 3 档克制）
- 主题三态（浅/暗/系统）`html.dark` class 驱动；Branding 白标（logo/名称/主色）后台可配
- **Pre-Flight 清单 = 前端 PR 验收红线**（零 em-dash/单强调色锁/禁纯黑白/暗色双测/>5 项列表禁裸 ul/骨架屏匹配布局/CTA 单行）

## 6. 浏览器兼容（项目级覆盖，PRD §13.12）

Chrome/Edge ≥111、Safari ≥16.4、Firefox ≥128、国产 Chromium ≥111 内核；最小宽 1024px；缩放 100/125/150/175/200% 全测；DPR 1x/2x/3x；移动端 v2。

## 7. 性能预算

Lighthouse ≥90；LCP <2.5s / INP <200ms / CLS <0.1；首屏 bundle ≤250KB gz（图谱/编辑器/伴读路由级 code-split 懒加载）；sigma 场景独立 chunk；虚拟列表（TanStack Virtual）用于页面树/源列表/审计表；图谱 1 万节点 ≥30fps（集成显卡参考机）。

## 8. 可访问性

WCAG 2.1 AA：按钮对比 4.5:1 强检、键盘全可达（编辑器/图谱有键盘导航替代径）、SSE 更新 aria-live、焦点管理（弹窗/抽屉）、可访问性声明页（b2b 基线）。

## 9. i18n 实现

zh-CN（fallback）+ en 资源文件；后端回 code 前端翻译；语言切换自定义下拉（母语名标签）；原生控件包装；时区默认 Asia/Shanghai；数字/token 计量 tabular-nums；锁定文案逐字断言进 e2e。

## 10. 浏览器插件与桌面端（同仓独立包）

- `terrane-clipper/`（WebExtension MV3）：Defuddle+Turndown 打包；后台双声明（scripts+service_worker）；侧边栏 side_panel/sidebar_action 适配层；Firefox `browser_specific_settings.gecko.id`；设置页 = 服务器地址+API Key+目标库；离线安装包随发布
- `terrane-sync/`（Go，非前端栈但交互归口本档）：托盘 UI 极简（状态/暂停/打开 Web）

---

## 历史变更
**[2026-06-13] v1.0 草案**：taste-skill 旋钮与 Pre-Flight 落为验收红线；双栏 SSE→Query 失效机制定稿。

**[2026-06-13] v1.1 终审修订定稿**：交叉终审 3 阻塞+14 重要全部修复（MCP client 端点与页面/音频概览表与 UI/admin_readable 写扩权矫正/配额表/队列清单/SSE 枚举/对话结束判定/估价口径/唤回流/外部变更检测/web-search 渠道/伴读章节端点/埋点载体/锁定页轮询/Helm PG 自写模板/NetworkPolicy admin-api 放行等）；建议项已并入。
