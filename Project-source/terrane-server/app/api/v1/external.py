"""Terrane External Knowledge API —— 把知识库暴露给任意外部应用作「外部知识库 / 检索工具」。

三个面向,共用一套 Bearer 鉴权(复用 api_keys 的 trn_ 令牌,scope 到密钥绑定的单个 KB):
  • Dify 兼容:   POST /api/v1/external/retrieval   (知识库基址填 {host}/api/v1/external)
  • 通用检索:     POST /api/v1/external/search       ({query, top_k, score_threshold})
  • 自描述工具:   GET  /api/v1/external/openapi.json  (供 Coze 插件 / GPTs Actions / n8n / FastGPT 导入)

Dify 规范:Authorization: Bearer <key>;请求 {knowledge_id, query, retrieval_setting:{top_k, score_threshold},
metadata_condition?};成功 200 {records:[{content, score, title, metadata:{}}]};
失败非 200 {error_code, error_msg}(1001 头格式错 / 1002 鉴权失败 / 2001 库不存在)。
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
from app.services import ingest_service

log = structlog.get_logger("terrane.external")

router = APIRouter(prefix="/api/v1/external", tags=["external-knowledge"])

_MAX_TOP_K = 50


def _err(code: int, msg: str, status: int) -> JSONResponse:
    """Dify 规范的错误体。"""
    return JSONResponse({"error_code": code, "error_msg": msg}, status_code=status)


async def _auth_key(request: Request, db: AsyncSession) -> ApiKey | JSONResponse:
    """Bearer 鉴权;失败时直接返回 Dify 规范错误响应(调用方需判类型)。"""
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
    """搬成 Dify records 形状。score 夹到 [0,1];metadata 必须是对象(不能 null)。"""
    out = []
    for h in hits:
        try:
            score = max(0.0, min(1.0, float(h.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        sid = str(h.get("source_id") or "")
        out.append({
            "content": h.get("content", ""),
            "score": score,
            "title": h.get("source_title") or "untitled",
            "metadata": {"source_id": sid, "document_id": sid, "knowledge_base": "terrane"},
        })
    return out


async def _retrieve(db: AsyncSession, kb_id, query: str, top_k: int, threshold: float) -> list[dict]:
    if not query.strip():
        return []
    limit = max(1, min(int(top_k or 5), _MAX_TOP_K))
    hits = await ingest_service.search_chunks(db, kb_id=kb_id, query=query, limit=limit)
    records = _to_records(hits)
    # 不按 score_threshold 硬过滤:Terrane 的「向量+词法混合(可选重排)」分不一定落在调用方的
    # 0-1 标尺上(常 <0.5),硬过滤会让 Dify 等默认阈值 0.5 的应用「什么都搜不到」。
    # 检索本身已排序,直接返回 top_k 最相关项;阈值仅在调用方明确传且能命中时做软收紧。
    if threshold and threshold > 0:
        kept = [r for r in records if r["score"] >= threshold]
        if kept:
            records = kept
    return records


@router.post("/retrieval")
async def dify_retrieval(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Dify「外部知识库」回调端点。"""
    key = await _auth_key(request, db)
    if isinstance(key, JSONResponse):
        return key
    try:
        body = await request.json()
    except Exception:
        return _err(400, "Request body must be valid JSON.", 400)

    knowledge_id = str(body.get("knowledge_id") or "").strip()
    # knowledge_id 必须等于密钥绑定的库 id(留空则放行,容错)
    if knowledge_id and knowledge_id != str(key.kb_id):
        return _err(2001, "Knowledge base not found or not accessible with this API key.", 404)

    rs = body.get("retrieval_setting") or {}
    records = await _retrieve(db, key.kb_id, str(body.get("query") or ""),
                              rs.get("top_k", 5), float(rs.get("score_threshold") or 0.0))
    return JSONResponse({"records": records})


@router.post("/search")
async def generic_search(request: Request, db: AsyncSession = Depends(get_db_session)):
    """通用检索端点(n8n / 自研 / HTTP 节点直连)。入参更随意,出参同 Dify records。"""
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
                              float(body.get("score_threshold") or 0.0))
    return JSONResponse({"records": records, "query": query.strip(), "count": len(records)})


@router.get("/openapi.json")
async def openapi_schema(request: Request):
    """自描述 OpenAPI 3.0,server 按实际部署地址自动填充。可直接导入 Coze 插件 / GPTs Actions / n8n。"""
    base = (_public_base_url(request) or str(request.base_url).rstrip("/")).rstrip("/")
    server = base + "/api/v1/external"
    record_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "命中片段正文"},
            "score": {"type": "number", "description": "相关度 0~1"},
            "title": {"type": "string", "description": "来源文档标题"},
            "metadata": {"type": "object", "description": "来源元数据"},
        },
    }
    return JSONResponse({
        "openapi": "3.0.1",
        "info": {"title": "Terrane Knowledge Retrieval", "version": "1.0.0",
                 "description": "在 Terrane 知识库中做语义+关键词混合检索,返回相关片段。Bearer 鉴权。"},
        "servers": [{"url": server}],
        "security": [{"bearerAuth": []}],
        "paths": {
            "/search": {
                "post": {
                    "operationId": "searchKnowledge",
                    "summary": "检索知识库",
                    "description": "传入自然语言 query,返回最相关的资料片段(带来源与相关度)。",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["query"], "properties": {
                            "query": {"type": "string", "description": "检索问题或关键词"},
                            "top_k": {"type": "integer", "default": 5, "description": "返回片段数(1-50)"},
                            "score_threshold": {"type": "number", "default": 0, "description": "相关度阈值 0~1"},
                        }}}}},
                    "responses": {"200": {"description": "检索结果", "content": {"application/json": {"schema": {
                        "type": "object", "properties": {
                            "records": {"type": "array", "items": record_schema},
                            "count": {"type": "integer"},
                        }}}}}},
                },
            },
            "/retrieval": {
                "post": {
                    "operationId": "difyRetrieval",
                    "summary": "Dify 外部知识库回调",
                    "description": "Dify「连接外部知识库」专用。基址填 " + server + " ,Dify 会自动调用 /retrieval。",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["query", "retrieval_setting"], "properties": {
                            "knowledge_id": {"type": "string"},
                            "query": {"type": "string"},
                            "retrieval_setting": {"type": "object", "properties": {
                                "top_k": {"type": "integer"}, "score_threshold": {"type": "number"}}},
                        }}}}},
                    "responses": {"200": {"description": "检索结果", "content": {"application/json": {"schema": {
                        "type": "object", "properties": {"records": {"type": "array", "items": record_schema}}}}}}},
                },
            },
        },
        "components": {"securitySchemes": {"bearerAuth": {
            "type": "http", "scheme": "bearer", "description": "知识库接入密钥(trn_ 令牌)"}}},
    })
