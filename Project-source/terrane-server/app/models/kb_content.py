"""Knowledge base content storage ORM (platform DB terrane_main): RawSource / Chunk / WikiPage / IngestJob.

chunks.embedding (halfvec) and content_tsv (generated column) are not mapped into the ORM — pgvector is not
installed locally, so vector read/write goes through raw SQL (::halfvec cast); the ORM only handles
structured fields. Hard delete: cascades from the KB as a real delete.
"""

from __future__ import annotations

import uuid

import datetime

from sqlalchemy import BigInteger, DateTime, Integer, LargeBinary, String, Text, Uuid, func
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
    """Chunk. embedding (halfvec) / content_tsv (generated column) are not in the ORM; see the module docstring."""

    __tablename__ = "chunks"

    kb_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    raw_source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ord: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RawSourceOriginal(Base):
    """Metadata for the raw bytes of an uploaded file. Bytes are stored in object storage first
    (key=originals/{rid}); the data column is only used for legacy data / fallback. Kept in a separate
    table so list/get don't load the blob. Hard-deleted by cascade from the source (object-storage side
    is cleaned up by the delete hook)."""

    __tablename__ = "raw_source_originals"

    raw_source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # data is nullable: NULL when object storage succeeds (bytes live in the bucket); on storage failure, fall back to storing the bytes here.
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RawSourceRender(Base):
    """Render status of per-page WebP layout images of the original document. Page-image bytes are stored in
    object storage (key=pages/{rid}/{n}.webp); this table only stores metadata (page count + per-page
    dimensions), which the front end uses to lazy-load single pages by viewport. Hard-deleted by cascade
    from the source."""

    __tablename__ = "raw_source_renders"

    raw_source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending/rendering/done/failed/skipped
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # [{"n":1,"w":1654,"h":2339}, ...]
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


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
