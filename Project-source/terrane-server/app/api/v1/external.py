"""Terrane External Knowledge API — exposes a knowledge base to any external app as an "external knowledge base / retrieval tool".

Three entry points sharing one Bearer auth scheme (reuses the trn_ token from api_keys, scoped to the single KB bound to the key):
  • Dify-compatible:   POST /api/v1/external/retrieval   (set the knowledge base endpoint to {host}/api/v1/external)
  • Generic search:    POST /api/v1/external/search       ({query, top_k, score_threshold})
  • Self-describing tool: GET /api/v1/external/openapi.json (for import into Coze plugins / GPTs Actions / n8n / FastGPT)

Dify spec: Authorization: Bearer <key>; request {knowledge_id, query, retrieval_setting:{top_k, score_threshold},
metadata_condition?}; success 200 {records:[{content, score, title, metadata:{}}]};
failure non-200 {error_code, error_msg} (1001 bad header format / 1002 auth failure / 2001 KB not found).
"""

from __future__ import annotations

import datetime
import hashlib

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.v1.auth import _public_base_url
from app.models.api_key import ApiKey
from app.services import retrieval_service

log = structlog.get_logger("terrane.external")

router = APIRouter(prefix="/api/v1/external", tags=["external-knowledge"])

_MAX_TOP_K = 50


def _err(code: int, msg: str, status: int) -> JSONResponse:
    """Error body in the Dify spec format."""
    return JSONResponse({"error_code": code, "error_msg": msg}, status_code=status)


async def _auth_key(request: Request, db: AsyncSession) -> ApiKey | JSONResponse:
    """Bearer auth; on failure, returns a Dify-spec error response directly (caller must check the type)."""
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        return _err(1001, "Invalid Authorization header format. Expected 'Bearer <api-key>'.", 403)
    token = h[7:].strip()
    if not token:
        return _err(1001, "Invalid Authorization header format. Expected 'Bearer <api-key>'.", 403)
    th = hashlib.sha256(token.encode()).hexdigest()
    key = (await db.execute(select(ApiKey).where(ApiKey.token_hash == th))).scalar_one_or_none()
    if key is None:
        return _err(1002, "Authorization failed. The API key is invalid or revoked.", 403)
    key.last_used_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    return key


def _to_records(hits: list[dict]) -> list[dict]:
    """Reshape into Dify records format. score is clamped to [0,1]; metadata must be an object (never null).
    Retrieval 2.0 adds an explainable citation path / page range to metadata when available."""
    out = []
    for h in hits:
        try:
            score = max(0.0, min(1.0, float(h.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        sid = str(h.get("source_id") or "")
        meta = {"source_id": sid, "document_id": sid, "knowledge_base": "terrane"}
        if h.get("citation_path"):
            meta["section_path"] = h["citation_path"]
        if h.get("page_start"):
            meta["page_start"] = h["page_start"]
            meta["page_end"] = h.get("page_end")
        out.append({
            "content": h.get("content", ""),
            "score": score,
            "title": h.get("source_title") or "untitled",
            "metadata": meta,
        })
    return out


async def _retrieve(db: AsyncSession, kb_id, query: str, top_k: int, threshold: float, mode: str = "auto") -> list[dict]:
    if not query.strip():
        return []
    limit = max(1, min(int(top_k or 5), _MAX_TOP_K))
    hits = await retrieval_service.retrieve(db, kb_id=kb_id, query=query, mode=mode, limit=limit)
    records = _to_records(hits)
    # Don't hard-filter by score_threshold: Terrane's "vector + lexical hybrid (optional rerank)" scores
    # don't necessarily fall on the caller's 0-1 scale (often <0.5), so hard filtering would make apps
    # like Dify (default threshold 0.5) "find nothing at all".
    # The search results are already ranked, so just return the top_k most relevant items; the threshold
    # is only applied as a soft tightening when the caller explicitly passes it and it still matches something.
    if threshold and threshold > 0:
        kept = [r for r in records if r["score"] >= threshold]
        if kept:
            records = kept
    return records


@router.post("/retrieval")
async def dify_retrieval(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Dify "external knowledge base" callback endpoint."""
    key = await _auth_key(request, db)
    if isinstance(key, JSONResponse):
        return key
    try:
        body = await request.json()
    except Exception:
        return _err(400, "Request body must be valid JSON.", 400)

    knowledge_id = str(body.get("knowledge_id") or "").strip()
    # knowledge_id must equal the KB id bound to the key (allowed through if empty, for tolerance)
    if knowledge_id and knowledge_id != str(key.kb_id):
        return _err(2001, "Knowledge base not found or not accessible with this API key.", 404)

    rs = body.get("retrieval_setting") or {}
    records = await _retrieve(db, key.kb_id, str(body.get("query") or ""),
                              rs.get("top_k", 5), float(rs.get("score_threshold") or 0.0))
    return JSONResponse({"records": records})


@router.post("/search")
async def generic_search(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Generic search endpoint (n8n / custom builds / direct HTTP-node connection). Inputs are more lenient; output matches Dify records."""
    key = await _auth_key(request, db)
    if isinstance(key, JSONResponse):
        return key
    try:
        body = await request.json()
    except Exception:
        return _err(400, "Request body must be valid JSON.", 400)
    query = str(body.get("query") or body.get("question") or "")
    records = await _retrieve(db, key.kb_id, query,
                              body.get("top_k", body.get("limit", 5)),
                              float(body.get("score_threshold") or 0.0),
                              str(body.get("mode") or "auto"))
    return JSONResponse({"records": records, "query": query.strip(), "count": len(records)})


@router.get("/openapi.json")
async def openapi_schema(request: Request):
    """Self-describing OpenAPI 3.0; the server field is auto-populated from the actual deployment address. Directly importable into Coze plugins / GPTs Actions / n8n."""
    base = (_public_base_url(request) or str(request.base_url).rstrip("/")).rstrip("/")
    server = base + "/api/v1/external"
    record_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The matched chunk text"},
            "score": {"type": "number", "description": "Relevance score, 0-1"},
            "title": {"type": "string", "description": "Source document title"},
            "metadata": {"type": "object", "description": "Source metadata"},
        },
    }
    return JSONResponse({
        "openapi": "3.0.1",
        "info": {"title": "Terrane Knowledge Retrieval", "version": "1.0.0",
                 "description": "Hybrid semantic + keyword retrieval over a Terrane knowledge base; returns relevant chunks. Bearer auth."},
        "servers": [{"url": server}],
        "security": [{"bearerAuth": []}],
        "paths": {
            "/search": {
                "post": {
                    "operationId": "searchKnowledge",
                    "summary": "Search the knowledge base",
                    "description": "Pass a natural-language query; returns the most relevant chunks (with source and relevance).",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["query"], "properties": {
                            "query": {"type": "string", "description": "Search question or keywords"},
                            "top_k": {"type": "integer", "default": 5, "description": "Number of chunks to return (1-50)"},
                            "score_threshold": {"type": "number", "default": 0, "description": "Relevance threshold, 0-1"},
                        }}}}},
                    "responses": {"200": {"description": "Retrieval results", "content": {"application/json": {"schema": {
                        "type": "object", "properties": {
                            "records": {"type": "array", "items": record_schema},
                            "count": {"type": "integer"},
                        }}}}}},
                },
            },
            "/retrieval": {
                "post": {
                    "operationId": "difyRetrieval",
                    "summary": "Dify external-knowledge callback",
                    "description": "For Dify's \"Connect to an external knowledge base\". Set the base URL to " + server + " ; Dify calls /retrieval automatically.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["query", "retrieval_setting"], "properties": {
                            "knowledge_id": {"type": "string"},
                            "query": {"type": "string"},
                            "retrieval_setting": {"type": "object", "properties": {
                                "top_k": {"type": "integer"}, "score_threshold": {"type": "number"}}},
                        }}}}},
                    "responses": {"200": {"description": "Retrieval results", "content": {"application/json": {"schema": {
                        "type": "object", "properties": {"records": {"type": "array", "items": record_schema}}}}}}},
                },
            },
        },
        "components": {"securitySchemes": {"bearerAuth": {
            "type": "http", "scheme": "bearer", "description": "Knowledge base access key (trn_ token)"}}},
    })
