"""Self-developed answer-grounding verification (engine ④).

Algorithm is ours; the LLM is just the configured cloud primitive. Given an answer and the retrieved
context, decompose the answer into claims and check each against the context, returning a groundedness
score in [0,1] plus any unsupported claims. This is what turns "an answer" into "a trustworthy, citable
answer" and lets the front end flag / abstain on weak grounding. One cheap LLM call. Best-effort: any
failure returns grounded=None (verification simply unavailable, never blocks the answer).
"""

from __future__ import annotations

import json
import re

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.verify")

# functional verification prompt — kept Chinese per project convention (model replies in the answer's language)
_PROMPT = (
    "你是答案接地核查器。只依据【资料】判断【答案】里的每条事实主张是否被资料支持。\n"
    "输出 JSON:{{\"grounded\":0~1 的支持比例, \"unsupported\":[不被资料支持的主张原文,最多5条]}}。\n"
    "只输出 JSON,不要解释。\n\n【资料】\n{ctx}\n\n【答案】\n{ans}"
)


def _parse(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        g = d.get("grounded")
        g = max(0.0, min(1.0, float(g))) if g is not None else None
        uns = [str(x) for x in (d.get("unsupported") or [])][:5]
        return {"grounded": g, "unsupported": uns}
    except (ValueError, TypeError):
        return None


async def verify_grounded(db: AsyncSession, *, answer: str, contexts: list[str]) -> dict:
    """Return {grounded: float|None, unsupported: [str]}. grounded=None when verification is unavailable."""
    ans = (answer or "").strip()
    ctx = "\n\n".join(c.strip() for c in contexts if c and c.strip())
    if not ans or not ctx:
        return {"grounded": None, "unsupported": []}
    prompt = _PROMPT.format(ctx=ctx[:6000], ans=ans[:3000])
    try:
        raw = await model_client.chat_complete(db, [{"role": "user", "content": prompt}],
                                                temperature=0.0, max_tokens=500)
    except ModelError as e:
        log.warning("verify_no_model", error=str(e))
        return {"grounded": None, "unsupported": []}
    parsed = _parse(raw)
    if parsed is None:
        return {"grounded": None, "unsupported": []}
    log.info("verify_done", grounded=parsed["grounded"], unsupported=len(parsed["unsupported"]))
    return parsed
