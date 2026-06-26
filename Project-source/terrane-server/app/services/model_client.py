"""Model invocation client (front-end): embedding / rerank / chat, via channels configured in admin.

- Embedding/chat: OpenAI-compatible (DashScope compatible-mode).
- Rerank: DashScope's native rerank endpoint (not OpenAI format).
No configured channel -> returns None, and the caller degrades gracefully (e.g. lexical-only retrieval). Failures raise ModelError.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.model_channels import get_channel, get_channel_by_model


async def _pick(db, kind: str, model: str | None):
    """Pick a channel by the user-selected model (front-end "Model settings"); if none selected or no match -> the default channel for that kind."""
    if model:
        ch = await get_channel_by_model(db, kind, model)
        if ch is not None:
            return ch
    return await get_channel(db, kind)

log = structlog.get_logger("terrane.model")

EMBED_DIM = 1024  # text-embedding-v4 defaults to 1024, aligned with chunks.embedding halfvec(1024)
_EMBED_BATCH = 10


class ModelError(Exception):
    pass


async def embed_texts(db: AsyncSession, texts: list[str], *, model: str | None = None) -> list[list[float]] | None:
    """Batch embedding. No embed channel -> None. Returns a vector list the same length as texts and in the same order."""
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
    """Rerank: returns [(original index, relevance score)] in descending order. No rerank channel -> None. DashScope native format."""
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
    """Multimodal: describe a single image frame (base64). The channel (base_url/key/model) is taken entirely from the admin "Model channels" kind=vl. No channel -> None."""
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


async def vl_caption_multi(db: AsyncSession, images_b64: list[str], *, prompt: str,
                           labels: list[str] | None = None, max_tokens: int = 8000) -> str | None:
    """Multimodal over SEVERAL images in one call (ordered) — used to parse a table that spans pages so the
    model can see adjacent pages together and stitch continued rows. Each image may be preceded by a short
    text label (e.g. '第 N 页：'). No vl channel -> None."""
    ch = await get_channel(db, "vl")
    if ch is None or not ch.base_url or not ch.api_key or not ch.model or not images_b64:
        return None
    import httpx

    url = ch.base_url.rstrip("/") + "/chat/completions"
    content: list[dict] = [{"type": "text", "text": prompt}]
    for i, b64 in enumerate(images_b64):
        if labels and i < len(labels) and labels[i]:
            content.append({"type": "text", "text": labels[i]})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {"model": ch.model, "messages": [{"role": "user", "content": content}],
               "max_tokens": max_tokens, "temperature": 0.0}
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {ch.api_key}"}, json=payload)
    if r.status_code >= 400:
        raise ModelError(f"vl_http_{r.status_code}: {r.text[:160]}")
    return r.json()["choices"][0]["message"]["content"]


async def asr(db: AsyncSession, audio_b64: str, *, mime: str = "audio/wav") -> str | None:
    """Speech recognition: transcribe audio (base64). The channel is taken from the admin "Model channels" kind=asr. No channel -> None."""
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
    """Streaming chat (SSE). Does not depend on a DB session. enable_search = web search (qwen built-in). Yields text deltas incrementally."""
    import json as _json

    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature,
               "max_tokens": max_tokens, "stream": True}
    if enable_search:
        payload["enable_search"] = True  # DashScope/qwen built-in web search
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
    """DashScope native streaming + web search. Yields ('sources', list) once + ('delta', str) multiple times."""
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
    """Text-to-speech (qwen-tts). The channel is taken from admin kind=tts. Returns wav bytes; no channel -> None."""
    ch = await get_channel(db, "tts")
    if ch is None or not ch.api_key or not ch.model or not text.strip():
        return None
    import asyncio

    import httpx

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = None
        for attempt in range(4):  # Back-off retry on 429 rate limiting (podcasts synthesize many segments in a row)
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
    """Non-streaming chat completion. No chat channel -> ModelError."""
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
