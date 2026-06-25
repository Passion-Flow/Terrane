# Terrane

**A flagship, private-deployment AI knowledge base** — knowledge bases, a knowledge graph, hybrid
retrieval, a personal Chat assistant, a NotebookLM-style Studio, and long-term memory. Runs fully on
**CPU (no GPU)**, ships for **on-prem / air-gapped / Xinchuang (domestic secure-controllable)** environments.

English | [中文](README-CN.md)

---

## Overview

Terrane turns your private documents into a queryable, graph-aware, multi-modal knowledge platform.
Everything stays inside your network: documents, embeddings, the knowledge graph, conversations and
memory never leave the deployment. A dual control plane separates the end-user platform from operator
administration, and every model backend is configured by you with your own API keys (the product
ships with **zero keys**).

## Features

- **Knowledge bases** — ingest text / PDF / Office (docx, xlsx, pptx) via the self-built **Terrane
  Parse** engine (page layout, ruled & borderless tables, formulas) — all on CPU, no GPU.
- **Video & audio understanding** — ffmpeg keyframes + audio → vision (VL) captions + speech (ASR)
  transcript, ingested back into the knowledge base.
- **Hybrid retrieval** — pgvector semantic search + lexical search + reranking.
- **Knowledge graph** — Apache AGE graph over your sources, with graph exploration.
- **Personal Chat assistant** — cross-knowledge-base auto-grounding, a web-search toggle with source
  cards, multi-modal attachments (docs / images / video / audio), persistent conversations, and
  memory recall.
- **Studio (NotebookLM-style)** — one-click study guide, FAQ, briefing, timeline, mind map,
  flashcards, quiz, data table, **slide deck (PPTX export)** and **audio overview (two-host podcast,
  TTS)**.
- **Long-term memory** — automatically remembered from your chats and uploaded documents, plus manual
  entries; deduped & updated (extract → retrieve → ADD/UPDATE), fully per-user isolated.
- **Model channels** — chat / embedding / rerank / vision / ASR / TTS backends, all configured in the
  admin console with your own keys (DashScope / OpenAI-compatible).
- **MCP server** — expose knowledge bases as MCP tools for external agents.
- **Enterprise** — workspaces & RBAC, SSO (OIDC), 2FA, field-level encryption (KEK), audit logging,
  observability, backup & migration, and optional license-gated activation.

## Architecture

Five application services + two datastores:

| Component | Role |
|---|---|
| `terrane-server` | Front business control plane (knowledge base / retrieval / Chat / Studio / memory), `:43001` |
| `terrane-admin-server` | Admin control plane (activation / wizard / model channels / members), `:43003` |
| `terrane-gateway` | Go data-plane gateway |
| `terrane-web` | Front SPA (nginx) |
| `terrane-admin-web` | Admin SPA (nginx) |
| **PostgreSQL 18 + Apache AGE + pgvector** | Knowledge graph + vector retrieval + relational data (required extensions) |
| **Redis** | Cache + rate limiting |

Two logical databases live on one PostgreSQL instance: `terrane_main` (platform) and `terrane_admin`
(operators).

## Tech stack

- **Backend** — Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, asyncpg, Redis, Pydantic v2,
  argon2id, structlog.
- **Data plane** — Go gateway.
- **Frontend** — React 19, Vite, Tailwind v4, react-i18next (zh-CN / en).
- **Models** — DashScope / OpenAI-compatible (chat, embedding, rerank, vision, ASR, TTS).

## Repository layout

```
Terrane/
├── Project-source/        # all services
│   ├── terrane-server/        # front business API (FastAPI)
│   ├── terrane-admin-server/  # admin API (FastAPI)
│   ├── terrane-gateway/       # data-plane gateway (Go)
│   ├── terrane-web/           # front SPA (React)
│   └── terrane-admin-web/     # admin SPA (React)
├── terrane-deploy/        # delivery: docker-compose / helm / gitlab / migration
└── ops/                   # ops scripts (multi-arch build, backup, Xinchuang notes)
```

## Deployment

Pick a path from [`terrane-deploy/`](terrane-deploy/README.md):

| Path | Use when |
|---|---|
| **docker-compose** | single host / appliance / air-gapped (bundled PostgreSQL + Redis by default) |
| **Helm** | Kubernetes incl. Xinchuang (domestic) K8s (external datastores by default) |
| **GitLab CI/CD** | build multi-arch images → manual push → manual Helm deploy |

### Single-host quick start

```bash
cd terrane-deploy/docker-compose
cp .env.example .env        # fill TERRANE_KEK + DB/Redis passwords
docker compose up -d        # brings up the full stack incl. PG18+AGE+pgvector & Redis
```

Then in the admin console: **change the factory super-admin password → run the setup wizard →
configure your model channels (your own API keys)**. The front app is then fully usable. (License
activation is optional and off by default.)

> The bundled PostgreSQL image ships Apache AGE + pgvector. CPU-only, no GPU required.

## License

Terrane is open-source software released under the **MIT License** — see [LICENSE](LICENSE).

It also ships an optional, self-hostable license-gating mechanism (disabled by default) for
organizations that want per-deployment activation; field-level secrets are encrypted with a
per-deployment KEK.
