from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.pipeline_job import PipelineJob, PipelineJobStatusEnum
from app.pipeline.orchestrator import run_pipeline, run_pipeline_from_comments
from app.pipeline.stage1_scraper import SCRAPER_AVAILABLE, SCRAPER_UNAVAILABLE_ERROR
from app.schemas.pipeline import (
    PipelineJobCreate,
    PipelineJobStatus,
    PipelineRunRequest,
    PipelineRunResponse,
    RunFromFileRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/pipeline')


def _is_facebook_post_url(url: str) -> bool:
    lowered = url.lower()
    return (lowered.startswith('http://') or lowered.startswith('https://')) and (
        'facebook.com/' in lowered or 'fb.com/' in lowered
    )


async def _create_job(db: AsyncSession, post_url: str) -> PipelineJob:
    job = PipelineJob(post_url=post_url, status=PipelineJobStatusEnum.pending, progress=0)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _fail_job(db: AsyncSession, job: PipelineJob, message: str) -> None:
    job.status = PipelineJobStatusEnum.failed
    job.current_stage = 'Pipeline failed'
    job.error_message = message
    await db.commit()
    await db.refresh(job)


@router.post('/run', response_model=PipelineRunResponse)
async def run_pipeline_job(
    payload: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunResponse:
    if not _is_facebook_post_url(payload.post_url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='post_url phai la Facebook URL hop le.')

    job = await _create_job(db, payload.post_url)

    if not SCRAPER_AVAILABLE:
        logger.warning('Scraper not available for job %s', job.id)
        await _fail_job(db, job, SCRAPER_UNAVAILABLE_ERROR)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='This deployment does not support Stage 1 scraping. Please provide pre-scraped data.',
        )

    background_tasks.add_task(run_pipeline, str(job.id), payload.post_url)
    return PipelineRunResponse(job_id=str(job.id), status='pending')


@router.post('/run-from-file', response_model=PipelineJobCreate, status_code=status.HTTP_201_CREATED)
async def run_pipeline_job_from_file(
    payload: RunFromFileRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineJobCreate:
    job = await _create_job(db, payload.post_url)
    background_tasks.add_task(run_pipeline_from_comments, str(job.id), payload.comments, payload.post_url)
    return PipelineJobCreate(job_id=str(job.id), status='pending')


@router.get('/status/{job_id}', response_model=PipelineJobStatus)
async def get_pipeline_status(job_id: str, db: AsyncSession = Depends(get_db)) -> PipelineJob:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Pipeline job khong ton tai.') from exc

    job = await db.get(PipelineJob, job_uuid)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Pipeline job khong ton tai.')
    return job


@router.get('/jobs', response_model=list[PipelineJobStatus])
async def list_pipeline_jobs(db: AsyncSession = Depends(get_db)) -> list[PipelineJob]:
    result = await db.execute(select(PipelineJob).order_by(PipelineJob.created_at.desc()).limit(20))
    return list(result.scalars().all())