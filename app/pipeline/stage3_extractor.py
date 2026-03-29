from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from app.services.extractor_service import get_extractor_service


async def stage3_extract(sos_comments: list[dict[str, Any]], job_id: str) -> list[dict[str, Any]]:
    if not sos_comments:
        return []

    extractor = get_extractor_service()
    loop = asyncio.get_running_loop()
    extracted = await loop.run_in_executor(None, partial(extractor.extract_batch, sos_comments, str(job_id)))

    extracted_cases: list[dict[str, Any]] = []
    for comment, item in zip(sos_comments, extracted):
        extracted_cases.append(
            {
                'source_post_id': comment.get('post_id', ''),
                'raw_comment': comment.get('text', ''),
                'commenter_name': comment.get('author'),
                'severity': item.get('severity', 'MEDIUM'),
                'location_description': item.get('locationDescription'),
                'ward_commune': item.get('wardCommune'),
                'district_extracted': item.get('district'),
                'province': item.get('province'),
                'normalized_address': None,
                'district': '',
                'lat': item.get('lat'),
                'lng': item.get('lng'),
                'num_people': item.get('numPeople'),
                'vulnerable_groups': item.get('vulnerableGroups') or [],
                'accessibility': item.get('accessibility'),
                'waiting_hours': item.get('waitingHours'),
                'phone': item.get('phone'),
                'ai_confidence': comment.get('ai_confidence'),
                'llm_confidence': None,
                'geocode_status': 'pending',
                'rescue_status': 'waiting',
                'current_score': None,
                'current_rank': None,
                '_comment_id': comment.get('id'),
                '_reaction_count': comment.get('reaction_count', 0),
                '_timestamp': comment.get('timestamp'),
            }
        )
    return extracted_cases