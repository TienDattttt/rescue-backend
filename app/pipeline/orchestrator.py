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
from app.pipeline.stage1_scraper import extract_post_id_from_url, stage1_scrape
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


async def _save_cases_to_db(db: AsyncSession, final_cases: list[dict[str, Any]], post_url: str, total_comments: int) -> None:
    if not final_cases:
        return

    source_post_id = str(final_cases[0].get('source_post_id') or '')
    if source_post_id:
        await db.execute(delete(RescueCase).where(RescueCase.source_post_id == source_post_id))

    db.add_all(RescueCase(**{key: value for key, value in item.items() if not key.startswith('_')}) for item in final_cases)

    districts = sorted({str(item.get('district') or '').strip() for item in final_cases if str(item.get('district') or '').strip()})
    monitored_post = await db.get(MonitoredPost, source_post_id)
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

    await db.commit()


async def _run_pipeline_with_session(job_id: str, post_url: str, db: AsyncSession) -> None:
    try:
        post_id = extract_post_id_from_url(post_url)
        await _update_job(
            db,
            job_id,
            status=PipelineJobStatusEnum.scraping,
            current_stage='Đang crawl comments từ Facebook...',
            post_id=post_id,
            progress=0,
        )
        raw_comments = await stage1_scrape(post_url)
        await _update_job(
            db,
            job_id,
            progress=25,
            total_comments=len(raw_comments),
            current_stage=f'Đã crawl {len(raw_comments)} comments',
        )

        await _update_job(db, job_id, status=PipelineJobStatusEnum.classifying, current_stage='Đang phân loại comment cầu cứu...')
        sos_comments = await stage2_classify(raw_comments)
        await _update_job(
            db,
            job_id,
            progress=50,
            classified_count=len(sos_comments),
            current_stage=f'Đã phân loại: {len(sos_comments)} cầu cứu / {len(raw_comments)}',
        )

        await _update_job(db, job_id, status=PipelineJobStatusEnum.extracting, current_stage='Đang trích xuất thông tin bằng AI...')
        extracted = await stage3_extract(sos_comments)
        await _update_job(
            db,
            job_id,
            progress=75,
            extracted_count=len(extracted),
            current_stage=f'Đã trích xuất {len(extracted)} ca',
        )

        await _update_job(db, job_id, status=PipelineJobStatusEnum.deduplicating, current_stage='Đang loại trùng lặp...')
        final_cases = stage4_dedup(extracted)
        await _save_cases_to_db(db, final_cases, post_url=post_url, total_comments=len(raw_comments))
        await _update_job(
            db,
            job_id,
            status=PipelineJobStatusEnum.done,
            progress=100,
            current_stage=f'✅ Hoàn thành: {len(final_cases)} ca sau dedup',
        )
    except Exception as exc:
        logger.exception('Pipeline job %s failed', job_id)
        await _update_job(
            db,
            job_id,
            status=PipelineJobStatusEnum.failed,
            error_message=str(exc),
            current_stage='Pipeline thất bại',
        )


async def run_pipeline(job_id: str, post_url: str, db: AsyncSession | None = None) -> None:
    if db is not None:
        await _run_pipeline_with_session(job_id, post_url, db)
        return

    async with async_session_maker() as session:
        await _run_pipeline_with_session(job_id, post_url, session)
