#!/usr/bin/env python3
"""R4 PoC: CPU 档 Qwen3-4B Q4 结构化抽取质量（离线包命门，PRD R4）。
依赖: llama.cpp llama-server --model Qwen3-4B-Q4_K_M.gguf --port 43091 (json_schema 约束输出)
评测: testdata/extract_cases.jsonl（30 条中英段落 + 人工标注实体/关系金标）
判定: 实体召回 ≥0.8 且关系召回 ≥0.7 且 JSON 合法率 ≥0.98 → PASS（达标=时序层 CPU 档可开）
     未达 → 离线包文档标注"图谱/时序层建议外接模型"（PRD 4.6.3/4.10.3 既定降级文案）。
用法: python r4_extract_quality.py  # 读 env LLAMA_URL，默认 http://127.0.0.1:43091
"""
# 台架骨架：schema={"entities":[{"name","etype"}],"relations":[{"src","dst","rtype"}]}
# 逐条调 /v1/chat/completions + response_format json_schema，对照金标算召回/合法率
raise SystemExit("台架骨架：下载权重并起 llama-server 后填 testdata 金标再跑")
