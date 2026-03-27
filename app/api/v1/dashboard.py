from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.posts import fetch_monitored_posts
from app.api.v1.presets import get_presets
from app.core.database import get_db
from app.models.pipeline_job import PipelineJob, PipelineJobStatusEnum
from app.models.rescue_case import GeocodeStatus, RescueCase, RescueStatus, SeverityLevel
from app.schemas.dashboard import DashboardOut, DashboardStatsOut, PipelineHealthOut
from app.schemas.rescue_case import RescueCaseOut

router = APIRouter(prefix='')


def _build_pipeline_health(latest_job: PipelineJob | None) -> PipelineHealthOut:
    if latest_job is None:
        return PipelineHealthOut(scraper='healthy', aiInference='healthy', geocoding='offline', realtime='degraded')
    if latest_job.status == PipelineJobStatusEnum.failed:
        stage = (latest_job.current_stage or '').lower()
        scraper = 'degraded' if 'crawl' in stage or 'scrap' in stage else 'healthy'
        ai = 'degraded' if any(keyword in stage for keyword in ['phân loại', 'trích xuất', 'extract']) else 'healthy'
        return PipelineHealthOut(scraper=scraper, aiInference=ai, geocoding='offline', realtime='degraded')
    return PipelineHealthOut(scraper='healthy', aiInference='healthy', geocoding='offline', realtime='degraded')


@router.get('/dashboard', response_model=DashboardOut)
async def get_dashboard(
    activePresetId: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> DashboardOut:
    del activePresetId

    total_incoming = int((await db.execute(select(func.count()).select_from(RescueCase))).scalar_one() or 0)
    waiting_cases = int(
        (await db.execute(select(func.count()).select_from(RescueCase).where(RescueCase.rescue_status == RescueStatus.waiting))).scalar_one()
        or 0
    )
    critical_count = int(
        (await db.execute(select(func.count()).select_from(RescueCase).where(RescueCase.severity == SeverityLevel.CRITICAL))).scalar_one()
        or 0
    )
    geocoded_count = int(
        (await db.execute(select(func.count()).select_from(RescueCase).where(RescueCase.geocode_status == GeocodeStatus.success))).scalar_one()
        or 0
    )
    active_posts = int((await db.execute(select(func.count(func.distinct(RescueCase.source_post_id))).select_from(RescueCase))).scalar_one() or 0)

    cases_result = await db.execute(
        select(RescueCase)
        .where(RescueCase.rescue_status != RescueStatus.false_alarm)
        .order_by(RescueCase.created_at.desc())
    )
    cases = list(cases_result.scalars().all())
    shortlisted_count = min(len(cases), 10)

    posts = await fetch_monitored_posts(db)

    latest_job_result = await db.execute(select(PipelineJob).order_by(PipelineJob.created_at.desc()).limit(1))
    latest_job = latest_job_result.scalars().first()

    last_sync = max((case.created_at for case in cases), default=datetime.now(timezone.utc))
    stats = DashboardStatsOut(
        totalIncomingCases=total_incoming,
        waitingCases=waiting_cases,
        criticalCount=critical_count,
        geocodedCount=geocoded_count,
        activePosts=active_posts,
        shortlistedCount=shortlisted_count,
        lastSyncAt=last_sync.isoformat(),
        currentPresetLabel='Mặc định',
        consistencyRatio=0.08,
    )
    pipeline_health = _build_pipeline_health(latest_job)

    return DashboardOut(
        stats=stats,
        cases=[RescueCaseOut.model_validate(case) for case in cases],
        posts=posts,
        events=[],
        pipelineStatus=pipeline_health,
        presets=get_presets(),
    )
