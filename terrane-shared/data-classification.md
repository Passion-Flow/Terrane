# Terrane 数据分类清单（data-compliance.md L1-L5）

| 数据 | 等级 | 存储 | 加密/处理 | DSR 行为 |
|------|------|------|----------|----------|
| Raw 源原件/解析产物 | **L4** | 对象存储 | 卷加密=部署指引；备份 AES-256 | 硬删 + 对象清理 |
| chunks.content / wiki_pages.body_md / 图实体属性 | **L4** | PG | 同上 | 硬删 + AGE drop + git history-rewrite |
| memories / memory_episodes / conversations / messages | **L4** | PG | 同上；per-user 永不跨用户 | 用户删除全级联 + mem graph 销毁 |
| git 镜像卷（Wiki Markdown） | **L4** | 本地卷/PVC | 卷加密=部署指引（private 库承诺的一部分） | 随删随 commit；DSR rewrite/整仓销毁 |
| connector_configs.credentials / channels.api_key / webhook secret | **L5** | PG | 字段级 envelope AES-256-GCM；vault 占位符（Agent 不可见） | 实例删除即密文删除 |
| users.password_hash | L5(哈希) | PG | argon2id | 账户删除级联 |
| users.email / profile | L3 | PG | 防枚举 | 删除/导出 |
| usage_records / ingest 账单 / product_events | L3 | PG 分区 | 保留期走 Data Retention 策略 | 匿名化保留聚合或删除 |
| audit_logs | L3 | PG 分区 | append-only ≥1 年；**仅操作元数据绝不含内容** | 不删（合规例外），主体标识可匿名化 |
| settings / branding / model_roles | L2 | PG | — | — |
| 公开文档/THIRD-PARTY-NOTICES | L1 | 镜像内 | — | — |

数据出境：私有化客户自管模型渠道自担；产品文档明示"外接云端模型时，送检索上下文与对话内容至所配厂商"。
导出（DSR 访问权）：`kb/{id}/export` 全量包 + 用户级记忆/对话导出。
删除（DSR 删除权）：硬删除铁律全链（PG 级联 + AGE drop + 对象存储 + git rewrite + 备份过期自然滚出，备份保留期内的介质访问受恢复审计约束）。
