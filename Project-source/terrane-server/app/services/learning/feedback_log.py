"""Retrieval feedback logging — the training asset for the self-developed learning-to-rank loop.

log_impression: record what was shown for a query (chunks + rank + score). Returns the row id, which the
  frontend echoes back when the user clicks / thumbs / accepts an answer.
log_feedback: attach implicit (click + dwell) and explicit (thumb, answer-accepted) signals to that row.
Best-effort: never raises (a logging failure must not break retrieval).
"""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger("terrane.feedback")


async def log_impression(db: AsyncSession, *, kb_id, user_id, query: str, mode: str,
                         hits: list[dict]) -> str | None:
    """Persist an impression; returns its id (str) for later feedback attachment, or None on failure."""
    try:
        fid = uuid.uuid4()
        shown = [{"chunk_id": h.get("chunk_id"), "rank": i, "score": h.get("score"),
                  "source_id": h.get("source_id")} for i, h in enumerate(hits)]
        await db.execute(text("""
            INSERT INTO retrieval_feedback (id, kb_id, user_id, query, mode, shown)
            VALUES (:id, :kb, :uid, :q, :mode, CAST(:shown AS jsonb))
        """), {"id": str(fid), "kb": str(kb_id), "uid": str(user_id) if user_id else None,
               "q": query[:4000], "mode": mode, "shown": json.dumps(shown, ensure_ascii=False)})
        await db.commit()
        return str(fid)
    except Exception as e:  # noqa: BLE001
        log.warning("impression_log_failed", error=str(e))
        return None


async def log_feedback(db: AsyncSession, *, feedback_id: str, kb_id, clicked: list | None = None,
                       thumb: int | None = None, answer_accepted: bool | None = None) -> bool:
    """Attach feedback to an impression. Only the provided signals are updated."""
    try:
        sets, params = [], {"id": feedback_id, "kb": str(kb_id)}
        if clicked is not None:
            sets.append("clicked = CAST(:clicked AS jsonb)")
            params["clicked"] = json.dumps(clicked, ensure_ascii=False)
        if thumb is not None:
            sets.append("thumb = :thumb"); params["thumb"] = max(-1, min(1, int(thumb)))
        if answer_accepted is not None:
            sets.append("answer_accepted = :acc"); params["acc"] = bool(answer_accepted)
        if not sets:
            return False
        await db.execute(text(f"UPDATE retrieval_feedback SET {', '.join(sets)} "
                              f"WHERE id = :id AND kb_id = :kb"), params)
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("feedback_log_failed", error=str(e))
        return False
