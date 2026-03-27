from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.pipeline_job import PipelineJob, PipelineJobStatusEnum
from app.pipeline.orchestrator import run_pipeline
from app.schemas.pipeline import PipelineJobStatus, PipelineRunRequest, PipelineRunResponse

router = APIRouter(prefix='/pipeline')


def _is_facebook_post_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith('http://') or lowered.startswith('https://') and ('facebook.com/' in lowered or 'fb.com/' in lowered)


@router.post('/run', response_model=PipelineRunResponse)
async def run_pipeline_job(
    payload: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunResponse:
    if 'facebook.com/' not in payload.post_url.lower() and 'fb.com/' not in payload.post_url.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='post_url phải là Facebook URL hợp lệ.')

    job = PipelineJob(post_url=payload.post_url, status=PipelineJobStatusEnum.pending, progress=0)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(run_pipeline, str(job.id), payload.post_url)
    return PipelineRunResponse(job_id=str(job.id), status='pending')


@router.get('/status/{job_id}', response_model=PipelineJobStatus)
async def get_pipeline_status(job_id: str, db: AsyncSession = Depends(get_db)) -> PipelineJob:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Pipeline job không tồn tại.') from exc

    job = await db.get(PipelineJob, job_uuid)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Pipeline job không tồn tại.')
    return job


@router.get('/jobs', response_model=list[PipelineJobStatus])
async def list_pipeline_jobs(db: AsyncSession = Depends(get_db)) -> list[PipelineJob]:
    result = await db.execute(select(PipelineJob).order_by(PipelineJob.created_at.desc()).limit(20))
    return list(result.scalars().all())
