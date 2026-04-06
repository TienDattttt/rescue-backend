from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.monitored_post import MonitoredPost
from app.models.pipeline_job import PipelineJob, PipelineJobStatusEnum
from app.models.rescue_case import RescueCase
from app.pipeline.stage1_scraper import SCRAPER_UNAVAILABLE_ERROR, extract_post_id_from_url, stage1_scrape
from app.pipeline.stage2_classifier import stage2_classify
from app.pipeline.stage3_extractor import stage3_extract
from app.pipeline.stage4_dedup import stage4_dedup

logger = logging.getLogger(__name__)


async def _update_job(db: AsyncSession, job_id: str, **kwargs: Any) -> None:
    job = await db.get(PipelineJob, uuid.UUID(job_id))
    if job is None:
        return
    for key, value in kwargs.items():
        setattr(job, key, value)
    await db.commit()
    await db.refresh(job)


async def _save_cases_to_db(
    db: AsyncSession,
    final_cases: list[dict[str, Any]],
    post_url: str,
    total_comments: int,
    source_post_id: str,
) -> None:
    source_post_id = str(source_post_id or '').strip()
    if source_post_id:
        await db.execute(delete(RescueCase).where(RescueCase.source_post_id == source_post_id))

    districts = sorted({str(item.get('district') or '').strip() for item in final_cases if str(item.get('district') or '').strip()})

    monitored_post = await db.get(MonitoredPost, source_post_id) if source_post_id else None
    if source_post_id:
        if monitored_post is None:
            monitored_post = MonitoredPost(
                id=source_post_id,
                title=post_url,
                source_name='Facebook',
                sync_status='live',
                comment_volume=total_comments,
                last_sync_at=datetime.now(timezone.utc),
                district_scope=districts,
            )
            db.add(monitored_post)
        else:
            monitored_post.title = post_url
            monitored_post.source_name = 'Facebook'
            monitored_post.sync_status = 'live'
            monitored_post.comment_volume = total_comments
            monitored_post.last_sync_at = datetime.now(timezone.utc)
            monitored_post.district_scope = districts

    if not final_cases:
        logger.warning('Pipeline finished with no rescue cases for post %s', source_post_id or post_url)
        await db.commit()
        return

    db.add_all(RescueCase(**{key: value for key, value in item.items() if not key.startswith('_')}) for item in final_cases)
    await db.commit()
    logger.info('Saved %s cases for post %s', len(final_cases), source_post_id or post_url)


def _infer_source_post_id(post_url: str, raw_comments: list[dict[str, Any]]) -> str:
    for comment in raw_comments:
        post_id = str(comment.get('post_id') or '').strip()
        if post_id:
            return post_id

    try:
        return extract_post_id_from_url(post_url)
    except Exception:
        return ''


async def _run_pipeline_after_scrape(
    job_id: str,
    post_url: str,
    raw_comments: list[dict[str, Any]],
    source_post_id: str,
    db: AsyncSession,
) -> None:
    await _update_job(
        db,
        job_id,
        status=PipelineJobStatusEnum.classifying,
        current_stage='Dang phan loai comment cau cuu...',
        post_id=source_post_id or None,
        progress=25,
        total_comments=len(raw_comments),
    )
    sos_comments = await stage2_classify(raw_comments)
    await _update_job(
        db,
        job_id,
        progress=50,
        classified_count=len(sos_comments),
        current_stage=f'Da phan loai: {len(sos_comments)} cau cuu / {len(raw_comments)}',
    )

    await _update_job(db, job_id, status=PipelineJobStatusEnum.extracting, current_stage='Dang trich xuat thong tin bang AI...')
    extracted = await stage3_extract(sos_comments, job_id=job_id)
    await _update_job(
        db,
        job_id,
        progress=75,
        extracted_count=len(extracted),
        current_stage=f'Da trich xuat {len(extracted)} ca',
    )

    await _update_job(db, job_id, status=PipelineJobStatusEnum.deduplicating, current_stage='Dang loai trung lap...')
    final_cases = stage4_dedup(extracted)
    await _save_cases_to_db(
        db,
        final_cases,
        post_url=post_url,
        total_comments=len(raw_comments),
        source_post_id=source_post_id,
    )
    await _update_job(
        db,
        job_id,
        status=PipelineJobStatusEnum.done,
        progress=100,
        current_stage=f'Hoan thanh: {len(final_cases)} ca sau dedup',
    )


async def _mark_job_failed(db: AsyncSession, job_id: str, exc: Exception) -> None:
    message = str(exc)
    if message == SCRAPER_UNAVAILABLE_ERROR:
        logger.error('Pipeline job %s failed: %s', job_id, message)
    else:
        logger.exception('Pipeline job %s failed', job_id)

    await _update_job(
        db,
        job_id,
        status=PipelineJobStatusEnum.failed,
        error_message=message,
        current_stage='Pipeline failed',
    )


async def _run_pipeline_with_session(job_id: str, post_url: str, db: AsyncSession) -> None:
    try:
        post_id = extract_post_id_from_url(post_url)
        await _update_job(
            db,
            job_id,
            status=PipelineJobStatusEnum.scraping,
            current_stage='Dang crawl comments tu Facebook...',
            post_id=post_id,
            progress=0,
        )
        raw_comments = await stage1_scrape(post_url)
        await _update_job(
            db,
            job_id,
            progress=10,
            total_comments=len(raw_comments),
            current_stage=f'Da crawl {len(raw_comments)} comments',
        )
        await _run_pipeline_after_scrape(job_id, post_url, raw_comments, post_id, db)
    except Exception as exc:
        await _mark_job_failed(db, job_id, exc)


async def _run_pipeline_from_comments_with_session(
    job_id: str,
    post_url: str,
    raw_comments: list[dict[str, Any]],
    db: AsyncSession,
) -> None:
    try:
        source_post_id = _infer_source_post_id(post_url, raw_comments)
        await _update_job(
            db,
            job_id,
            status=PipelineJobStatusEnum.classifying,
            current_stage=f'Loaded {len(raw_comments)} pre-scraped comments',
            post_id=source_post_id or None,
            progress=10,
            total_comments=len(raw_comments),
        )
        await _run_pipeline_after_scrape(job_id, post_url, raw_comments, source_post_id, db)
    except Exception as exc:
        await _mark_job_failed(db, job_id, exc)


async def run_pipeline(job_id: str, post_url: str, db: AsyncSession | None = None) -> None:
    if db is not None:
        await _run_pipeline_with_session(job_id, post_url, db)
        return

    async with async_session_maker() as session:
        await _run_pipeline_with_session(job_id, post_url, session)


async def run_pipeline_from_comments(
    job_id: str,
    post_url: str,
    raw_comments: list[dict[str, Any]],
    db: AsyncSession | None = None,
) -> None:
    if db is not None:
        await _run_pipeline_from_comments_with_session(job_id, post_url, raw_comments, db)
        return

    async with async_session_maker() as session:
        await _run_pipeline_from_comments_with_session(job_id, post_url, raw_comments, session)