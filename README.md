<p align="center">
  <img src="assets/banner.svg?v=2" alt="Terrane — open-source AI knowledge base" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2bb0a6.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/PostgreSQL-18%20·%20AGE%20·%20pgvector-0c5563" alt="PostgreSQL 18 + AGE + pgvector">
  <img src="https://img.shields.io/badge/Runtime-CPU--only%20·%20no%20GPU-23606a" alt="CPU-only">
  <img src="https://img.shields.io/badge/Deploy-Docker%20·%20Helm-2bb0a6" alt="Deploy">
  <a href="https://github.com/Passion-Flow/Terrane/issues"><img src="https://img.shields.io/badge/PRs-welcome-8df3d6.svg" alt="PRs welcome"></a>
  <a href="https://github.com/Passion-Flow/Terrane/stargazers"><img src="https://img.shields.io/github/stars/Passion-Flow/Terrane?style=flat&color=27a6a4" alt="Stars"></a>
</p>

<p align="center">
  <b>Terrane</b> turns your documents into a knowledge base you can <i>reason over</i> — knowledge graph,
  reasoning-grade hybrid retrieval, a NotebookLM-style Studio, a personal Chat assistant and long-term memory.
  <br>It runs entirely on <b>CPU (no GPU)</b>, you bring your own models, and you can plug it into any app.
</p>

<p align="center">
  <b>English</b> · <a href="README-CN.md">简体中文</a>
</p>

---

## ✨ Highlights

- 🧠 **Reasoning-grade retrieval (Retrieval&nbsp;2.0).** Not just vector search — a per-document structural
  tree is navigated by an LLM and fused (via Reciprocal Rank Fusion) with vector + lexical recall, a
  knowledge-graph multi-hop path and a RAPTOR-style semantic tree. A Fast/Deep router keeps everyday
  queries in milliseconds and spends reasoning only when it pays off. Every Deep answer is **traceable to
  the exact `document › section › page`.**
- 🕸️ **Built-in knowledge graph.** Entities and relations are extracted into **Apache AGE** (graph database
  inside PostgreSQL 18) for multi-hop questions that flat retrieval misses.
- 🖼️ **SOTA multimodal parsing.** A 3-tier engine (lexical → vision-language → full-page VL layout) handles
  scanned PDFs, tables, formulas and figures; videos are parsed by scene keyframes; OCR / ASR / TTS included.
- 🧩 **Plug into any app.** Expose any knowledge base as a **Dify-compatible External Knowledge API**, a
  generic REST endpoint, a self-describing **OpenAPI** tool (Coze / GPTs / n8n / FastGPT) or an **MCP server**
  for Claude Code / Cursor.
- 📓 **NotebookLM-style Studio & Wiki.** Compile sources into study guides, FAQs, briefings and audio
  overviews, or a structured, navigable knowledge Wiki.
- 🧬 **Long-term memory.** A personal assistant that remembers facts and preferences across conversations.
- 🔌 **Bring your own models.** Any OpenAI-compatible channel for chat / embedding / rerank / vision /
  ASR / TTS — configured from the admin console, no code changes.
- 🗄️ **Pluggable object storage.** Bundled SeaweedFS out of the box, or any of S3, Azure Blob, Google Cloud
  Storage, Aliyun OSS, Tencent COS, Volcengine TOS, Huawei OBS.
- 🏠 **Self-hosted & air-gapped.** One `docker compose up` brings up the whole stack — PostgreSQL 18 + AGE +
  pgvector and Redis bundled. CPU-only, no data leaves your network.

## 📋 Table of contents

- [Quick start](#-quick-start)
- [Retrieval 2.0](#-retrieval-20)
- [Plug into any app](#-plug-into-any-app)
- [Architecture](#-architecture)
- [Tech stack](#-tech-stack)
- [Deployment](#-deployment)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

## 🚀 Quick start

> Prerequisites: Docker + Docker Compose. No GPU required.

```bash
git clone https://github.com/Passion-Flow/Terrane.git
cd Terrane/terrane-deploy/docker-compose

cp .env.example .env          # set TERRANE_KEK + database/Redis passwords
docker compose up -d          # brings up the full stack, incl. PostgreSQL 18 (AGE + pgvector) & Redis
```

Then open the **admin console**, change the factory super-admin password, run the setup wizard, and add a
**model channel** (your own OpenAI-compatible API key). The front app is then fully usable.

| App | Default URL | Purpose |
|---|---|---|
| Front (user) | `http://localhost:43000` | Knowledge bases, retrieval, Chat, Studio, Memory |
| Admin (operator) | `http://localhost:43002` | Users, model channels, settings, audit |

> The bundled PostgreSQL image ships **Apache AGE + pgvector**; everything runs on CPU.

## 🧠 Retrieval 2.0

Terrane treats retrieval as a first-class engine, not a vector lookup. For each document it builds a
**structural "table-of-contents" tree** (from the vision-language–parsed Markdown), then answers queries by
**fusing up to five recall paths** with Reciprocal Rank Fusion (RRF):

| Path | What it contributes |
|---|---|
| Vector (pgvector / HNSW) | Dense semantic recall |
| Lexical (pg_trgm) | Exact terms, names, identifiers |
| **Tree reasoning** | LLM navigates the document structure to the right section (PageIndex-style) |
| **Graph multi-hop** | Apache AGE expands entities 1–2 hops for cross-document questions |
| RAPTOR semantic tree | Cluster summaries for global / multi-step questions |

A lightweight **Fast / Deep router** sends short keyword lookups down a millisecond hybrid path, and routes
reasoning-heavy or structured queries to the full fusion — with a hard cap on reasoning calls so latency
stays bounded. Deep results carry an explainable **`document › section › page`** citation path.

**Benchmark.** On the standard **BEIR `nfcorpus`** retrieval benchmark (3,633 documents, 323 test queries,
scored with `pytrec_eval`), Terrane's full retrieval reaches **nDCG@10 0.405 / Recall@10 0.196** — above the
dense `bge-m3` baseline of ~0.34. The hybrid recall + cross-encoder reranking measurably beats dense-only
vector search on the same corpus.

## 🧩 Plug into any app

Every knowledge base can be exposed to external applications with a scoped API key:

- **Dify** — *Connect to an external knowledge base* → point it at `/api/v1/external` (Dify-spec `/retrieval`).
- **Coze · GPTs · n8n · FastGPT** — import the self-describing OpenAPI at `/api/v1/external/openapi.json`.
- **Claude Code · Cursor** — add the built-in **MCP** server.
- **Anything else** — a plain REST `POST /api/v1/external/search` with `{ "query": "...", "top_k": 5 }`.

## 🏗 Architecture

```
              ┌──────────────┐        ┌──────────────────┐
  Browser ──▶ │  terrane-web │ ──────▶│   terrane-server  │  Front API (FastAPI)
              │  (React/Vite)│        │  KB · retrieval   │
              └──────────────┘        │  graph · Studio   │
                                      │  memory · MCP     │
  Operator ─▶ terrane-admin-web ────▶ terrane-admin-server │  Admin API
                                      └─────────┬─────────┘
                                                │
   terrane-gateway (Go data plane) ◀────────────┤
                                                ▼
        PostgreSQL 18  ·  Apache AGE  ·  pgvector   |   Redis   |   SeaweedFS / S3 / …
        (relational + graph + vector, one database) | (cache)   | (object storage)
```

| Component | Stack | Role |
|---|---|---|
| `terrane-server` | Python · FastAPI · SQLAlchemy | Knowledge bases, retrieval, graph, Studio, memory, MCP & external API |
| `terrane-admin-server` | Python · FastAPI | Users, model channels, settings, audit |
| `terrane-gateway` | Go | High-throughput data-plane hot path |
| `terrane-web` / `terrane-admin-web` | React 19 · Vite · Tailwind | User & operator consoles (i18n: 简体中文 / English) |
| Datastores | PostgreSQL 18 (AGE + pgvector) · Redis · SeaweedFS | Relational + graph + vector in one DB; cache; object storage |

## 🛠 Tech stack

**Backend** FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · Go (gateway) · Celery
**Data** PostgreSQL 18 · Apache AGE · pgvector (halfvec) · Redis · SeaweedFS
**Frontend** React 19 · Vite · Tailwind CSS · react-i18next
**Models** Any OpenAI-compatible provider for chat / embed / rerank / vision / ASR / TTS

## 📦 Deployment

Pick a path from [`terrane-deploy/`](terrane-deploy/):

| Path | Use when |
|---|---|
| **docker-compose** | Single host / appliance / air-gapped (bundled PostgreSQL + Redis) |
| **Helm** | Kubernetes (external datastores by default) |
| **GitLab CI/CD** | Build multi-arch images → push → Helm deploy |

Images are published for **`linux/amd64` and `linux/arm64`**.

## 🗺 Roadmap

- [x] Reasoning-grade Retrieval 2.0 (tree reasoning + graph multi-hop + RRF fusion)
- [x] External Knowledge API + MCP server + OpenAPI tool
- [x] Multimodal parsing (vision-language layout, video, OCR/ASR/TTS), Studio, Wiki, memory
- [ ] Evaluation harness & retrieval benchmarks
- [ ] More connectors (Notion, web crawl, IMAP)
- [ ] Collaborative annotations

## 🤝 Contributing

Contributions are welcome. Found a bug, hit a rough edge, or have a feature in mind?
**[Open an issue](https://github.com/Passion-Flow/Terrane/issues)** — that is the best way to reach the
maintainers. For code changes, fork the repo, create a feature branch, and open a pull request.

## 📄 License

Terrane is released under the **[MIT License](LICENSE)**. An optional, self-hostable license-gating
mechanism ships disabled by default for organizations that want per-deployment activation.

<p align="center"><sub>Built for teams that want their knowledge to stay theirs.</sub></p>
