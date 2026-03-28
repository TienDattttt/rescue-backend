from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from typing import Any


def _normalize_text(text: str) -> str:
    return ' '.join((text or '').split()).strip().lower()


def _safe_timestamp(value: Any) -> tuple[int, str]:
    if not value:
        return (1, '')
    text = str(value)
    try:
        return (0, datetime.fromisoformat(text.replace('Z', '+00:00')).isoformat())
    except ValueError:
        return (0, text)


def _pick_better_case(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_reactions = int(left.get('_reaction_count') or 0)
    right_reactions = int(right.get('_reaction_count') or 0)
    if left_reactions != right_reactions:
        return left if left_reactions > right_reactions else right

    left_ts = _safe_timestamp(left.get('_timestamp'))
    right_ts = _safe_timestamp(right.get('_timestamp'))
    if left_ts != right_ts:
        return left if left_ts < right_ts else right

    left_conf = float(left.get('ai_confidence') or 0.0)
    right_conf = float(right.get('ai_confidence') or 0.0)
    return left if left_conf >= right_conf else right


def stage4_dedup(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not cases:
        return []

    exact_map: dict[str, dict[str, Any]] = {}
    for case in cases:
        key = _normalize_text(case.get('raw_comment', ''))
        if not key:
            continue
        if key not in exact_map:
            exact_map[key] = case
        else:
            exact_map[key] = _pick_better_case(exact_map[key], case)

    deduped = list(exact_map.values())
    final_cases: list[dict[str, Any]] = []
    for candidate in deduped:
        is_duplicate = False
        for index, existing in enumerate(final_cases):
            similarity = SequenceMatcher(
                None,
                _normalize_text(candidate.get('raw_comment', '')),
                _normalize_text(existing.get('raw_comment', '')),
            ).ratio()
            if similarity > 0.85:
                final_cases[index] = _pick_better_case(existing, candidate)
                is_duplicate = True
                break
        if not is_duplicate:
            final_cases.append(candidate)
    return final_cases
