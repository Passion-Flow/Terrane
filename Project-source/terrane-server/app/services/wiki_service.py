"""Wiki 编译投影（平台库 terrane_main）——知识复利核心:把 Raw 源 LLM 编译成结构化 Wiki。

Wiki 是 Raw/图的投影:agent 编译生成(source='agent'),用户可接管编辑(source='user')。
无源支撑的推断段落标 inferred=true(前端标「推断」)。本增量:编译 KB 概览页;按主题分页后续。
"""

from __future__ import annotations

import re
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb_content import WikiPage
from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.wiki")

_COMPILE_PROMPT = (
    "你是知识编译器。把下面的【资料】整理成一篇结构化的知识 Wiki,用 Markdown 输出(含 ## 小标题、要点列表)。"
    "要求:只基于资料,严禁编造;合并重复信息,去除冗余;条理清晰、便于检索。直接输出 Markdown 正文,不要前后多余说明。\n\n【资料】\n"
)
_MAX = 8000


def _slugify(s: str) -> str:
    base = re.sub(r"[^a-z0-9一-鿿]+", "-", s.lower()).strip("-")[:48]
    return base or "overview"


async def compile_overview(db: AsyncSession, kb_id: uuid.UUID, workspace_id: uuid.UUID,
                           kb_name: str, sources: list[tuple[str, str]]) -> WikiPage | None:
    """把全部源编译成一篇「概览」Wiki 页(upsert)。返回 WikiPage;无源/无模型→None。"""
    corpus = "\n\n".join(f"## {t}\n{x}" for t, x in sources if x and x.strip())[:_MAX]
    if not corpus.strip():
        return None
    try:
        body = await model_client.chat_complete(
            db, [{"role": "user", "content": _COMPILE_PROMPT + corpus}], temperature=0.2, max_tokens=3000)
    except ModelError as e:
        log.warning("wiki_compile_failed", error=str(e))
        raise

    slug = "overview"
    page = (await db.execute(select(WikiPage).where(
        WikiPage.kb_id == kb_id, WikiPage.slug == slug))).scalar_one_or_none()
    title = f"{kb_name} · 概览"
    if page is None:
        page = WikiPage(kb_id=kb_id, workspace_id=workspace_id, slug=slug, title=title,
                        body_md=body, source="agent", status="published", inferred=False)
        db.add(page)
    else:
        page.title = title
        page.body_md = body
        page.source = "agent"
        page.status = "published"
    await db.commit()
    await db.refresh(page)
    log.info("wiki_compiled", kb_id=str(kb_id), slug=slug, chars=len(body))
    return page


async def list_pages(db: AsyncSession, kb_id: uuid.UUID) -> list[WikiPage]:
    return list((await db.execute(select(WikiPage).where(WikiPage.kb_id == kb_id)
                                  .order_by(WikiPage.updated_at.desc()))).scalars().all())


async def get_page(db: AsyncSession, kb_id: uuid.UUID, slug: str) -> WikiPage | None:
    return (await db.execute(select(WikiPage).where(
        WikiPage.kb_id == kb_id, WikiPage.slug == slug))).scalar_one_or_none()
