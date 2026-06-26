<p align="center">
  <img src="assets/banner.svg?v=2" alt="Terrane — 开源 AI 知识库" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2bb0a6.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/PostgreSQL-18%20·%20AGE%20·%20pgvector-0c5563" alt="PostgreSQL 18 + AGE + pgvector">
  <img src="https://img.shields.io/badge/运行-纯%20CPU%20·%20无需%20GPU-23606a" alt="纯 CPU">
  <img src="https://img.shields.io/badge/部署-Docker%20·%20Helm-2bb0a6" alt="部署">
  <a href="https://github.com/Passion-Flow/Terrane/issues"><img src="https://img.shields.io/badge/PRs-welcome-8df3d6.svg" alt="欢迎 PR"></a>
  <a href="https://github.com/Passion-Flow/Terrane/stargazers"><img src="https://img.shields.io/github/stars/Passion-Flow/Terrane?style=flat&color=27a6a4" alt="Stars"></a>
</p>

<p align="center">
  <b>Terrane</b> 把你的文档变成一个<i>可推理</i>的知识库 —— 知识图谱、推理级混合检索、NotebookLM 式 Studio、
  个人 Chat 助手与长期记忆。
  <br>它<b>纯 CPU 运行(无需 GPU)</b>,模型自带,并能接入任意应用。
</p>

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b>
</p>

---

## ✨ 亮点

- 🧠 **推理级检索(Retrieval&nbsp;2.0)。** 不止是向量搜索 —— 为每篇文档构建结构树,由 LLM 推理式导航,并通过
  **倒数排名融合(RRF)** 与向量召回、词法召回、**知识图谱多跳**、RAPTOR 语义树融合。**快/深分级路由**让日常查询
  停在毫秒级,只在值得时才动用推理。每条深度答案都可追溯到精确的 **`文档 › 章节 › 页码`**。
- 🕸️ **内置知识图谱。** 实体与关系抽取进 **Apache AGE**(PostgreSQL 18 内的图数据库),回答扁平检索答不了的多跳问题。
- 🖼️ **SOTA 多模态解析。** 三档引擎(词法 → 视觉语言 → 整页 VL 版面)处理扫描件、表格、公式、图表;视频按场景关键帧解析;内置 OCR / ASR / TTS。
- 🧩 **接入任意应用。** 把任一知识库暴露为 **Dify 兼容的外部知识库 API**、通用 REST 端点、自描述 **OpenAPI** 工具
  (Coze / GPTs / n8n / FastGPT),或给 Claude Code / Cursor 用的 **MCP Server**。
- 📓 **NotebookLM 式 Studio 与 Wiki。** 把资料编译成学习指南、FAQ、简报与音频概览,或一篇结构化、可导航的知识 Wiki。
- 🧬 **长期记忆。** 跨对话记住事实与偏好的个人助手。
- 🔌 **模型自带。** chat / embedding / rerank / 视觉 / ASR / TTS 全用任意 OpenAI 兼容渠道,后台配置,零改代码。
- 🗄️ **可插拔对象存储。** 开箱自带 SeaweedFS,或任选 S3、Azure Blob、Google Cloud Storage、阿里云 OSS、腾讯云 COS、火山引擎 TOS、华为云 OBS。
- 🏠 **私有部署 / 气隙离线。** 一条 `docker compose up` 拉起整套栈 —— 自带 PostgreSQL 18 + AGE + pgvector 与 Redis,纯 CPU,数据不出网。

## 📋 目录

- [快速开始](#-快速开始)
- [Retrieval 2.0](#-retrieval-20)
- [接入任意应用](#-接入任意应用)
- [架构](#-架构)
- [技术栈](#-技术栈)
- [部署](#-部署)
- [路线图](#-路线图)
- [贡献](#-贡献)
- [许可证](#-许可证)

## 🚀 快速开始

> 前置:Docker + Docker Compose。无需 GPU。

```bash
git clone https://github.com/Passion-Flow/Terrane.git
cd Terrane/terrane-deploy/docker-compose

cp .env.example .env          # 设置 TERRANE_KEK + 数据库/Redis 密码
docker compose up -d          # 拉起整套栈,含 PostgreSQL 18(AGE + pgvector)与 Redis
```

随后进入**管理后台**,修改出厂超管密码、运行初始化向导,并添加一个**模型渠道**(你自己的 OpenAI 兼容 API Key),前台即可完整使用。

| 应用 | 默认地址 | 用途 |
|---|---|---|
| 前台(用户) | `http://localhost:43000` | 知识库、检索、Chat、Studio、记忆 |
| 后台(运营) | `http://localhost:43002` | 用户、模型渠道、设置、审计 |

> 自带的 PostgreSQL 镜像内置 **Apache AGE + pgvector**;全程纯 CPU 运行。

## 🧠 Retrieval 2.0

Terrane 把检索当作一等引擎,而非一次向量查找。它为每篇文档构建**结构「目录」树**(源自视觉语言解析出的 Markdown),
再用**倒数排名融合(RRF)** 融合多达五路召回来回答问题:

| 召回路 | 贡献 |
|---|---|
| 向量(pgvector / HNSW) | 稠密语义召回 |
| 词法(pg_trgm) | 精确术语、人名、标识符 |
| **树推理** | LLM 沿文档结构导航到正确章节(PageIndex 式) |
| **图谱多跳** | Apache AGE 沿实体扩展 1–2 跳,解跨文档问题 |
| RAPTOR 语义树 | 簇摘要,解全局 / 多步问题 |

轻量的**快 / 深分级路由**把短关键词查询送往毫秒级混合路径,把推理密集或结构化查询交给完整融合 —— 并对推理调用设硬上限,延迟可控。
深度结果带可解释的 **`文档 › 章节 › 页码`** 引用路径。

**基准。** 在标准检索基准 **BEIR `nfcorpus`**(3,633 篇文档、323 条测试查询,用 `pytrec_eval` 评分)上,Terrane 完整检索达到
**nDCG@10 0.405 / Recall@10 0.196** —— 高于稠密 `bge-m3` 基线 ~0.34。在同一语料上,混合召回 + 交叉编码器重排明显优于纯稠密向量检索。

## 🧩 接入任意应用

每个知识库都能用范围化 API Key 暴露给外部应用:

- **Dify** —— 「连接外部知识库」→ 指向 `/api/v1/external`(Dify 规范 `/retrieval`)。
- **Coze · GPTs · n8n · FastGPT** —— 导入自描述 OpenAPI:`/api/v1/external/openapi.json`。
- **Claude Code · Cursor** —— 添加内置 **MCP** Server。
- **其它任意** —— 直连 REST `POST /api/v1/external/search`,请求 `{ "query": "...", "top_k": 5 }`。

## 🏗 架构

```
              ┌──────────────┐        ┌──────────────────┐
   浏览器 ──▶ │  terrane-web │ ──────▶│   terrane-server  │  前台 API(FastAPI)
              │  (React/Vite)│        │  知识库 · 检索    │
              └──────────────┘        │  图谱 · Studio    │
                                      │  记忆 · MCP       │
   运营 ────▶ terrane-admin-web ────▶ terrane-admin-server │  后台 API
                                      └─────────┬─────────┘
                                                │
   terrane-gateway(Go 数据面) ◀────────────────┤
                                                ▼
        PostgreSQL 18  ·  Apache AGE  ·  pgvector   |   Redis   |   SeaweedFS / S3 / …
        (关系 + 图 + 向量,同一个数据库)            | (缓存)    | (对象存储)
```

| 组件 | 技术 | 角色 |
|---|---|---|
| `terrane-server` | Python · FastAPI · SQLAlchemy | 知识库、检索、图谱、Studio、记忆、MCP 与外部 API |
| `terrane-admin-server` | Python · FastAPI | 用户、模型渠道、设置、审计 |
| `terrane-gateway` | Go | 高吞吐数据面热路径 |
| `terrane-web` / `terrane-admin-web` | React 19 · Vite · Tailwind | 用户 / 运营控制台(i18n:简体中文 / English) |
| 存储 | PostgreSQL 18(AGE + pgvector)· Redis · SeaweedFS | 关系 + 图 + 向量同库;缓存;对象存储 |

## 🛠 技术栈

**后端** FastAPI · SQLAlchemy 2(异步)· Alembic · Pydantic v2 · Go(网关)· Celery
**数据** PostgreSQL 18 · Apache AGE · pgvector(halfvec)· Redis · SeaweedFS
**前端** React 19 · Vite · Tailwind CSS · react-i18next
**模型** chat / embed / rerank / 视觉 / ASR / TTS 任选 OpenAI 兼容厂商

## 📦 部署

从 [`terrane-deploy/`](terrane-deploy/) 选一条路径:

| 路径 | 适用 |
|---|---|
| **docker-compose** | 单机 / 一体机 / 气隙离线(自带 PostgreSQL + Redis) |
| **Helm** | Kubernetes(默认外接数据存储) |
| **GitLab CI/CD** | 构建多架构镜像 → 推送 → Helm 部署 |

镜像提供 **`linux/amd64` 与 `linux/arm64`** 双架构。

## 🗺 路线图

- [x] 推理级 Retrieval 2.0(树推理 + 图谱多跳 + RRF 融合)
- [x] 外部知识库 API + MCP Server + OpenAPI 工具
- [x] 多模态解析(视觉语言版面、视频、OCR/ASR/TTS)、Studio、Wiki、记忆
- [ ] 评测装置与检索基准
- [ ] 更多连接器(Notion、网页抓取、IMAP)
- [ ] 协作批注

## 🤝 贡献

欢迎贡献。发现 Bug、用着别扭、或有功能想法?
**[提一个 Issue](https://github.com/Passion-Flow/Terrane/issues)** —— 这是联系维护者最好的方式。
代码改动请 fork 仓库、新建特性分支并发起 Pull Request。

## 📄 许可证

Terrane 以 **[MIT 许可证](LICENSE)** 发布。另附一套可选、可自托管的许可证门控机制,默认关闭,供需要按部署激活的组织使用。

<p align="center"><sub>为「让知识留在自己手里」的团队而造。</sub></p>
