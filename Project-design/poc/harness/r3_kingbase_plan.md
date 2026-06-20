# R3 PoC 方案：KingbaseES 图存储替换路径（信创 SKU 前置）

**背景**：金仓无 AGE/pgvector 任何一手证据（2026-06-13 核验）；设计已定"graph_store 接口替换实现"路径（04-services §2）。

**试验步骤**（拿到 KingbaseES V9 试用镜像后）：
1. 扩展兼容探底：尝试源码编译 pgvector 与 AGE（KES 基线偏 PG9.6 系，预期 AGE 失败、pgvector 半数可能）；
2. 若 pgvector 可用：向量路保留，仅图走替换；若不可用：向量改 KES 自带向量能力（V9 宣称有）或词法+图双路降级；
3. **图替换实现基准**：`graph_store` 的 SQL 邻接表实现（nodes/edges 两表 + 递归 CTE ≤3 跳）跑 02-database §4.1 同款操作集（MERGE 语义=UPSERT、邻域、子图删除、双时态边过滤），对照 AGE 版回归集断言行为等价；
4. 性能基线：10 万节点/50 万边邻域查询 P95，与 AGE 版对比，偏慢 ≤3 倍可接受（信创场景吞吐预期低）。

**判定**：行为等价回归全绿 → 金仓 provider 排进开发；否则信创 SKU 文档如实标注"金仓适配中，当前推荐 openGauss/PolarDB-PG"。
