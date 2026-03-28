from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.monitored_post import MonitoredPost
from app.models.rescue_case import RescueCase
from app.schemas.dashboard import MonitoredPostOut

router = APIRouter(prefix='')


async def fetch_monitored_posts(db: AsyncSession) -> list[MonitoredPostOut | MonitoredPost]:
    result = await db.execute(select(MonitoredPost).order_by(MonitoredPost.last_sync_at.desc()))
    posts = list(result.scalars().all())
    if posts:
        return posts

    case_result = await db.execute(select(RescueCase).order_by(RescueCase.created_at.desc()))
    cases = list(case_result.scalars().all())
    grouped: dict[str, dict] = defaultdict(lambda: {'commentVolume': 0, 'districtScope': set(), 'lastSyncAt': None})
    for case in cases:
        bucket = grouped[case.source_post_id]
        bucket['commentVolume'] += 1
        if case.district:
            bucket['districtScope'].add(case.district)
        if bucket['lastSyncAt'] is None or case.created_at > bucket['lastSyncAt']:
            bucket['lastSyncAt'] = case.created_at

    fallback_posts: list[MonitoredPostOut] = []
    for post_id, bucket in grouped.items():
        last_sync = bucket['lastSyncAt'] or datetime.now(timezone.utc)
        fallback_posts.append(
            MonitoredPostOut(
                id=post_id,
                title=f'Facebook post {post_id}',
                sourceName='Facebook',
                syncStatus='live',
                commentVolume=bucket['commentVolume'],
                lastSyncAt=last_sync.isoformat(),
                districtScope=sorted(bucket['districtScope']),
            )
        )
    return sorted(fallback_posts, key=lambda item: item.lastSyncAt, reverse=True)


@router.get('/posts', response_model=list[MonitoredPostOut])
async def list_posts(db: AsyncSession = Depends(get_db)) -> list[MonitoredPostOut | MonitoredPost]:
    return await fetch_monitored_posts(db)
