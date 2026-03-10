"""Auto-comment functionality for Xiaohongshu notes."""

import time

from playwright.sync_api import Page

from actions import auth
from core import navigator as nav
from utils import timing
from utils.log import get_logger

log = get_logger("comment")

# Retry: 1 retry with 10s backoff (comments are more sensitive)
_COMMENT_RETRY_BACKOFF = [10]


def post_comment(
    page: Page,
    url: str,
    text: str,
) -> dict:
    """Post a comment on a Xiaohongshu note, with retry on failure.

    Args:
        page: Browser page (must be logged in).
        url: Full note URL.
        text: Comment text.

    Returns dict with status.
    """
    if not text.strip():
        raise ValueError("Comment text cannot be empty")

    last_result = None
    for attempt in range(len(_COMMENT_RETRY_BACKOFF) + 1):
        result = _post_comment_once(page, url, text)
        if result.get("status") != "error":
            return result
        last_result = result
        if attempt < len(_COMMENT_RETRY_BACKOFF):
            backoff = _COMMENT_RETRY_BACKOFF[attempt]
            log.warning(f"Comment attempt {attempt + 1} failed ({result.get('message', '')}), retrying in {backoff}s...")
            time.sleep(backoff)
    return last_result


def _post_comment_once(
    page: Page,
    url: str,
    text: str,
) -> dict:
    """Single attempt to post a comment (no retry)."""
    log.info(f"Posting comment on {url}")

    # Navigate to the note
    nav.goto(page, url)

    # Check for security redirect — may indicate session expiry
    if nav.is_security_blocked(page):
        log.warning(f"Note blocked by XHS security (URL: {page.url})")

        if not auth.verify_session_live(page):
            log.info("Session expired — triggering re-login...")
            auth.invalidate_cache()
            if auth.login_qr(page):
                nav.goto(page, url)
                if not nav.is_security_blocked(page):
                    log.info("Retry after re-login succeeded")
                else:
                    return {"status": "error", "message": "重新登录后笔记仍无法访问", "url": url}
            else:
                return {"status": "error", "message": "会话已过期，重新登录失败", "url": url}
        else:
            return {"status": "error", "message": "笔记无法访问（安全验证失败）", "url": url}

    timing.action_pause(2000, 3000)

    # Find comment input area
    comment_input = page.locator(
        '[placeholder*="评论"], [placeholder*="说点什么"], '
        '[class*="comment"] [contenteditable], '
        '[class*="comment"] input, [class*="comment"] textarea'
    )

    if comment_input.count() == 0:
        # Try scrolling down to find comment section
        nav.scroll_down(page, 500)
        timing.human_delay(1000, 2000)
        comment_input = page.locator(
            '[placeholder*="评论"], [placeholder*="说点什么"], '
            '[class*="comment"] [contenteditable]'
        )

    if comment_input.count() == 0:
        raise RuntimeError("Comment input not found on page")

    # Click to focus
    comment_input.first.click()
    timing.human_delay(500, 1000)

    # Type comment character by character
    for ch in text:
        page.keyboard.type(ch, delay=0)
        timing.typing_delay(base_ms=100)

    timing.action_pause(800, 1500)

    # Find and click submit button
    submit_btn = page.locator(
        'button:has-text("发送"), button:has-text("发布"), '
        '[class*="comment"] button[class*="submit"], '
        '[class*="comment"] [class*="send"]'
    )

    if submit_btn.count() == 0:
        # Try pressing Enter as fallback
        page.keyboard.press("Enter")
        timing.human_delay(1000, 2000)
    else:
        submit_btn.first.click()
        timing.human_delay(1000, 2000)

    log.info("Comment submitted")

    # Check for success/error
    error_el = page.locator('[class*="error"], [class*="toast"][class*="fail"]')
    if error_el.count() > 0:
        error_msg = error_el.first.text_content() or "Unknown error"
        return {"status": "error", "message": error_msg}

    return {"status": "success", "url": url, "comment": text}
