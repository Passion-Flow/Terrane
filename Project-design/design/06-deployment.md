# 部署设计：Terrane 个人知识库平台

状态：**v1.1 定稿**（2026-06-13，终审 28 项修订后定稿——用户授权"按照你的理解来"） ｜ 依据：PRD 4.13 + `.agent.md`[镜像规划/跨平台] ｜ 对齐：04-Deployment 全套规范

---

## 1. 镜像规划

8 镜像 + 1 自建基础镜像，见 `.agent.md`[镜像规划]（api/worker/scheduler/gateway/web/admin-api/admin-web/inference + terrane-postgres）。tag 钉死 `v1.0.0` 禁 latest（用户铁律：未发版前热修覆盖 v1.0.0）。非镜像交付物：Terrane Sync 三平台二进制、Clipper .crx/.xpi、离线模型包（外挂卷，版本与主程序解耦）。

## 2. multi-arch

- 全镜像 `docker buildx --platform linux/amd64,linux/arm64` 双 manifest（CI 强制，禁单架构）
- terrane-postgres：pgvector 官方镜像基底 + AGE `release/PG18/1.7.0` 源码编译 + zhparser（纯 C 扩展双架构无障碍，LightRAG Dockerfile.postgres 范式）
- terrane-inference：amd64 = AVX2 基线（运行时探测 AVX-512 用更优 kernel）；arm64 = NEON；GPU 档 CUDA 变体单独 tag `v1.0.0-cuda`
- 基础镜像优先 openEuler 系（信创铁律），避免 alpine/musl

## 3. 三套交付物（环境变量字段名一一对应）

| 交付物 | 形态 | 规格 |
|--------|------|------|
| **docker-compose** | 单机（个人版主打） | `docker-compose.yml` + `.env.example`（出厂默认值，向导改密）；profiles：`core`（默认）/ `inference`（离线包）/ `gpu`；卷：pg 数据/对象存储/git 镜像/licenses/模型包 |
| **GitLab** | docker-based 单机 + k8s-based 集群双 substrate | [2026-06-07] 补强规范：Scripts 双脚本（密钥生成/部署）+ 双语 README + customCA 注入 |
| **Helm** | 集群（企业版） | api/gateway/web HPA；worker 按队列分组 Deployment；scheduler 单副本（leader 选举预留）；PG = **自写 StatefulSet 模板**（terrane-postgres 自建镜像；Bitnami 公共目录 2025-08 起重组付费化，弃用）或 `externalDatabase` 接客户 PG（需确认 AGE/pgvector/zhparser 扩展可装）；Redis/对象存储同理可外接 |

单机→集群迁移：`terrane export-cluster`（pg_dump + 对象存储 sync + git 卷打包）→ Helm 侧 `terrane import` 任务，演练进验收（PRD §11）。

## 4. 网络拓扑（集群）

Ingress（TLS/cert-manager/rate-limit/WAF 注解，k8s-ingress.md）→ web/admin-web（静态）+ api/admin-api（含 `/mcp` `/api/v1/kb/*/events` SSE：Ingress 关闭代理缓冲、超时 ≥1h）→ 内网 Service：gateway（api/worker/**admin-api**[渠道 `:test` 必经] 可达）/ inference（仅 gateway 可达）/ PG/Redis/对象存储（NetworkPolicy 默认拒绝+白名单，k8s-security.md）。admin 面建议独立 Ingress host + IP 白名单。

## 5. 扩缩容

| 组件 | HPA 指标 | 副本基线 | 资源 requests/limits 基线 |
|------|---------|---------|--------------------------|
| api | CPU 70% + SSE 连接数自定义指标 | 2 | 0.5/2C，1/2Gi |
| gateway | CPU 70% | 2 | 0.25/1C，256Mi/512Mi |
| worker(ingest/graph) | 队列深度（KEDA 可选） | 2 | 1/4C，2/6Gi（MinerU 峰值） |
| worker(memory/misc) | 队列深度 | 1 | 0.5/2C，1/2Gi |
| scheduler | 不扩（单活） | 1 | 0.25C/512Mi |
| web/admin-web | CPU | 2/1 | 0.1C/128Mi |
| inference | 不自动扩（模型常驻） | 按需 | CPU 档 8C/24-32Gi；GPU 档 nvidia.com/gpu:1 |

PDB：api/gateway minAvailable 1；CPU 档单机无 HPA——compose 内 worker 并发由执行权信号量控制（解析×推理互斥）。

## 6. 安全

k8s-security.md 全套：Pod Security Standards restricted、securityContext 非 root/只读根文件系统（卷挂载例外：git 镜像/模型包）、NetworkPolicy 默认拒绝、RBAC 最小化、Secrets 走 Sealed Secrets/ESO（k8s-secrets.md）；镜像签名+SBOM（dependency-management.md）+ THIRD-PARTY-NOTICES 内置；离线包断网环境零外呼验证（除可选 Forge 在线租约——离线 .forge 模式零外呼）。

## 7. 备份 / 灾备

- RPO ≤1h / RTO ≤4h；**三位一体一致性快照**：PG（全量每日+WAL 每小时）+ 对象存储（3-2-1）+ git 镜像卷（与 PG 快照点对齐：备份任务先 flush git 队列再快照）
- K8s：VolumeSnapshot + Velero（disaster-recovery.md）；跨可用区可选；恢复演练季度+发版前
- 备份含 private 库内容 → 介质 AES-256 + 密钥部署方持有 + 恢复操作审计（PRD 4.1.6）

## 8. 多平台部署

multi-platform-deploy.md runbook：Linux 主线；Windows Server = Tier 2（WSL2/Linux 容器 runbook）；macOS = 开发期；信创 = 麒麟/UOS/openEuler runbook + openGauss（`enable_thread_pool=off` 写入 values 注释与文档）/PolarDB-PG 外接指引 + 金仓按 R3 PoC 结论补充；loong64 v2。

## 9. 监控告警

- Prometheus 抓取全容器 `/metrics`；Grafana dashboard 出厂（摄入管线/检索延迟/渠道健康/队列/预算/git 滞后）
- 关键告警规则：检索 P95 >2s（10min）、ingest 队列 >100 且 worker 满载、渠道全断（TRN_NO_AVAILABLE_CHANNEL 速率）、预算 100%、git 落盘滞后 >5min、备份失败、License 离到期 30/7 天、PG 磁盘 >80%、HNSW 构建积压
- 客户接入：OTel Data Push 后台页面化配置（OTLP endpoint+鉴权）；告警通道 Email+Webhook

---

## 历史变更
**[2026-06-13] v1.0 草案**：单机/集群同镜像双拓扑落地为 compose profiles + Helm 同 tag；三位一体快照与 SSE Ingress 细节定稿。

**[2026-06-13] v1.1 终审修订定稿**：交叉终审 3 阻塞+14 重要全部修复（MCP client 端点与页面/音频概览表与 UI/admin_readable 写扩权矫正/配额表/队列清单/SSE 枚举/对话结束判定/估价口径/唤回流/外部变更检测/web-search 渠道/伴读章节端点/埋点载体/锁定页轮询/Helm PG 自写模板/NetworkPolicy admin-api 放行等）；建议项已并入。
