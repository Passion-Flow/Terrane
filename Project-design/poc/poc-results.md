# Terrane 设计期 PoC 结果（2026-06-13）

环境：macOS arm64 / Docker 29.5.2 / 自建镜像 `terrane-postgres:poc`（pgvector/pgvector:pg18-trixie + AGE release/PG18/1.7.0 源码编译）——构建路径本身即 06-deployment §2 的实证。

## 结论总表

| PoC | 验证目标 | 结果 | 对设计文档的影响 |
|-----|---------|------|------------------|
| **D2 混合查询** | AGE cypher CTE + pgvector halfvec 余弦在**单事务单 SQL** 内融合 | ✅ PASS（图 2 命中 + 向量 2 命中，HYBRID_OK） | 01-system D2 风险划除；02 §7 检索 SQL 形态可行性坐实 |
| **R1 投影回写** | 实体+1 跳 → Markdown 投影；人工接管断言（human_verified=true）回写图；重渲染人工事实优先排序 | ✅ PASS（V2 含 `inspired_by → [[Memex]] ✓人工` 且排首位） | PRD R1 高风险 → **低**；兜底方案（降级缓存渲染）保留但预期不触发 |
| **R16 双时态** | 边带 t_valid/t_invalid；矛盾消解=失效不删；as-of 时点查询；历史可回溯；用户硬删 DETACH DELETE | ✅ PASS（T=1500→"加糖"，T=2500→"不加糖"，HISTORY=2，硬删后 facts=1） | PRD R16 中风险 → **低**；自研双时态在 AGE openCypher 子集内完整可表达 |

## 过程中获得的真实工程知识（写入开发须知）

1. **`properties()` 等是 Cypher 函数不是 SQL 函数**——只能在 `cypher()` 内部使用；外层 SQL 取值必须在 cypher 的 `RETURN` 子句完成（`RETURN n.name, r.rtype`），agtype → `::text` 后自带引号需 trim。查询层封装（01-system D-R6）必须内置此约定。
2. **构建镜像必须装 `ca-certificates`**（第一次构建失败教训），已修入 PoC Dockerfile，正式 terrane-postgres Dockerfile 继承。
3. AGE `release/PG18/1.7.0` 分支真实存在且 arm64 源码编译顺利（纯 C，无补丁需求）；`shared_preload_libraries=age` + `CREATE EXTENSION age CASCADE` + 每会话 `LOAD 'age'; SET search_path` 三件套缺一不可。
4. agtype 布尔/数值比较（`r.t_valid <= 1500`、`r.t_invalid = -1`）在 WHERE 内工作正常；用 `-1` 表示"未失效"规避 NULL 比较的方言差异（02-database §4.2 采纳此约定）。

## 残留 PoC（试验台架已备，见同目录 harness/）

| PoC | 状态 | 依赖 | 阻塞性 |
|-----|------|------|--------|
| R2 1MB 抽取 token 实测 | 脚本就绪（harness/r2_token_bench.py） | 任一 OpenAI 兼容 API Key（env 注入） | 不阻塞开发启动；阶段④前出结论校准估价系数 |
| R4 CPU 小模型结构化抽取质量 | 脚本就绪（harness/r4_extract_quality.py） | 本机 llama.cpp + Qwen3-4B Q4 权重（~2.5GB 下载） | 不阻塞；离线包发布前必须出结论 |
| R3 金仓图存储替换 | 方案文档就绪（harness/r3_kingbase_plan.md） | KingbaseES 试用镜像（人工获取） | 不阻塞；信创 SKU 交付前必须出结论 |

## 复现

```bash
cd Terrane/Project-design/poc
docker build -t terrane-postgres:poc -f Dockerfile.terrane-postgres .
./run_poc.sh   # 三个 SQL 断言全绿即通过
```
PoC 容器用毕清理：`docker rm -f terrane-pg-poc`。本目录代码为丢弃式验证物，永不进产品代码库。
