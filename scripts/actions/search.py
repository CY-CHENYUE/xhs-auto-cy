"""Xiaohongshu note search functionality."""

import json
import re
from urllib.parse import quote

from playwright.sync_api import Page

from core import navigator as nav
from utils import timing
from utils.log import get_logger

log = get_logger("search")

SORT_MAP = {
    "relevant": "general",
    "latest": "time_descending",
    "popular": "popularity_descending",
}

TYPE_MAP = {
    "all": "",
    "image": "1",
    "video": "2",
}


def search(
    page: Page,
    keyword: str,
    sort_by: str = "relevant",
    note_type: str = "all",
    limit: int = 20,
) -> dict:
    """Search for notes on Xiaohongshu.

    Args:
        page: Browser page (must be logged in).
        keyword: Search keyword.
        sort_by: Sort order - "relevant", "latest", "popular".
        note_type: Filter by type - "all", "image", "video".
        limit: Max number of results to collect.

    Returns dict with search results.
    """
    log.info(f"Searching: keyword='{keyword}', sort={sort_by}, type={note_type}")

    # Build search URL
    encoded_kw = quote(keyword)
    url = f"{nav.XHS_SEARCH}?keyword={encoded_kw}&source=web_search_result_notes"

    sort_key = SORT_MAP.get(sort_by, "general")
    if sort_key != "general":
        url += f"&sort={sort_key}"

    type_key = TYPE_MAP.get(note_type, "")
    if type_key:
        url += f"&type={type_key}"

    nav.goto(page, url)
    timing.action_pause(2000, 3000)

    # Collect results by scrolling
    results: list[dict] = []
    seen_ids: set[str] = set()
    scroll_count = 0
    max_scrolls = limit // 5 + 3

    while len(results) < limit and scroll_count < max_scrolls:
        # Extract note cards from the page
        new_notes = _extract_notes(page)

        for note in new_notes:
            if note["id"] not in seen_ids:
                seen_ids.add(note["id"])
                results.append(note)
                if len(results) >= limit:
                    break

        # Scroll for more
        nav.scroll_down(page, 800)
        scroll_count += 1
        timing.human_delay(1000, 2000)

    log.info(f"Found {len(results)} notes")

    return {
        "keyword": keyword,
        "sort_by": sort_by,
        "note_type": note_type,
        "count": len(results),
        "notes": results[:limit],
    }


def _extract_notes(page: Page) -> list[dict]:
    """Extract note data from current page DOM."""
    notes = []

    # Try to extract from __INITIAL_STATE__ (SSR data)
    # XHS uses Vue 3 reactive refs; must unwrap via _rawValue/_value
    try:
        state_data = page.evaluate("""
            () => {
                if (!window.__INITIAL_STATE__) return null;
                const state = window.__INITIAL_STATE__;
                const unwrap = (v) => {
                    if (v && v._rawValue !== undefined) return v._rawValue;
                    if (v && v._value !== undefined) return v._value;
                    return v;
                };
                const searchState = state.search;
                if (!searchState) return null;
                let feeds = unwrap(searchState.feeds) || unwrap(searchState.searchFeedsWrapper);
                if (!feeds) feeds = unwrap(state.feed?.feeds);
                if (!Array.isArray(feeds) || !feeds.length) return null;
                return feeds.map(item => {
                    const it = unwrap(item);
                    const nc = unwrap(it.noteCard || it.note_card) || it;
                    const user = unwrap(nc.user) || {};
                    const interact = unwrap(nc.interactInfo) || {};
                    const cover = unwrap(nc.cover) || {};
                    return {
                        id: it.id || it.noteId || it.note_id || '',
                        title: nc.title || nc.displayTitle || '',
                        nickname: user.nickname || user.nickName || '',
                        likedCount: interact.likedCount || '',
                        type: nc.type || '',
                        cover: cover.url || '',
                        xsecToken: it.xsecToken || it.xsec_token || '',
                    };
                });
            }
        """)
        if state_data:
            for item in state_data:
                note_id = item.get("id", "")
                if note_id:
                    xsec = item.get("xsecToken", "")
                    base_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                    notes.append({
                        "id": note_id,
                        "title": item.get("title", ""),
                        "author": item.get("nickname", ""),
                        "likes": str(item.get("likedCount", "")),
                        "type": item.get("type", ""),
                        "cover": item.get("cover", ""),
                        "xsec_token": xsec,
                        "url": f"{base_url}?xsec_token={xsec}" if xsec else base_url,
                    })
            if notes:
                return notes
    except Exception as e:
        log.debug(f"__INITIAL_STATE__ extraction failed: {e}")

    # Fallback: extract from DOM elements
    cards = page.locator('section.note-item, [class*="note-item"], '
                         'a[href*="/explore/"], a[href*="/search_result/"]').all()
    log.debug(f"DOM fallback: found {len(cards)} card elements")

    for card in cards:
        try:
            href = card.get_attribute("href") or ""
            note_id = ""
            match = re.search(r"/explore/([a-f0-9]+)", href)
            if match:
                note_id = match.group(1)

            title_el = card.locator('[class*="title"], h3, [class*="desc"]')
            title = title_el.first.text_content() if title_el.count() > 0 else ""

            author_el = card.locator('[class*="author"], [class*="nickname"]')
            author = author_el.first.text_content() if author_el.count() > 0 else ""

            likes_el = card.locator('[class*="like"], [class*="count"]')
            likes = likes_el.first.text_content() if likes_el.count() > 0 else ""

            if note_id:
                # Prefer full href if it already contains xsec_token
                xsec_match = re.search(r"xsec_token=([^&]+)", href)
                base_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                note_url = f"{base_url}?xsec_token={xsec_match.group(1)}" if xsec_match else base_url
                notes.append({
                    "id": note_id,
                    "title": (title or "").strip(),
                    "author": (author or "").strip(),
                    "likes": (likes or "").strip(),
                    "url": note_url,
                })
        except Exception:
            continue

    return notes


def _parse_feed_item(item: dict) -> dict | None:
    """Parse a feed item from __INITIAL_STATE__ data."""
    try:
        note_id = item.get("id") or item.get("noteId") or item.get("note_id", "")
        if not note_id:
            return None

        note_card = item.get("noteCard") or item.get("note_card") or item
        user = note_card.get("user") or {}

        xsec = item.get("xsecToken") or item.get("xsec_token", "")
        base_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        return {
            "id": note_id,
            "title": note_card.get("title") or note_card.get("displayTitle", ""),
            "author": user.get("nickname") or user.get("nickName", ""),
            "likes": str(note_card.get("interactInfo", {}).get("likedCount", "")),
            "type": note_card.get("type", ""),
            "cover": note_card.get("cover", {}).get("url", ""),
            "xsec_token": xsec,
            "url": f"{base_url}?xsec_token={xsec}" if xsec else base_url,
        }
    except Exception:
        return None
