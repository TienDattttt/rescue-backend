from __future__ import annotations

import enum

from sqlalchemy import DateTime, Enum as SqlEnum, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SyncStatus(str, enum.Enum):
    live = 'live'
    lagging = 'lagging'
    paused = 'paused'


class MonitoredPost(Base):
    __tablename__ = 'monitored_posts'

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default='Facebook')
    sync_status: Mapped[SyncStatus] = mapped_column(SqlEnum(SyncStatus, name='sync_status'), nullable=False, default=SyncStatus.live)
    comment_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    district_scope: Mapped[list[str]] = mapped_column(ARRAY(String()), nullable=False, default=list)
