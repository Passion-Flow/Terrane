# Terrane 版本锁定（设计期锚点 2026-06-13）

> 版本时效铁律：以下为设计期锚点；每个组件**开发前**重新 Web Search 核最新 STABLE 并钉死 tag，更新本文件。存储三元组按 `.agent.md`[项目专属规则]§1 例外管理（升级必走回归集）。

## 存储（锁死三元组）
| 组件 | 版本 | 备注 |
|------|------|------|
| PostgreSQL | 18.x（基底 `pgvector/pgvector:pg18-trixie`） | LightRAG 官方基线 |
| Apache AGE | `release/PG18/1.7.0` 源码分支 | 官方 Docker `release_PG18_1.7.0` 双架构存在 |
| pgvector | 0.8.x（0.8.3 发布后升——PG18 Hamming/Jaccard 回归修复） | 主线 halfvec+cosine 不受回归影响 |
| zhparser | v2.3+（2026-06 仍活跃） | 中文分词主路 |
| LightRAG | 固定 tag（开发期钉死，一周三发不追 latest） | PG 单后端模式 |

## 运行时
| 组件 | 锚点 | 备注 |
|------|------|------|
| Python | 3.13+（视依赖矩阵，开发前核） | FastAPI/SQLAlchemy 2.x/Celery/Pydantic |
| Go | 最新 stable | gateway + Sync |
| Node | 24 LTS | 前端构建 |
| mcp（python-sdk） | ≥1.27（2025-11-25 协议版） | stateless_http=True |
| React / Vite / Tailwind | 19.2.x / 8.0.x / 4.3.x | `@tailwindcss/vite` 插件 |
| @base-ui/react | 1.5.x | shadcn `--base base-ui` |
| sigma.js / graphology | 3.0.x / 0.26.x | |
| NetworkX | ≥3.4（forceatlas2_layout） | BSD |
| llama.cpp | 开发期钉 commit | 生成/嵌入/重排三实例 |

## 模型（离线包 CPU 档；体积为 HF API 实测）
| 模型 | 版本/量化 | 体积 |
|------|----------|------|
| Qwen3-4B（生成） | Q4_K_M GGUF | 2.50GB |
| Qwen3-Embedding-0.6B | Q8_0 GGUF | 0.64GB |
| BGE-reranker-v2-m3 | int8 | ~0.6GB |
| SenseVoiceSmall（ASR） | int8 | ~0.25GB |
| MinerU ≥3.1.0 pipeline 模型组（仅 2.5-Pro 系权重） | — | 1.5-2GB |
| MeloTTS-Chinese | — | ~0.5GB |
| Docling 中文 OCR 预置 | — | ~0.2GB |
| **CPU 档合计** | | **≈6.5-7GB** |
| GPU 档追加：Qwen3-8B Q4 / Qwen3-Embedding-4B / Qwen3-Reranker-4B / MinerU VLM / CosyVoice2(3.86GB) / faster-whisper turbo / ColQwen2(许可待核) | | 15-29GB |

## 硬件基线（如实宣传红线，.agent.md §9）
CPU 档：8 物理核（AVX2）/ 内存最低 24GB·推荐 32GB / 磁盘 64GB·推荐 128GB SSD。GPU 档：单卡 24GB 全承载。
