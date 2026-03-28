from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

import requests

from app.core.database import async_session_maker
from app.models.pipeline_job import PipelineJob, PipelineJobStatusEnum
from app.pipeline import orchestrator
from app.pipeline.stage1_scraper import _is_effectively_empty, _make_comment_id, _parse_reaction_count


def load_comments_from_json(json_file: str) -> tuple[str, list[dict[str, Any]]]:
    path = Path(json_file)
    payload = json.loads(path.read_text(encoding='utf-8'))
    post_id = str(payload.get('post_id') or path.stem)
    comments = payload.get('comments') or []

    flattened: list[dict[str, Any]] = []
    for top_index, comment in enumerate(comments, start=1):
        text = str(comment.get('text') or '')
        if not _is_effectively_empty(text):
            flattened.append(
                {
                    'id': _make_comment_id(post_id, 'top_level', [top_index]),
                    'text': text,
                    'author': comment.get('author'),
                    'timestamp': comment.get('timestamp'),
                    'reaction_count': _parse_reaction_count(comment.get('reaction_count')),
                    'source': 'top_level',
                    'parent_author': None,
                    'post_id': post_id,
                }
            )

        replies = comment.get('replies') or []
        for reply_index, reply in enumerate(replies, start=1):
            reply_text = str(reply.get('text') or '')
            if _is_effectively_empty(reply_text):
                continue
            flattened.append(
                {
                    'id': _make_comment_id(post_id, 'reply', [top_index, reply_index]),
                    'text': reply_text,
                    'author': reply.get('author'),
                    'timestamp': reply.get('timestamp'),
                    'reaction_count': _parse_reaction_count(reply.get('reaction_count')),
                    'source': 'reply',
                    'parent_author': comment.get('author'),
                    'post_id': post_id,
                }
            )
    return post_id, flattened


async def create_job(post_url: str, post_id: str) -> str:
    async with async_session_maker() as session:
        job = PipelineJob(
            post_url=post_url,
            post_id=post_id,
            status=PipelineJobStatusEnum.pending,
            progress=0,
            current_stage='Chuẩn bị chạy pipeline test từ file JSON',
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return str(job.id)


async def fetch_job(job_id: str) -> PipelineJob | None:
    async with async_session_maker() as session:
        return await session.get(PipelineJob, UUID(job_id))


async def poll_job(job_id: str, started_at: float) -> PipelineJob | None:
    last_snapshot: tuple[str, int, str | None] | None = None
    final_job: PipelineJob | None = None

    while True:
        job = await fetch_job(job_id)
        final_job = job
        if job is None:
            print('Pipeline job not found.')
            return None

        snapshot = (str(job.status), int(job.progress or 0), job.current_stage)
        if snapshot != last_snapshot:
            elapsed = int(time.time() - started_at)
            minutes, seconds = divmod(elapsed, 60)
            print(f'[{minutes:02d}:{seconds:02d}] {job.status:<13} | {int(job.progress or 0):3d}% | {job.current_stage or ""}')
            last_snapshot = snapshot

        if job.status in {PipelineJobStatusEnum.done, PipelineJobStatusEnum.failed}:
            return job
        await asyncio.sleep(3)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json-file', required=True)
    parser.add_argument('--api-base', default='http://localhost:8000')
    args = parser.parse_args()

    post_id, raw_comments = load_comments_from_json(args.json_file)
    print(f'Loaded {len(raw_comments)} normalized comments from {args.json_file}')

    post_url = 'file://test'
    job_id = await create_job(post_url=post_url, post_id=post_id)
    print(f'Created pipeline job: {job_id}')

    original_extract_post_id = orchestrator.extract_post_id_from_url
    original_stage1_scrape = orchestrator.stage1_scrape

    def fake_extract_post_id(_url: str) -> str:
        return post_id

    async def fake_stage1_scrape(_url: str) -> list[dict[str, Any]]:
        return list(raw_comments)

    orchestrator.extract_post_id_from_url = fake_extract_post_id
    orchestrator.stage1_scrape = fake_stage1_scrape

    started_at = time.time()
    task = asyncio.create_task(orchestrator.run_pipeline(job_id, post_url))
    try:
        final_job = await poll_job(job_id, started_at)
        await task
    finally:
        orchestrator.extract_post_id_from_url = original_extract_post_id
        orchestrator.stage1_scrape = original_stage1_scrape

    if final_job is None:
        raise SystemExit(1)

    print('\n=== FINAL JOB ===')
    print(f'  status: {final_job.status}')
    print(f'  progress: {final_job.progress}')
    print(f'  stage: {final_job.current_stage}')
    if final_job.error_message:
        print(f'  error: {final_job.error_message}')

    response = requests.get(f'{args.api_base}/cases', timeout=30)
    response.raise_for_status()
    cases = response.json()
    related_cases = [case for case in cases if case.get('sourcePostId') == post_id]

    print('\n=== CASE SUMMARY ===')
    print(f'Total cases for post {post_id}: {len(related_cases)}')
    severity_counts = Counter(case.get('severity') for case in related_cases)
    print(f'Severity breakdown: {dict(severity_counts)}')

    for case in related_cases:
        if not case.get('locationDescription') and case.get('lat') is None and case.get('lng') is None and not case.get('phone'):
            print(f"WARNING: sparse case -> {case.get('id')}")


if __name__ == '__main__':
    asyncio.run(main())