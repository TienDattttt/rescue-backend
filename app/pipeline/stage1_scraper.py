from __future__ import annotations

import asyncio
import base64
import re
from html import unescape
from typing import Any

import requests

from scraper.comment_scraper import fetch_comments, fetch_replies

URL_PATTERN = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)
POST_ID_PATTERNS = [
    r'/groups/[^/]+/posts/(\d+)',
    r'/posts/(\d+)',
    r'story_fbid=(\d+)',
    r'fbid=(\d+)',
]


def _is_effectively_empty(text: str) -> bool:
    if not text or not text.strip():
        return True
    without_urls = URL_PATTERN.sub(' ', text)
    without_symbols = re.sub(r'[\W_]+', '', without_urls, flags=re.UNICODE)
    return not without_symbols.strip()


def extract_post_id_from_url(url: str) -> str:
    for pattern in POST_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    html = response.text

    story_match = re.search(r'"storyID":"([^"]+)"', html)
    if story_match:
        try:
            story_id_decoded = base64.b64decode(story_match.group(1)).decode('utf-8')
            parts = story_id_decoded.split(':')
            if len(parts) >= 2 and parts[-1].isdigit():
                return parts[-1]
        except Exception:
            pass

    og_url_match = re.search(r'<meta property="og:url" content="([^"]+)"', html)
    if og_url_match:
        og_url = unescape(og_url_match.group(1))
        for pattern in POST_ID_PATTERNS:
            match = re.search(pattern, og_url)
            if match:
                return match.group(1)

    raise ValueError(f'Không thể trích xuất post_id từ URL: {url}')


def _parse_reaction_count(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _make_comment_id(post_id: str, source: str, indices: list[int]) -> str:
    suffix = '-'.join(f'{index:04d}' for index in indices)
    return f'{post_id}-{source}-{suffix}'


def _blocking_stage1_scrape(post_url: str) -> list[dict[str, Any]]:
    post_id = extract_post_id_from_url(post_url)
    feedback_id = base64.b64encode(f'feedback:{post_id}'.encode()).decode()
    comments, _post_info = fetch_comments(feedback_id)

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

        replies = fetch_replies(comment)
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
    return flattened


async def stage1_scrape(post_url: str) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _blocking_stage1_scrape, post_url)
