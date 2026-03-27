from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, field_validator


class PipelineRunRequest(BaseModel):
    post_url: str


class PipelineRunResponse(BaseModel):
    job_id: str
    status: str


class PipelineJobStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    postUrl: Annotated[str, Field(validation_alias=AliasChoices('post_url', 'postUrl'))]
    status: str
    progress: int
    currentStage: Annotated[str | None, Field(default=None, validation_alias=AliasChoices('current_stage', 'currentStage'))]
    totalComments: Annotated[int | None, Field(default=None, validation_alias=AliasChoices('total_comments', 'totalComments'))]
    classifiedCount: Annotated[
        int | None,
        Field(default=None, validation_alias=AliasChoices('classified_count', 'classifiedCount')),
    ]
    extractedCount: Annotated[
        int | None,
        Field(default=None, validation_alias=AliasChoices('extracted_count', 'extractedCount')),
    ]
    errorMessage: Annotated[
        str | None,
        Field(default=None, validation_alias=AliasChoices('error_message', 'errorMessage')),
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


class CaseStatusPatch(BaseModel):
    rescueStatus: str
