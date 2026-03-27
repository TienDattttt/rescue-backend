import json
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GRAPHQL = "https://www.facebook.com/api/graphql/"

# Base headers for all requests
BASE_HEADERS = {
    "user-agent": "Mozilla/5.0",
    "content-type": "application/x-www-form-urlencoded"
}

# Get proxy configuration
PROXY = os.getenv("PROXY")
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None

# FB_DTSG token (set by UI when provided)
FB_DTSG = ""

# Optional response dump for investigating pagination mismatches.
DEBUG_COMMENT_RESPONSES = os.getenv("DEBUG_COMMENT_RESPONSES", "").strip().lower() in {"1", "true", "yes", "on"}
DEBUG_COMMENT_DIR = os.getenv("DEBUG_COMMENT_DIR", "debug_comment_responses")

COMMENT_QUERY_STRATEGIES = [
    {
        "name": "dedicated_reverse",
        "doc_id": "25550760954572974",
        "friendly_name": "CommentsListComponentsPaginationQuery",
        "variables": {
            "commentsAfterCount": -1,
            "commentsAfterCursor": None,
            "commentsIntentToken": "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1",
            "feedLocation": "DEDICATED_COMMENTING_SURFACE",
            "focusCommentID": None,
            "scale": 2,
            "useDefaultActor": False
        }
    },
    {
        "name": "permalink_ranked",
        "doc_id": "7353244678054869",
        "friendly_name": "CommentsListComponentsPaginationQuery",
        "variables": {
            "commentsBeforeCount": None,
            "commentsBeforeCursor": None,
            "commentsIntentToken": "RANKED_UNFILTERED_CHRONOLOGICAL_REPLIES_INTENT_V1",
            "feedLocation": "PERMALINK",
            "focusCommentID": None,
            "scale": 1,
            "useDefaultActor": False
        }
    }
]

if PROXY:
    print(f"Using proxy: {PROXY}")


# ========= RETRY HELPER =========
def retry_request(url, headers, data, proxies, cookies=None, max_retries=5):
    """Make a POST request with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, data=data, proxies=proxies, cookies=cookies, timeout=30)
            if response.status_code == 200:
                return response
            print(f"  Warning attempt {attempt}/{max_retries}: status {response.status_code}")
        except Exception as exc:
            print(f"  Warning attempt {attempt}/{max_retries}: {exc}")

        if attempt < max_retries:
            wait_time = attempt * 2
            print(f"  Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

    raise Exception(f"Failed after {max_retries} attempts")


# ===== PAYLOADS =====
def comments_payload(feedback_id, strategy, cursor=None, cookies=None):
    # Extract user ID from cookies if available
    user_id = "0"
    if cookies and "c_user" in cookies:
        user_id = cookies["c_user"]

    variables = dict(strategy["variables"])
    if "commentsAfterCursor" in variables:
        variables["commentsAfterCursor"] = cursor
    if "commentsBeforeCursor" in variables:
        variables["commentsBeforeCursor"] = cursor
    variables["id"] = feedback_id

    return {
        "av": user_id,
        "__user": user_id,
        "__a": "1",
        "fb_dtsg": FB_DTSG if FB_DTSG else "",
        "doc_id": strategy["doc_id"],
        "variables": json.dumps(variables)
    }


def replies_payload(comment_feedback_id, expansion_token, cursor=None, cookies=None):
    # Extract user ID from cookies if available
    user_id = "0"
    if cookies and "c_user" in cookies:
        user_id = cookies["c_user"]

    variables = {
        "clientKey": None,
        "expansionToken": expansion_token,
        "feedLocation": "POST_PERMALINK_DIALOG",
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": comment_feedback_id
    }

    # Facebook has changed the cursor variable name across reply queries.
    # Sending several likely candidates keeps the request tolerant to schema drift.
    if cursor:
        variables.update({
            "cursor": cursor,
            "after": cursor,
            "afterCursor": cursor,
            "commentsAfterCursor": cursor
        })

    return {
        "av": user_id,
        "__user": user_id,
        "__a": "1",
        "fb_dtsg": FB_DTSG if FB_DTSG else "",
        "doc_id": "26570577339199586",
        "variables": json.dumps(variables)
    }


# ===== HELPERS =====
def fb_json(response_text):
    """
    Facebook GraphQL sometimes returns:
    for (;;);
    {json}
    {json}

    This extracts the first valid JSON object safely.
    """
    text = response_text.strip()

    if text.startswith("for (;;);"):
        text = text[len("for (;;);"):]

    first = text.split("\n")[0].strip()
    return json.loads(first)


def _save_debug_response(prefix, response_index, response_json):
    if not DEBUG_COMMENT_RESPONSES:
        return

    os.makedirs(DEBUG_COMMENT_DIR, exist_ok=True)
    output_path = os.path.join(DEBUG_COMMENT_DIR, f"{prefix}_{response_index}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(response_json, f, ensure_ascii=False, indent=2)


def _get_path(data, *path):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _first_non_empty(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _find_first_value(data, keys):
    stack = [data]
    seen = set()

    while stack:
        current = stack.pop()
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)

        if isinstance(current, dict):
            for key in keys:
                value = current.get(key)
                if value not in (None, "", [], {}):
                    return value
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))

    return None


def _normalize_timestamp(raw_value):
    if raw_value in (None, "", [], {}):
        return None

    if isinstance(raw_value, dict):
        raw_value = _first_non_empty(
            raw_value.get("time"),
            raw_value.get("created_time"),
            raw_value.get("publish_time"),
            raw_value.get("text"),
            raw_value.get("localized_text")
        )

    if raw_value in (None, "", [], {}):
        return None

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if not raw_value:
            return None
        if raw_value.isdigit():
            raw_value = int(raw_value)
        else:
            return raw_value

    if isinstance(raw_value, (int, float)):
        timestamp_value = float(raw_value)
        if timestamp_value > 1_000_000_000_000:
            timestamp_value /= 1000
        try:
            return datetime.fromtimestamp(timestamp_value, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(raw_value)

    return str(raw_value)


def _extract_author(node):
    author = _first_non_empty(
        node.get("author"),
        _find_first_value(node, ["author"])
    )

    if isinstance(author, dict):
        return _first_non_empty(
            author.get("name"),
            _get_path(author, "name", "text"),
            _find_first_value(author, ["text"])
        )

    if isinstance(author, str):
        author = author.strip()
        return author or None

    return None


def _extract_timestamp(node):
    candidates = [
        node.get("created_time"),
        node.get("timestamp"),
        node.get("publish_time"),
        _get_path(node, "comment_action_links_renderer", "comment", "timestamp"),
        _get_path(node, "comment_action_links_renderer", "comment", "timestamp_renderer", "timestamp"),
        _find_first_value(node, ["created_time", "timestamp", "publish_time"])
    ]

    for candidate in candidates:
        normalized = _normalize_timestamp(candidate)
        if normalized:
            return normalized

    return None


def _extract_reaction_count(feedback):
    reactors = feedback.get("reactors", {}) if isinstance(feedback, dict) else {}
    return str(reactors.get("count_reduced", "0"))


def _extract_expansion_token(feedback):
    if not isinstance(feedback, dict):
        return None

    return _first_non_empty(
        _get_path(feedback, "expansion_info", "expansion_token"),
        _find_first_value(feedback, ["expansion_token"])
    )


def _build_comment_record(node, feedback, include_internal=False):
    record = {
        "author": _extract_author(node),
        "timestamp": _extract_timestamp(node),
        "text": (node.get("body") or {}).get("text", ""),
        "reaction_count": _extract_reaction_count(feedback)
    }

    if include_internal:
        feedback_id = feedback.get("id") if isinstance(feedback, dict) else None
        if feedback_id:
            record["_feedback_id"] = feedback_id

        expansion_token = _extract_expansion_token(feedback)
        if expansion_token:
            record["_expansion_token"] = expansion_token

    return record


def _extract_post_info(comment_node, comments_block):
    parent_post_story = comment_node.get("parent_post_story", {})
    if not parent_post_story:
        return {}

    post_info = {
        "post_story_id": parent_post_story.get("id"),
        "media_id": None
    }

    total_count = comments_block.get("total_count")
    if total_count is not None:
        post_info["graphql_top_level_comment_count"] = total_count

    attachments = parent_post_story.get("attachments", [])
    for attachment in attachments:
        media = attachment.get("media", {})
        if media and media.get("id"):
            post_info["media_id"] = media.get("id")
            break

    return post_info


def _looks_like_comment_node(node):
    if not isinstance(node, dict):
        return False

    has_feedback = isinstance(node.get("feedback"), dict)
    has_body = isinstance(node.get("body"), dict) or "body" in node
    has_author = "author" in node or _find_first_value(node, ["author"]) is not None
    return has_feedback and (has_body or has_author)


def _extract_comments_block(parsed):
    preferred_paths = [
        ("data", "node", "comment_rendering_instance_for_feed_location", "comments"),
        ("data", "node", "comment_rendering_instance", "comments"),
        ("data", "node", "feedback", "comment_rendering_instance", "comments"),
        ("data", "node", "feedback", "display_comments", "comments")
    ]

    for path in preferred_paths:
        candidate = _get_path(parsed, *path)
        if isinstance(candidate, dict) and isinstance(candidate.get("edges"), list):
            return candidate

    stack = [parsed]
    seen = set()

    while stack:
        current = stack.pop()
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)

        if isinstance(current, dict):
            edges = current.get("edges")
            if isinstance(edges, list) and edges:
                first_edge = edges[0]
                if isinstance(first_edge, dict) and _looks_like_comment_node(first_edge.get("node")):
                    return current
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))

    return {}


def _fetch_comments_for_strategy(feedback_id, strategy, cookies=None):
    headers = {**BASE_HEADERS, "x-fb-friendly-name": strategy["friendly_name"]}
    results = []
    cursor = None
    response_count = 0
    post_info = None
    seen_feedback_ids = set()
    seen_cursors = set()

    while True:
        response = retry_request(
            GRAPHQL,
            headers,
            comments_payload(feedback_id, strategy, cursor, cookies),
            PROXIES,
            cookies=cookies
        )
        parsed = fb_json(response.text)

        response_count += 1
        _save_debug_response(f"comments_{strategy['name']}", response_count, parsed)

        comments_block = _extract_comments_block(parsed)
        edges = comments_block.get("edges", [])
        if not edges:
            break

        for edge in edges:
            comment_node = edge["node"]
            feedback = comment_node.get("feedback", {})
            feedback_item_id = feedback.get("id")

            if feedback_item_id and feedback_item_id in seen_feedback_ids:
                continue
            if feedback_item_id:
                seen_feedback_ids.add(feedback_item_id)

            if response_count == 1 and post_info is None:
                post_info = _extract_post_info(comment_node, comments_block) or None
                if post_info:
                    print(f"Extracted post info from {strategy['name']}: {post_info}")

            results.append(_build_comment_record(comment_node, feedback, include_internal=True))

        page_info = comments_block.get("page_info", {})
        next_cursor = page_info.get("end_cursor")
        has_next_page = page_info.get("has_next_page")
        if not next_cursor or next_cursor in seen_cursors or has_next_page is False:
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return results, post_info, response_count


# ===== FETCH COMMENTS =====
def fetch_comments(feedback_id, cookies=None):
    results = []
    post_info = None
    seen_feedback_ids = set()
    strategy_stats = []

    for strategy in COMMENT_QUERY_STRATEGIES:
        strategy_results, strategy_post_info, response_count = _fetch_comments_for_strategy(
            feedback_id,
            strategy,
            cookies=cookies
        )
        strategy_unique = 0
        for comment in strategy_results:
            feedback_item_id = comment.get("_feedback_id")
            if feedback_item_id and feedback_item_id in seen_feedback_ids:
                continue
            if feedback_item_id:
                seen_feedback_ids.add(feedback_item_id)
            results.append(comment)
            strategy_unique += 1

        strategy_stats.append({
            "strategy": strategy["name"],
            "fetched_comments": len(strategy_results),
            "unique_comments_added": strategy_unique,
            "response_pages": response_count
        })

        if strategy_post_info and post_info is None:
            post_info = strategy_post_info

    if post_info is None:
        post_info = {}
    post_info["comment_query_stats"] = strategy_stats

    return results, post_info


# ===== FETCH REPLIES =====
def fetch_replies(comment, cookies=None):
    feedback_id = comment.get("_feedback_id")
    expansion_token = comment.get("_expansion_token")
    if not feedback_id or not expansion_token:
        return []

    headers = {**BASE_HEADERS, "x-fb-friendly-name": "Depth1CommentsListPaginationQuery"}
    replies = []
    cursor = None
    response_count = 0
    seen_reply_keys = set()
    seen_cursors = set()

    while True:
        response = retry_request(
            GRAPHQL,
            headers,
            replies_payload(feedback_id, expansion_token, cursor, cookies),
            PROXIES,
            cookies=cookies
        )

        parsed = fb_json(response.text)
        response_count += 1
        _save_debug_response(f"replies_{feedback_id}", response_count, parsed)

        replies_connection = (
            parsed.get("data", {})
            .get("node", {})
            .get("replies_connection", {})
        )
        edges = replies_connection.get("edges", [])
        if not edges:
            break

        new_items = 0
        for edge in edges:
            reply_node = edge["node"]
            feedback = reply_node.get("feedback", {})
            reply_record = _build_comment_record(reply_node, feedback)
            dedupe_key = (
                reply_record.get("author"),
                reply_record.get("timestamp"),
                reply_record.get("text"),
                reply_record.get("reaction_count")
            )
            if dedupe_key in seen_reply_keys:
                continue

            seen_reply_keys.add(dedupe_key)
            replies.append(reply_record)
            new_items += 1

        page_info = replies_connection.get("page_info", {})
        next_cursor = page_info.get("end_cursor")
        has_next_page = page_info.get("has_next_page", False)

        if new_items == 0 or not has_next_page or not next_cursor or next_cursor in seen_cursors:
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

        next_token = _extract_expansion_token(_get_path(parsed, "data", "node", "feedback"))
        if next_token:
            expansion_token = next_token

    return replies


# ===== RUN =====
if __name__ == "__main__":
    POST_FEEDBACK_ID = "ZmVlZGJhY2s6MTg3NDE2NTYxMzI0NjAwMw=="
    POST_ID = "1420269302790428"

    comments, post_info = fetch_comments(POST_FEEDBACK_ID)

    output = {
        "post_info": post_info,
        "comments": []
    }

    for comment in comments:
        comment["replies"] = fetch_replies(comment)
        output["comments"].append(comment)

    os.makedirs(f"simple_post/{POST_ID}", exist_ok=True)

    output_file = f"simple_post/{POST_ID}/{POST_ID}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_file}")
