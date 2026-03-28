from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class RescueCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    sourcePostId: Annotated[str, Field(validation_alias=AliasChoices('source_post_id', 'sourcePostId'))]
    rawComment: Annotated[str, Field(validation_alias=AliasChoices('raw_comment', 'rawComment'))]
    commenterName: Annotated[str | None, Field(default=None, validation_alias=AliasChoices('commenter_name', 'commenterName'))]
    severity: Literal['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NOT_RESCUE']
    locationDescription: Annotated[
        str | None,
        Field(default=None, validation_alias=AliasChoices('location_description', 'locationDescription')),
    ]
    normalizedAddress: Annotated[
        str | None,
        Field(default=None, validation_alias=AliasChoices('normalized_address', 'normalizedAddress')),
    ]
    district: str
    lat: float | None = None
    lng: float | None = None
    numPeople: Annotated[int | None, Field(default=None, validation_alias=AliasChoices('num_people', 'numPeople'))]
    vulnerableGroups: Annotated[
        list[str],
        Field(default_factory=list, validation_alias=AliasChoices('vulnerable_groups', 'vulnerableGroups')),
    ]
    accessibility: Literal['EASY', 'MODERATE', 'HARD'] | None = None
    waitingHours: Annotated[
        float | None,
        Field(default=None, validation_alias=AliasChoices('waiting_hours', 'waitingHours')),
    ]
    aiConfidence: Annotated[
        float | None,
        Field(default=None, validation_alias=AliasChoices('ai_confidence', 'aiConfidence')),
    ]
    geocodeStatus: Annotated[
        Literal['pending', 'success', 'failed'],
        Field(validation_alias=AliasChoices('geocode_status', 'geocodeStatus')),
    ]
    rescueStatus: Annotated[
        Literal['waiting', 'dispatched', 'rescued', 'false_alarm'],
        Field(validation_alias=AliasChoices('rescue_status', 'rescueStatus')),
    ]
    currentScore: Annotated[
        float | None,
        Field(default=None, validation_alias=AliasChoices('current_score', 'currentScore')),
    ]
    currentRank: Annotated[
        int | None,
        Field(default=None, validation_alias=AliasChoices('current_rank', 'currentRank')),
    ]
    createdAt: Annotated[str, Field(validation_alias=AliasChoices('created_at', 'createdAt'))]
    updatedAt: Annotated[str, Field(validation_alias=AliasChoices('updated_at', 'updatedAt'))]

    @field_validator('id', mode='before')
    @classmethod
    def serialize_uuid(cls, value: Any) -> str:
        if isinstance(value, UUID):
            return str(value)
        return str(value)

    @field_validator('createdAt', 'updatedAt', mode='before')
    @classmethod
    def serialize_datetime(cls, value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
