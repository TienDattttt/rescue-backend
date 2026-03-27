from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.rescue_case import RescueCaseOut


class MonitoredPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    title: str
    sourceName: Annotated[str, Field(validation_alias=AliasChoices('source_name', 'sourceName'))]
    syncStatus: Annotated[
        Literal['live', 'lagging', 'paused'],
        Field(validation_alias=AliasChoices('sync_status', 'syncStatus')),
    ]
    commentVolume: Annotated[int, Field(validation_alias=AliasChoices('comment_volume', 'commentVolume'))]
    lastSyncAt: Annotated[str, Field(validation_alias=AliasChoices('last_sync_at', 'lastSyncAt'))]
    districtScope: Annotated[
        list[str],
        Field(default_factory=list, validation_alias=AliasChoices('district_scope', 'districtScope')),
    ]

    @field_validator('lastSyncAt', mode='before')
    @classmethod
    def serialize_datetime(cls, value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)


class DashboardStatsOut(BaseModel):
    totalIncomingCases: int
    waitingCases: int
    criticalCount: int
    geocodedCount: int
    activePosts: int
    shortlistedCount: int
    lastSyncAt: str
    currentPresetLabel: str
    consistencyRatio: float


class IncomingEventOut(BaseModel):
    id: str
    type: Literal['new_case', 'rescued', 'geocode_failed', 'ai_refresh']
    caseId: str | None = None
    title: str
    detail: str
    createdAt: str


class PipelineHealthOut(BaseModel):
    scraper: Literal['healthy', 'degraded', 'offline']
    aiInference: Literal['healthy', 'degraded', 'offline']
    geocoding: Literal['healthy', 'degraded', 'offline']
    realtime: Literal['healthy', 'degraded', 'offline']


class AHPPresetOut(BaseModel):
    id: str
    label: str
    description: str
    matrix: list[list[float]]


class DispatchTeamOut(BaseModel):
    id: str
    name: str
    district: str
    status: Literal['available', 'en_route', 'busy']
    capacity: int


class DashboardOut(BaseModel):
    stats: DashboardStatsOut
    cases: list[RescueCaseOut]
    posts: list[MonitoredPostOut]
    events: list[IncomingEventOut] = Field(default_factory=list)
    pipelineStatus: PipelineHealthOut
    presets: list[AHPPresetOut]
