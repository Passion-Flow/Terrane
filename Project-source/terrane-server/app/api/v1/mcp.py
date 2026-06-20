"""Terrane MCP Server —— 把知识库暴露为 MCP 工具,挂进 Claude Code / Cursor 等。

无状态 Streamable HTTP:单 POST /mcp 端点处理 JSON-RPC(initialize / tools/list / tools/call)。
Bearer 鉴权(api_keys.token_hash),scope 到密钥绑定的单个 KB。工具:search_knowledge / ask_knowledge。
不依赖 mcp 库——协议即 JSON-RPC,直接实现。
"""

from __future__ import annotations

import datetime
import hashlib

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.models.api_key import ApiKey
from app.services import ingest_service
from app.services.model_client import ModelError, chat_complete

log = structlog.get_logger("terrane.mcp")

router = APIRouter(prefix="/mcp", tags=["mcp"])

PROTOCOL_VERSION = "2025-03-26"

_TOOLS = [
    {"name": "search_knowledge",
     "description": "在该知识库中做语义+关键词混合检索,返回最相关的资料片段(带来源)。",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "检索问题或关键词"},
         "top_k": {"type": "integer", "description": "返回片段数(默认5)", "default": 5}},
         "required": ["query"]}},
    {"name": "ask_knowledge",
     "description": "基于该知识库内容回答问题,答案严格基于资料并标注引用。",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string", "description": "要回答的问题"}},
         "required": ["question"]}},
]


async def _auth(request: Request, db: AsyncSession) -> ApiKey:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        raise PermissionError("missing bearer")
    token = h[7:].strip()
    th = hashlib.sha256(token.encode()).hexdigest()
    key = (await db.execute(select(ApiKey).where(ApiKey.token_hash == th))).scalar_one_or_none()
    if key is None:
        raise PermissionError("invalid key")
    key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    return key


async def _call_tool(db: AsyncSession, kb_id, params: dict) -> dict:
    name = params.get("name")
    args = params.get("arguments") or {}
    if name == "search_knowledge":
        hits = await ingest_service.search_chunks(db, kb_id=kb_id, query=args.get("query", ""),
                                                  limit=int(args.get("top_k", 5)))
        if not hits:
            return {"content": [{"type": "text", "text": "(知识库中未检索到相关内容)"}]}
        lines = [f"[{i + 1}] (来源:{h['source_title']}, 相关度 {h['score']})\n{h['content']}"
                 for i, h in enumerate(hits)]
        return {"content": [{"type": "text", "text": "\n\n".join(lines)}]}
    if name == "ask_knowledge":
        q = args.get("question", "")
        hits = await ingest_service.search_chunks(db, kb_id=kb_id, query=q, limit=5)
        ctx = "\n\n".join(f"[{i + 1}] {h['content']}" for i, h in enumerate(hits)) or "(无相关资料)"
        msgs = [{"role": "system", "content": "严格依据【资料】回答,句末用[n]标注引用,资料不足就说未提及,不要编造。"},
                {"role": "user", "content": f"【资料】\n{ctx}\n\n【问题】{q}"}]
        try:
            answer = await chat_complete(db, msgs, temperature=0.2)
        except ModelError as e:
            return {"content": [{"type": "text", "text": f"(对话模型不可用: {e})"}], "isError": True}
        return {"content": [{"type": "text", "text": answer}]}
    return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}


@router.post("")
async def mcp_endpoint(request: Request, db: AsyncSession = Depends(get_db_session)):
    try:
        key = await _auth(request, db)
    except PermissionError:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32001, "message": "Unauthorized"}}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}}, status_code=400)

    method = body.get("method")
    rid = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "Terrane Knowledge Base", "version": "1.0.0"}}
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return Response(status_code=202)
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _TOOLS}
    elif method == "tools/call":
        result = await _call_tool(db, key.kb_id, params)
    else:
        return JSONResponse({"jsonrpc": "2.0", "id": rid,
                             "error": {"code": -32601, "message": f"Method not found: {method}"}})
    return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result})
