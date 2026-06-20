#!/usr/bin/env python3
"""R2 PoC: 1MB 文档 LightRAG 抽取 token 实测（校准估价系数 tier_coef，01-system D4）。
依赖: pip install lightrag-hku tiktoken; env: LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（任一 OpenAI 兼容端点）
     + 本目录起 terrane-postgres:poc (run_poc.sh 同款) 提供 PG 后端。
用法: python r2_token_bench.py <真实文档目录>   # 建议混合中英 PDF 解析后的 .md 共 ~1MB
输出: 总输入/输出 token、每 MB 系数（与设计锚点 60-170 万/MB 对比）、写回 settings 的建议系数。
"""
import os, sys, glob, json, time

def main():
    docs_dir = sys.argv[1]
    files = glob.glob(os.path.join(docs_dir, "*.md"))
    total_bytes = sum(os.path.getsize(f) for f in files)
    print(f"语料: {len(files)} 文件 / {total_bytes/1e6:.2f} MB")
    # 计量方式: 经 terrane 设计同款路径——LightRAG insert + 包一层计数的 OpenAI client
    # （此处为台架骨架：接 lightrag 的 llm_model_func 包装器，累计 prompt/completion tokens）
    # 断言输出: tokens_per_mb 与估价公式 est = bytes/4*1.35*2.5 的偏差 → 校准建议
    raise SystemExit("台架骨架：填入 LLM 凭据后按注释接通 lightrag 计量包装器再跑")

if __name__ == "__main__":
    main()
