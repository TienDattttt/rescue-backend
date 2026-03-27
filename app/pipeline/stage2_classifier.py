from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from app.services.classifier_service import get_classifier_service


async def stage2_classify(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not comments:
        return []

    classifier = get_classifier_service()
    texts = [str(comment.get('text') or '') for comment in comments]
    loop = asyncio.get_running_loop()
    predictions = await loop.run_in_executor(None, partial(classifier.predict_batch, texts, 32))

    sos_comments: list[dict[str, Any]] = []
    for comment, prediction in zip(comments, predictions):
        if prediction.get('label') != 'cau_cuu':
            continue
        enriched = dict(comment)
        enriched['ai_confidence'] = float(prediction.get('confidence') or 0.0)
        sos_comments.append(enriched)
    return sos_comments
