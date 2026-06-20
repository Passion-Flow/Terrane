"""模型调用客户端（前台）：嵌入 / 重排 / 对话，走 admin 配置的渠道。

- 嵌入/对话:OpenAI 兼容(DashScope compatible-mode)。
- 重排:DashScope 原生 rerank 端点(非 OpenAI 格式)。
未配置渠道 → 返回 None,调用方优雅降级(如纯词法检索)。失败抛 ModelError。
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.model_channels import get_channel, get_channel_by_model


async def _pick(db, kind: str, model: str | None):
    """按用户选定 model 取渠道(前台「模型设置」),无选/无匹配 → 默认该 kind 渠道。"""
    if model:
        ch = await get_channel_by_model(db, kind, model)
        if ch is not None:
            return ch
    return await get_channel(db, kind)

log = structlog.get_logger("terrane.model")

EMBED_DIM = 1024  # text-embedding-v4 默认 1024,对齐 chunks.embedding halfvec(1024)
_EMBED_BATCH = 10


class ModelError(Exception):
    pass


async def embed_texts(db: AsyncSession, texts: list[str], *, model: str | None = None) -> list[list[float]] | None:
    """批量嵌入。无 embed 渠道 → None。返回与 texts 等长、顺序一致的向量列表。"""
    ch = await _pick(db, "embed", model)
    if ch is None or not ch.base_url or not ch.api_key:
        return None
    import httpx

    url = ch.base_url.rstrip("/") + "/embeddings"
    headers = {"Authorization": f"Bearer {ch.api_key}", "Content-Type": "application/json"}
    out: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i:i + _EMBED_BATCH]
            r = await client.post(url, headers=headers, json={"model": ch.model, "input": batch})
            if r.status_code >= 400:
                raise ModelError(f"embed_http_{r.status_code}: {r.text[:200]}")
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out.extend([d["embedding"] for d in data])
    return out


async def embed_query(db: AsyncSession, query: str, *, model: str | None = None) -> list[float] | None:
    vecs = await embed_texts(db, [query], model=model)
    return vecs[0] if vecs else None


async def rerank(db: AsyncSession, query: str, documents: list[str], top_n: int | None = None, *, model: str | None = None) -> list[tuple[int, float]] | None:
    """重排:返回 [(原索引, 相关分)] 降序。无 rerank 渠道 → None。DashScope 原生格式。"""
    ch = await _pick(db, "rerank", model)
    if ch is None or not ch.base_url or not ch.api_key or not documents:
        return None
    import httpx

    headers = {"Authorization": f"Bearer {ch.api_key}", "Content-Type": "application/json"}
    payload = {"model": ch.model,
               "input": {"query": query, "documents": documents},
               "parameters": {"top_n": top_n or len(documents), "return_documents": False}}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(ch.base_url, headers=headers, json=payload)
    if r.status_code >= 400:
        raise ModelError(f"rerank_http_{r.status_code}: {r.text[:200]}")
    results = r.json().get("output", {}).get("results", [])
    return [(x["index"], float(x["relevance_score"])) for x in results]


async def vl_caption(db: AsyncSession, image_b64: str, *, prompt: str = "详细客观地描述这一帧画面的主要内容(物体/文字/场景/动作)。") -> str | None:
    """多模态:描述一帧图像(base64)。渠道(base_url/key/model)全取自后台「模型渠道」kind=vl。无渠道→None。"""
    ch = await get_channel(db, "vl")
    if ch is None or not ch.base_url or not ch.api_key or not ch.model:
        return None
    import httpx

    url = ch.base_url.rstrip("/") + "/chat/completions"
    payload = {"model": ch.model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}]}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {ch.api_key}"}, json=payload)
    if r.status_code >= 400:
        raise ModelError(f"vl_http_{r.status_code}: {r.text[:160]}")
    return r.json()["choices"][0]["message"]["content"]


async def asr(db: AsyncSession, audio_b64: str, *, mime: str = "audio/wav") -> str | None:
    """语音识别:转录音频(base64)。渠道取自后台「模型渠道」kind=asr。无渠道→None。"""
    ch = await get_channel(db, "asr")
    if ch is None or not ch.base_url or not ch.api_key or not ch.model:
        return None
    import httpx

    url = ch.base_url.rstrip("/") + "/chat/completions"
    payload = {"model": ch.model, "messages": [{"role": "user", "content": [
        {"type": "input_audio", "input_audio": {"data": f"data:{mime};base64,{audio_b64}"}}]}]}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {ch.api_key}"}, json=payload)
    if r.status_code >= 400:
        raise ModelError(f"asr_http_{r.status_code}: {r.text[:160]}")
    return r.json()["choices"][0]["message"]["content"]


async def chat_stream(base_url: str, api_key: str, model: str, messages: list[dict], *,
                      temperature: float = 0.3, max_tokens: int = 2048, enable_search: bool = False):
    """流式对话(SSE)。不依赖 DB 会话。enable_search=联网搜索(qwen 内置)。逐段 yield 文本增量。"""
    import json as _json

    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature,
               "max_tokens": max_tokens, "stream": True}
    if enable_search:
        payload["enable_search"] = True  # DashScope/qwen 内置联网搜索
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "ignore")
                raise ModelError(f"chat_http_{resp.status_code}: {body[:200]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = _json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content")
                except (ValueError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta


_DS_NATIVE = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
_DS_TTS = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


async def chat_stream_search(api_key: str, model: str, messages: list[dict], *,
                             temperature: float = 0.3, max_tokens: int = 2048):
    """DashScope 原生流式 + 联网搜索。yield ('sources', list) 一次 + ('delta', str) 多次。"""
    import json as _json

    import httpx

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "X-DashScope-SSE": "enable"}
    payload = {"model": model, "input": {"messages": messages},
               "parameters": {"result_format": "message", "incremental_output": True,
                              "temperature": temperature, "max_tokens": max_tokens,
                              "enable_search": True,
                              "search_options": {"enable_source": True, "enable_citation": True, "forced_search": True}}}
    sent = False
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", _DS_NATIVE, headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "ignore")
                raise ModelError(f"chat_search_http_{resp.status_code}: {body[:200]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    out = _json.loads(data).get("output", {})
                except ValueError:
                    continue
                if not sent:
                    si = out.get("search_info") or {}
                    res = si.get("search_results") if isinstance(si, dict) else None
                    if res:
                        sent = True
                        yield ("sources", [{"index": r.get("index"), "title": r.get("title"),
                                            "url": r.get("url"), "site": r.get("site_name")} for r in res])
                try:
                    delta = out["choices"][0]["message"].get("content")
                except (KeyError, IndexError, TypeError):
                    delta = None
                if delta:
                    yield ("delta", delta)


async def tts(db: AsyncSession, text: str, *, voice: str = "Cherry") -> bytes | None:
    """文本转语音(qwen-tts)。渠道取自后台 kind=tts。返回 wav 字节;无渠道→None。"""
    ch = await get_channel(db, "tts")
    if ch is None or not ch.api_key or not ch.model or not text.strip():
        return None
    import asyncio

    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = None
        for attempt in range(4):  # 429 限流退避重试(播客连续合成多段)
            r = await client.post(_DS_TTS, headers={"Authorization": f"Bearer {ch.api_key}"},
                                  json={"model": ch.model, "input": {"text": text, "voice": voice}})
            if r.status_code != 429:
                break
            await asyncio.sleep(1.5 * (attempt + 1))
        if r is None or r.status_code >= 400:
            raise ModelError(f"tts_http_{r.status_code if r is not None else 'none'}: {(r.text[:160] if r is not None else '')}")
        au = (r.json().get("output", {}).get("audio") or {}).get("url")
        if not au:
            return None
        a = await client.get(au)
        return a.content if a.status_code < 400 else None


async def chat_complete(db: AsyncSession, messages: list[dict], *, temperature: float = 0.3,
                        max_tokens: int = 2048) -> str:
    """非流式对话补全。无 chat 渠道 → ModelError。"""
    ch = await get_channel(db, "chat")
    if ch is None or not ch.base_url or not ch.api_key:
        raise ModelError("no_chat_channel")
    import httpx

    url = ch.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {ch.api_key}", "Content-Type": "application/json"}
    payload = {"model": ch.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, json=payload)
    if r.status_code >= 400:
        raise ModelError(f"chat_http_{r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]
