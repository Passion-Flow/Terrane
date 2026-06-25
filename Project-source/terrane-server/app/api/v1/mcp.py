"""Terrane MCP Server — exposes a knowledge base as MCP tools for use in Claude Code / Cursor, etc.

Stateless Streamable HTTP: a single POST /mcp endpoint handles JSON-RPC (initialize / tools/list / tools/call).
Bearer auth (api_keys.token_hash), scoped to the single KB bound to the key. Tools: search_knowledge / ask_knowledge.
No dependency on the mcp library — the protocol is just JSON-RPC, implemented directly.
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
     "description": "Hybrid semantic + keyword retrieval over this knowledge base; returns the most relevant chunks (with sources).",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Search question or keywords"},
         "top_k": {"type": "integer", "description": "Number of chunks to return (default 5)", "default": 5}},
         "required": ["query"]}},
    {"name": "ask_knowledge",
     "description": "Answer a question from this knowledge base; the answer is grounded strictly in the sources and cites them.",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string", "description": "The question to answer"}},
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
            return {"content": [{"type": "text", "text": "(No relevant content found in this knowledge base)"}]}
        lines = [f"[{i + 1}] (source: {h['source_title']}, relevance {h['score']})\n{h['content']}"
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
            return {"content": [{"type": "text", "text": f"(Chat model unavailable: {e})"}], "isError": True}
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
