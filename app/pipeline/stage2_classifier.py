from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PHOBERT_SERVICE_URL = os.getenv('PHOBERT_SERVICE_URL', 'http://localhost:7860')
CLASSIFY_TIMEOUT = 120
CHUNK_SIZE = 50


async def stage2_classify(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Goi PhoBERT inference service qua HTTP theo nhieu chunk nho.
    Chi giu lai comments co is_sos=True.
    """
    if not comments:
        return []

    threshold = float(os.getenv('CLASSIFIER_THRESHOLD', '0.4'))
    texts = [str(comment.get('text') or '') for comment in comments]

    logger.info('Stage 2: %s comments, chunk_size=%s', len(texts), CHUNK_SIZE)

    all_predictions: list[dict[str, Any]] = []
    total_chunks = (len(texts) + CHUNK_SIZE - 1) // CHUNK_SIZE

    async with httpx.AsyncClient(timeout=CLASSIFY_TIMEOUT) as client:
        for index in range(0, len(texts), CHUNK_SIZE):
            chunk_texts = texts[index:index + CHUNK_SIZE]
            chunk_num = index // CHUNK_SIZE + 1

            logger.info('Chunk %s/%s: %s texts', chunk_num, total_chunks, len(chunk_texts))

            try:
                response = await client.post(
                    f'{PHOBERT_SERVICE_URL}/classify',
                    json={'texts': chunk_texts, 'threshold': threshold},
                )
                response.raise_for_status()
                payload = response.json()
                all_predictions.extend(payload.get('predictions') or [])
            except httpx.TimeoutException as exc:
                logger.error('Chunk %s timeout', chunk_num)
                raise RuntimeError('PhoBERT service timeout') from exc
            except httpx.HTTPError as exc:
                logger.error('Chunk %s loi: %s', chunk_num, exc)
                raise RuntimeError(f'PhoBERT service loi: {exc}') from exc

    sos_comments: list[dict[str, Any]] = []
    for comment, prediction in zip(comments, all_predictions):
        if not prediction.get('is_sos'):
            continue
        enriched = dict(comment)
        enriched['ai_confidence'] = float(prediction.get('confidence') or 0.0)
        sos_comments.append(enriched)

    logger.info('Stage 2 xong: %s/%s cau cuu', len(sos_comments), len(comments))
    return sos_comments
