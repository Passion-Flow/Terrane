# Terrane

**私有化部署的旗舰级 AI 知识库** —— 知识库、知识图谱、混合检索、个人 Chat 助手、NotebookLM 式 Studio
与长期记忆。**纯 CPU 运行(无需 GPU)**,面向**私有化 / 气隙离线 / 信创**环境交付。

[English](README.md) | 中文

---

## 概述

Terrane 把你的私有文档变成可检索、带图谱、多模态的知识平台。一切都留在你的网络内:文档、向量、
知识图谱、对话与记忆都不出部署环境。双控制面把面向用户的业务平台与运营管理分离;所有模型后端都由你
用**自己的 API key** 配置(产品**出厂零 key**)。

## 功能

- **知识库** —— 通过自研 **Terrane Parse** 引擎摄入 文本 / PDF / Office(docx、xlsx、pptx),支持
  版面、有线/无线表格、公式还原 —— 全程 CPU,无需 GPU。
- **视频/音频理解** —— ffmpeg 抽关键帧+音轨 → 视觉(VL)描述 + 语音(ASR)转录,回灌进知识库。
- **混合检索** —— pgvector 语义检索 + 词法检索 + 重排。
- **知识图谱** —— 基于 Apache AGE 的图谱,支持图谱浏览。
- **个人 Chat 助手** —— 跨知识库自动引用、联网搜索开关(带来源卡片)、多模态附件(文档/图片/视频/
  音频)、持久化对话、记忆唤回。
- **Studio(NotebookLM 式)** —— 一键生成 学习指南、FAQ、简报、时间线、思维导图、记忆闪卡、测验、
  数据表、**幻灯片(PPTX 导出)** 与 **播客音频(双人对话,TTS)**。
- **长期记忆** —— 从你的对话与上传文档**自动记忆**,也可手动添加;去重+更新(抽取→检索→ADD/UPDATE),
  严格按用户隔离。
- **模型渠道** —— 对话 / 嵌入 / 重排 / 多模态 / 语音识别 / 语音合成,均在后台用你自己的 key 配置
  (DashScope / OpenAI 兼容)。
- **MCP 服务** —— 把知识库暴露为 MCP 工具供外部 Agent 调用。
- **企业能力** —— 工作空间与 RBAC、SSO(OIDC)、2FA、字段级加密(KEK)、审计日志、可观测、备份与迁移、
  License 授权激活。

## 架构

5 个应用服务 + 2 个数据存储:

| 组件 | 角色 |
|---|---|
| `terrane-server` | 前台业务控制面(知识库 / 检索 / Chat / Studio / 记忆),`:43001` |
| `terrane-admin-server` | 后台管理控制面(激活 / 向导 / 模型渠道 / 成员),`:43003` |
| `terrane-gateway` | Go 数据面网关 |
| `terrane-web` | 前台 SPA(nginx) |
| `terrane-admin-web` | 后台 SPA(nginx) |
| **PostgreSQL 18 + Apache AGE + pgvector** | 知识图谱 + 向量检索 + 关系数据(必需扩展) |
| **Redis** | 缓存 + 限流 |

同一 PostgreSQL 实例上有两个逻辑库:`terrane_main`(平台)与 `terrane_admin`(运营)。

## 技术栈

- **后端** —— Python 3.13、FastAPI、SQLAlchemy 2(async)、Alembic、asyncpg、Redis、Pydantic v2、
  argon2id、structlog。
- **数据面** —— Go 网关。
- **前端** —— React 19、Vite、Tailwind v4、react-i18next(zh-CN / en)。
- **模型** —— DashScope / OpenAI 兼容(对话、嵌入、重排、多模态、ASR、TTS)。

## 仓库结构

```
Terrane/
├── Project-source/        # 全部服务
│   ├── terrane-server/        # 前台业务 API(FastAPI)
│   ├── terrane-admin-server/  # 后台 API(FastAPI)
│   ├── terrane-gateway/       # 数据面网关(Go)
│   ├── terrane-web/           # 前台 SPA(React)
│   └── terrane-admin-web/     # 后台 SPA(React)
├── terrane-deploy/        # 交付:docker-compose / helm / gitlab / migration
├── terrane-shared/        # 共享规约(数据分类、错误码、webhook)
├── Project-design/        # PRD、设计文档、规格、PoC
└── ops/                   # 运维脚本(多架构构建、备份、信创说明)
```

## 部署

从 [`terrane-deploy/`](terrane-deploy/README.md) 选一种方式:

| 方式 | 适用 |
|---|---|
| **docker-compose** | 单机 / 一体机 / 气隙离线(默认自带 PostgreSQL + Redis) |
| **Helm** | Kubernetes(含信创 K8s,默认对接外部数据存储) |
| **GitLab CI/CD** | 多架构构建镜像 → 手动推送 → 手动 Helm 部署 |

### 单机快速起

```bash
cd terrane-deploy/docker-compose
cp .env.example .env        # 填 TERRANE_KEK + 数据库/Redis 密码
docker compose up -d        # 一把起全栈,含 PG18+AGE+pgvector 与 Redis
```

随后在后台:**激活 License → 修改出厂超管密码 → 走初始化向导 → 配置模型渠道(填你自己的 API key)**,
前台即可全功能使用。

> 自带的 PostgreSQL 镜像内置 Apache AGE + pgvector。纯 CPU,无需 GPU。

## 授权

Terrane 是商业化、私有化部署产品。每个部署用为该部署签发的 License 激活;字段级密文由每部署独立的
KEK 加密。
