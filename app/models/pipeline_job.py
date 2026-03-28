from __future__ import annotations

import enum
import uuid

from sqlalchemy import DateTime, Enum as SqlEnum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PipelineJobStatusEnum(str, enum.Enum):
    pending = 'pending'
    scraping = 'scraping'
    classifying = 'classifying'
    extracting = 'extracting'
    deduplicating = 'deduplicating'
    done = 'done'
    failed = 'failed'


class PipelineJob(Base):
    __tablename__ = 'pipeline_jobs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PipelineJobStatusEnum] = mapped_column(
        SqlEnum(PipelineJobStatusEnum, name='pipeline_job_status'), nullable=False, default=PipelineJobStatusEnum.pending
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classified_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
