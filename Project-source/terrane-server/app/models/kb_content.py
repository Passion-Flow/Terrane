"""知识库内容存储 ORM（平台库 terrane_main）：RawSource / Chunk / WikiPage / IngestJob。

chunks.embedding(halfvec) 与 content_tsv(生成列)不映射进 ORM —— 本机未装 pgvector,向量读写走原始 SQL
(::halfvec 转型);ORM 只管结构化字段。硬删除:随 kb 级联真删。
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin


class RawSource(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "raw_sources"

    kb_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="file")  # file/url/text/connector
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending/parsing/parsed/failed
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Chunk(UUIDMixin, Base):
    """切片。embedding(halfvec)/content_tsv(生成列)不在 ORM,见模块注释。"""

    __tablename__ = "chunks"

    kb_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    raw_source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ord: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WikiPage(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "wiki_pages"

    kb_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="agent")  # agent/user
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")  # draft/published
    inferred: Mapped[bool] = mapped_column(nullable=False, default=False)


class IngestJob(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "ingest_jobs"

    kb_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="parse")  # parse/embed/graph/lint
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
