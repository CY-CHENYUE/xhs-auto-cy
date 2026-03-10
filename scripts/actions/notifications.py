"""Notification and mention scraping for Xiaohongshu."""

import json

from playwright.sync_api import Page

from core import navigator as nav
from utils import timing
from utils.log import get_logger

log = get_logger("notifications")

# Maps CLI notification type to the state key used in notificationMap
_STATE_KEY_MAP = {
    "mentions": "mentions",
    "likes": "likes",
    "comments": "mentions",   # comments share the "评论和@" tab with mentions
    "follows": "connections",
}


def scrape(
    page: Page,
    notification_type: str = "mentions",
    limit: int = 50,
) -> dict:
    """Scrape notifications from Xiaohongshu.

    Args:
        page: Browser page (must be logged in).
        notification_type: Type of notification - "mentions", "likes", "comments", "follows".
        limit: Max number of notifications to collect.

    Returns dict with notification data.
    """
    log.info(f"Scraping notifications: type={notification_type}, limit={limit}")

    # Navigate to notification page
    nav.goto(page, nav.XHS_NOTIFICATION)
    timing.action_pause(2000, 3000)

    # Click on the correct tab — actual tab labels on the page:
    #   "评论和@"  |  "赞和收藏"  |  "新增关注"
    tab_text_map = {
        "mentions": ["评论和@"],
        "likes": ["赞和收藏"],
        "comments": ["评论和@"],
        "follows": ["新增关注"],
    }

    tab_texts = tab_text_map.get(notification_type, ["评论和@"])
    for tab_text in tab_texts:
        tab = page.locator(f'text="{tab_text}"')
        if tab.count() > 0:
            tab.first.click()
            timing.action_pause(1000, 2000)
            break

    # Try extracting from __INITIAL_STATE__
    notifications = _extract_from_state(page, notification_type, limit)
    if notifications:
        return {
            "type": notification_type,
            "count": len(notifications),
            "items": notifications,
        }

    # Fallback: extract from DOM
    items = _extract_from_dom(page, limit)
    return {
        "type": notification_type,
        "count": len(items),
        "items": items,
    }


def _extract_from_state(page: Page, notification_type: str, limit: int) -> list[dict] | None:
    """Extract notifications from window.__INITIAL_STATE__.notification.notificationMap."""
    state_key = _STATE_KEY_MAP.get(notification_type, "mentions")
    try:
        raw = page.evaluate("""(stateKey) => {
            const state = window.__INITIAL_STATE__;
            if (!state || !state.notification) return null;
            const unwrap = (v) => {
                if (v && v._rawValue !== undefined) return v._rawValue;
                if (v && v._value !== undefined) return v._value;
                return v;
            };
            const map = unwrap(state.notification.notificationMap);
            if (!map) return null;
            const bucket = unwrap(map[stateKey]);
            if (!bucket) return null;
            const msgList = unwrap(bucket.messageList);
            if (!Array.isArray(msgList) || msgList.length === 0) return null;
            return JSON.stringify(msgList);
        }""", state_key)
        if not raw:
            return None

        msg_list = json.loads(raw)
        results = []
        for item in msg_list[:limit]:
            user_info = item.get("userInfo") or {}
            item_info = item.get("itemInfo") or {}
            comment_info = item.get("commentInfo") or {}
            results.append({
                "id": item.get("id", ""),
                "type": item.get("type", ""),
                "title": item.get("title", ""),
                "user": user_info.get("nickname", ""),
                "user_id": user_info.get("userid", ""),
                "note_id": item_info.get("id", ""),
                "note_content": item_info.get("content", ""),
                "comment": comment_info.get("content", ""),
                "time": item.get("time", ""),
            })
        return results if results else None

    except Exception as e:
        log.debug(f"State extraction failed: {e}")
        return None


def _extract_from_dom(page: Page, limit: int) -> list[dict]:
    """Extract notification items from DOM.

    The notification page uses:
      .tabs-content-container > .container[note-id]
        .user-info a           — username
        .interaction-hint span — action description + time
        .quote-info            — quoted content (optional)
    """
    items = []

    cards = page.locator('.tabs-content-container > .container').all()

    for card in cards[:limit]:
        try:
            note_id = card.get_attribute("note-id") or ""

            user_el = card.locator('.user-info a')
            user = user_el.first.text_content() if user_el.count() > 0 else ""

            hint_spans = card.locator('.interaction-hint span').all()
            action = (hint_spans[0].text_content() or "").strip() if len(hint_spans) > 0 else ""
            time_str = (hint_spans[1].text_content() or "").strip() if len(hint_spans) > 1 else ""

            quote_el = card.locator('.quote-info')
            quote = quote_el.first.text_content() if quote_el.count() > 0 else ""

            items.append({
                "user": (user or "").strip(),
                "action": action,
                "note_id": note_id,
                "quote": (quote or "").strip(),
                "time": time_str,
            })
        except Exception:
            continue

    return items
