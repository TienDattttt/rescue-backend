from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PHOBERT_SERVICE_URL = os.getenv('PHOBERT_SERVICE_URL', 'http://localhost:7860')
CLASSIFY_TIMEOUT = 120


async def stage2_classify(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Gọi PhoBERT inference service qua HTTP.
    Chỉ giữ lại comments có is_sos=True.
    """
    if not comments:
        return []

    texts = [str(comment.get('text') or '') for comment in comments]
    threshold = float(os.getenv('CLASSIFIER_THRESHOLD', '0.4'))

    logger.info('Gửi %s comments đến PhoBERT service...', len(texts))

    try:
        async with httpx.AsyncClient(timeout=CLASSIFY_TIMEOUT) as client:
            response = await client.post(
                f'{PHOBERT_SERVICE_URL}/classify',
                json={'texts': texts, 'threshold': threshold},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        logger.error('PhoBERT service timeout')
        raise RuntimeError('PhoBERT service không phản hồi') from exc
    except httpx.HTTPError as exc:
        logger.error('PhoBERT service lỗi: %s', exc)
        raise RuntimeError(f'PhoBERT service lỗi: {exc}') from exc

    predictions = payload.get('predictions') or []
    sos_comments: list[dict[str, Any]] = []

    for comment, prediction in zip(comments, predictions):
        if not prediction.get('is_sos'):
            continue
        enriched = dict(comment)
        enriched['ai_confidence'] = float(prediction.get('confidence') or 0.0)
        sos_comments.append(enriched)

    logger.info('Stage 2 xong: %s/%s comments cầu cứu', len(sos_comments), len(comments))
    return sos_comments