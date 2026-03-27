from __future__ import annotations

import enum
import uuid

from sqlalchemy import DateTime, Enum as SqlEnum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SeverityLevel(str, enum.Enum):
    CRITICAL = 'CRITICAL'
    HIGH = 'HIGH'
    MEDIUM = 'MEDIUM'
    LOW = 'LOW'
    NOT_RESCUE = 'NOT_RESCUE'


class AccessibilityLevel(str, enum.Enum):
    EASY = 'EASY'
    MODERATE = 'MODERATE'
    HARD = 'HARD'


class GeocodeStatus(str, enum.Enum):
    pending = 'pending'
    success = 'success'
    failed = 'failed'


class RescueStatus(str, enum.Enum):
    waiting = 'waiting'
    dispatched = 'dispatched'
    rescued = 'rescued'
    false_alarm = 'false_alarm'


class RescueCase(Base):
    __tablename__ = 'rescue_cases'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_post_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    raw_comment: Mapped[str] = mapped_column(Text, nullable=False)
    commenter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[SeverityLevel] = mapped_column(SqlEnum(SeverityLevel, name='severity_level'), nullable=False)
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    district: Mapped[str] = mapped_column(String(255), nullable=False, default='')
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    num_people: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vulnerable_groups: Mapped[list[str]] = mapped_column(ARRAY(String()), nullable=False, default=list)
    accessibility: Mapped[AccessibilityLevel | None] = mapped_column(
        SqlEnum(AccessibilityLevel, name='accessibility_level'), nullable=True
    )
    waiting_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    geocode_status: Mapped[GeocodeStatus] = mapped_column(
        SqlEnum(GeocodeStatus, name='geocode_status'), nullable=False, default=GeocodeStatus.pending
    )
    rescue_status: Mapped[RescueStatus] = mapped_column(
        SqlEnum(RescueStatus, name='rescue_status'), nullable=False, default=RescueStatus.waiting
    )
    current_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
