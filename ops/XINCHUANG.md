# Terrane 信创适配(构建完成,真平台验证后置)
## 架构:ops/build-multiarch.sh(buildx amd64+arm64,鲲鹏/飞腾)。基础镜像官方多架构,Dockerfile 无需改。麒麟/UOS 宿主跑 compose 即可。
## 数据库(openGauss/金仓/PolarDB,均 PG 协议兼容):适配点 ① openGauss SHA256 认证→asyncpg 需调 sslmode 或 md5;② 扩展 vector/age/pg_trgm 在 openGauss 用 datavec/移植版,AGE 缺则图谱降级(检索/RAG/Wiki 不依赖图仍可用);③ halfvec/tsvector 目标库核验。DB 层标准 SQLAlchemy,切库改连接串;扩展差异迁移内 IF NOT EXISTS+启动自检降级。真机核验留到信创服务器。
## 离线推理:llama.cpp + Qwen3-Embedding GGUF;国产卡走对应 backend,模型渠道指向本地 /v1(已支持)。
