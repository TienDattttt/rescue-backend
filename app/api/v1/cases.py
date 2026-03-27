from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.rescue_case import RescueCase, RescueStatus
from app.schemas.pipeline import CaseStatusPatch
from app.schemas.rescue_case import RescueCaseOut

router = APIRouter(prefix='')


@router.get('/cases', response_model=list[RescueCaseOut])
async def list_cases(
    activePresetId: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[RescueCase]:
    del activePresetId
    result = await db.execute(
        select(RescueCase)
        .where(RescueCase.rescue_status != RescueStatus.false_alarm)
        .order_by(RescueCase.created_at.desc())
    )
    return list(result.scalars().all())


@router.patch('/cases/{case_id}', response_model=RescueCaseOut)
async def update_case_status(
    case_id: str,
    payload: CaseStatusPatch,
    db: AsyncSession = Depends(get_db),
) -> RescueCase:
    try:
        case_uuid = uuid.UUID(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Case không tồn tại.') from exc

    case = await db.get(RescueCase, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Case không tồn tại.')
    if payload.rescueStatus not in {item.value for item in RescueStatus}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='rescueStatus không hợp lệ.')

    case.rescue_status = RescueStatus(payload.rescueStatus)
    await db.commit()
    await db.refresh(case)
    return case
