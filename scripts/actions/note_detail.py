"""Fetch detailed information about a specific Xiaohongshu note."""

import json
import random
import re
import time

from playwright.sync_api import Page

from actions import auth
from core import navigator as nav
from utils import timing
from utils.log import get_logger

log = get_logger("note_detail")

# Rate limiting between consecutive detail calls
_last_detail_time = 0
_MIN_INTERVAL_S = 3
_MAX_INTERVAL_S = 8

# Retry with exponential backoff
_RETRY_BACKOFF = [5, 12, 25]


def get_detail(page: Page, url: str, xsec_token: str = "") -> dict:
    """Fetch full details of a note by URL, with rate limiting and retry.

    Args:
        page: Browser page (must be logged in).
        url: Full Xiaohongshu note URL (e.g. https://www.xiaohongshu.com/explore/xxxxx).
        xsec_token: Optional xsec_token for authentication.

    Returns dict with note details.
    """
    global _last_detail_time

    # Rate limiting: ensure minimum interval between consecutive calls
    elapsed = time.time() - _last_detail_time
    wait = random.uniform(_MIN_INTERVAL_S, _MAX_INTERVAL_S)
    if elapsed < wait:
        sleep_time = wait - elapsed
        log.debug(f"Rate limiting: waiting {sleep_time:.1f}s before next detail call")
        time.sleep(sleep_time)
    _last_detail_time = time.time()

    # Retry loop with exponential backoff
    last_result = None
    for attempt in range(len(_RETRY_BACKOFF) + 1):
        result = _get_detail_once(page, url, xsec_token)
        if "error" not in result:
            return result
        last_result = result
        if attempt < len(_RETRY_BACKOFF):
            backoff = _RETRY_BACKOFF[attempt]
            log.warning(f"Detail attempt {attempt + 1} failed ({result.get('error', '')}), retrying in {backoff}s...")
            time.sleep(backoff)
    return last_result


def _get_detail_once(page: Page, url: str, xsec_token: str = "") -> dict:
    """Single attempt to fetch note details (no retry)."""
    log.info(f"Fetching note detail: {url}")

    # Append xsec_token if provided and not already in URL
    if xsec_token and "xsec_token" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}xsec_token={xsec_token}"

    nav.goto(page, url)

    # Check for security redirect — may indicate session expiry
    if nav.is_security_blocked(page):
        log.warning(f"Note blocked by XHS security (URL: {page.url})")

        # Verify if the real cause is an expired session
        if not auth.verify_session_live(page):
            log.info("Session expired — triggering re-login...")
            auth.invalidate_cache()
            if auth.login_qr(page):
                # Retry navigation after re-login
                nav.goto(page, url)
                if not nav.is_security_blocked(page):
                    log.info("Retry after re-login succeeded")
                    # Fall through to normal extraction below
                else:
                    return {"error": "重新登录后笔记仍无法浏览（可能已被删除或设为私密）", "url": url}
            else:
                return {"error": "会话已过期，重新登录失败", "url": url}
        else:
            # Session is fine — the note itself is truly inaccessible
            return {"error": "当前笔记暂时无法浏览（可能已被删除、设为私密，或 xsec_token 缺失/过期）", "url": url}

    # Wait for note content to render (async-loaded page)
    try:
        page.wait_for_selector('#noteContainer, [class*="note-detail"], [class*="note-container"], [id="noteContainer"]', timeout=10000)
    except Exception:
        log.debug("Timed out waiting for note container selector")

    timing.action_pause(3000, 5000)

    # Try __INITIAL_STATE__ first, with retry for async loading
    detail = _extract_from_state_with_retry(page)
    if detail:
        return detail

    # Fallback: DOM extraction
    return _extract_from_dom(page, url)


def _extract_from_state_with_retry(page: Page, max_retries: int = 3) -> dict | None:
    """Try extracting from state multiple times, waiting for async data."""
    for attempt in range(max_retries):
        detail = _extract_from_state(page)
        if detail and detail.get("title"):
            return detail
        if attempt < max_retries - 1:
            log.debug(f"State extraction attempt {attempt + 1} got empty data, retrying...")
            time.sleep(2)
    return None


def _extract_from_state(page: Page) -> dict | None:
    """Extract note detail from window.__INITIAL_STATE__."""
    try:
        raw = page.evaluate("""
            () => {
                const state = window.__INITIAL_STATE__;
                if (!state) return null;
                const noteMap = state.note?.noteDetailMap || state.note?.detail || {};
                const entries = Object.values(noteMap);
                if (entries.length === 0) return null;

                const entry = entries[0];
                const note = entry?.note;

                // Check if note data is actually populated
                if (!note || Object.keys(note).length === 0) return null;

                try {
                    return JSON.stringify(entry, (key, value) => {
                        if (typeof value === 'function') return undefined;
                        if (value instanceof Element) return undefined;
                        return value;
                    });
                } catch(e) {
                    return null;
                }
            }
        """)
        if not raw:
            return None

        data = json.loads(raw)
        note = data.get("note") or data

        user = note.get("user") or {}
        interact = note.get("interactInfo") or {}
        image_list = note.get("imageList") or []

        images = []
        for img in image_list:
            img_url = img.get("urlDefault") or img.get("url") or ""
            if img_url:
                images.append(img_url)

        return {
            "id": note.get("noteId") or note.get("id", ""),
            "title": note.get("title", ""),
            "content": note.get("desc", ""),
            "author": user.get("nickname", ""),
            "author_id": user.get("userId", ""),
            "type": note.get("type", ""),
            "likes": interact.get("likedCount", 0),
            "collects": interact.get("collectedCount", 0),
            "comments": interact.get("commentCount", 0),
            "shares": interact.get("shareCount", 0),
            "images": images,
            "video_url": note.get("video", {}).get("url", ""),
            "tags": [t.get("name", "") for t in note.get("tagList") or []],
            "publish_time": note.get("time", ""),
            "ip_location": note.get("ipLocation", ""),
        }

    except Exception as e:
        log.debug(f"State extraction failed: {e}")
        return None


def _extract_from_dom(page: Page, url: str) -> dict:
    """Fallback: extract note detail from visible DOM elements."""
    result: dict = {"url": url}

    # Extract note ID from URL
    match = re.search(r"/explore/([a-f0-9]+)", url)
    if match:
        result["id"] = match.group(1)

    # Title — try specific XHS selectors first, then generic
    for selector in ['#detail-title', '[class*="title"]', 'h1']:
        title_el = page.locator(selector)
        if title_el.count() > 0:
            text = (title_el.first.text_content() or "").strip()
            if text:
                result["title"] = text
                break

    # Content/description — try note-specific selectors
    for selector in ['[id="detail-desc"]', '[class*="desc"]', '[class*="note-text"]',
                     '[class*="content"]']:
        content_el = page.locator(selector)
        if content_el.count() > 0:
            text = (content_el.first.text_content() or "").strip()
            if text:
                result["content"] = text
                break

    # Author
    for selector in ['[class*="username"]', '[class*="author"] [class*="name"]',
                     '[class*="nickname"]', '[class*="user-name"]']:
        author_el = page.locator(selector)
        if author_el.count() > 0:
            text = (author_el.first.text_content() or "").strip()
            if text:
                result["author"] = text
                break

    # Interaction counts — look for like/collect/comment spans
    for metric, keywords in [
        ("likes", ["like", "赞"]),
        ("collects", ["collect", "收藏"]),
        ("comments", ["comment", "评论"]),
    ]:
        for kw in keywords:
            el = page.locator(f'[class*="{kw}"] [class*="count"], [class*="{kw}"] span')
            if el.count() > 0:
                result[metric] = (el.first.text_content() or "").strip()
                break

    # Images
    img_els = page.locator('[class*="slide"] img, [class*="carousel"] img, '
                           '[class*="note-image"] img').all()
    result["images"] = [img.get_attribute("src") or "" for img in img_els if img.get_attribute("src")]

    return result
