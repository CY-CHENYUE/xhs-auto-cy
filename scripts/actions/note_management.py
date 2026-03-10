"""Note management: list, edit, and delete published notes."""

import re
import json

from playwright.sync_api import Page

from core import navigator as nav
from utils import timing
from utils.log import get_logger

log = get_logger("notes")


def list_notes(page: Page, limit: int = 20) -> dict:
    """List published notes from the creator note management page.

    Args:
        page: Browser page (must be logged in as creator).
        limit: Maximum number of notes to return.

    Returns dict with note list.
    """
    log.info(f"Listing notes (limit={limit})")

    nav.goto(page, nav.XHS_NOTE_MANAGEMENT)
    timing.action_pause(2000, 4000)

    notes = _extract_notes_from_state(page)

    if not notes:
        notes = _extract_notes_from_dom(page)

    # Scroll to load more if needed
    while len(notes) < limit:
        prev_count = len(notes)
        nav.scroll_down(page, 600)
        timing.human_delay(1500, 2500)

        more = _extract_notes_from_dom(page)
        # Merge by deduplicating on id or title
        seen_ids = {n.get("id") or n.get("title") for n in notes}
        for n in more:
            key = n.get("id") or n.get("title")
            if key and key not in seen_ids:
                notes.append(n)
                seen_ids.add(key)

        if len(notes) == prev_count:
            break  # No more notes loaded

    notes = notes[:limit]

    return {
        "count": len(notes),
        "notes": notes,
    }


def delete_note(page: Page, note_id: str) -> dict:
    """Delete a note by its ID.

    Args:
        page: Browser page (must be logged in as creator).
        note_id: The note ID to delete.

    Returns dict with deletion result.
    """
    log.info(f"Deleting note: {note_id}")

    nav.goto(page, nav.XHS_NOTE_MANAGEMENT)
    timing.action_pause(2000, 4000)

    # Find the note element by ID
    note_el = _find_note_element(page, note_id)
    if not note_el:
        return {"success": False, "error": f"Note not found: {note_id}"}

    # Delete button is directly visible on each note card (no "more" menu needed)
    delete_btn = note_el.locator(
        'button:has-text("删除"), a:has-text("删除"), span:has-text("删除"), [class*="delete"]'
    )
    if delete_btn.count() == 0:
        return {"success": False, "error": "Delete button not found"}

    delete_btn.first.click()
    timing.human_delay(500, 1000)

    # Confirm deletion dialog (DevUI d-modal or generic)
    confirm_btn = page.locator(
        'd-modal button:has-text("确定"), button:has-text("确定"), '
        'button:has-text("确认"), [class*="confirm"] button'
    )
    if confirm_btn.count() > 0:
        confirm_btn.first.click()
        timing.action_pause(1500, 3000)

    log.info(f"Note deleted: {note_id}")
    return {"success": True, "note_id": note_id}


def edit_note(
    page: Page,
    note_id: str,
    title: str | None = None,
    content: str | None = None,
) -> dict:
    """Edit a note's title and/or content.

    Args:
        page: Browser page (must be logged in as creator).
        note_id: The note ID to edit.
        title: New title (optional).
        content: New content (optional).

    Returns dict with edit result.
    """
    if not title and not content:
        return {"success": False, "error": "Must provide --title or --content"}

    log.info(f"Editing note: {note_id}")

    nav.goto(page, nav.XHS_NOTE_MANAGEMENT)
    timing.action_pause(2000, 4000)

    note_el = _find_note_element(page, note_id)
    if not note_el:
        return {"success": False, "error": f"Note not found: {note_id}"}

    # Edit button is directly visible on each note card
    edit_btn = note_el.locator(
        'button:has-text("编辑"), a:has-text("编辑"), span:has-text("编辑"), [class*="edit"]'
    )
    if edit_btn.count() == 0:
        return {"success": False, "error": "Edit button not found"}

    edit_btn.first.click()
    timing.action_pause(2000, 4000)

    # Edit title if provided
    if title:
        title_selector = (
            '[placeholder*="标题"], [class*="title"] input, '
            '[class*="title"] textarea, #title'
        )
        title_input = page.locator(title_selector)
        if title_input.count() > 0:
            # Use the first matching element directly — click, select all, type
            el = title_input.first
            el.click()
            page.keyboard.press("Meta+a")
            timing.human_delay(100, 300)
            page.keyboard.press("Backspace")
            timing.human_delay(200, 500)
            el.type(title, delay=50)
            timing.human_delay(300, 600)
            log.info(f"Title updated to: {title}")

    # Edit content if provided
    if content:
        content_selector = (
            '[class*="content"] [contenteditable], '
            '[class*="editor"] [contenteditable], '
            '[placeholder*="正文"], textarea[class*="content"], '
            '#post-textarea'
        )
        content_input = page.locator(content_selector)
        if content_input.count() > 0:
            content_el = content_input.first
            content_el.click()
            page.keyboard.press("Meta+a")
            timing.human_delay(100, 300)
            page.keyboard.press("Backspace")
            timing.human_delay(200, 500)
            content_el.type(content, delay=30)
            log.info("Content updated")

    # Click save/publish button
    save_btn = page.locator(
        'button:has-text("保存"), button:has-text("发布"), '
        'button:has-text("确认"), [class*="submit"] button'
    )
    if save_btn.count() > 0:
        save_btn.first.click()
        timing.action_pause(2000, 4000)

    return {"success": True, "note_id": note_id, "updated": {
        **({"title": title} if title else {}),
        **({"content": content} if content else {}),
    }}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_note_element(page: Page, note_id: str):
    """Find the DOM element for a note by its ID.

    The /new/note-manager page uses div.note elements with a data-impression
    attribute containing JSON with noteId.
    """
    # Primary: find by data-impression containing the note ID
    all_notes = page.locator('.notes-container .note, div.note[data-impression]').all()
    for el in all_notes:
        impression = el.get_attribute("data-impression") or ""
        if note_id in impression:
            return el

    # Secondary: try data attributes or link hrefs
    selectors = [
        f'[data-note-id="{note_id}"]',
        f'[data-id="{note_id}"]',
        f'div.note:has(a[href*="{note_id}"])',
        f'a[href*="{note_id}"]',
    ]
    for sel in selectors:
        el = page.locator(sel)
        if el.count() > 0:
            return el.first

    # Fallback: check all note-like containers
    rows = page.locator(
        '[class*="note-item"], [class*="note-card"], [class*="content-item"]'
    ).all()
    for row in rows:
        links = row.locator("a").all()
        for link in links:
            href = link.get_attribute("href") or ""
            if note_id in href:
                return row

    return None


def _extract_notes_from_state(page: Page) -> list[dict]:
    """Try to extract notes list from window.__INITIAL_STATE__."""
    try:
        raw = page.evaluate("""
            () => {
                const state = window.__INITIAL_STATE__;
                if (!state) return null;

                // Unwrap Vue 3 reactive refs
                const unwrap = (v) => {
                    if (v && v._rawValue !== undefined) return v._rawValue;
                    if (v && v._value !== undefined) return v._value;
                    return v;
                };

                // Try common state paths for note management
                const noteState = unwrap(state.noteManagement)
                    || unwrap(state.publish)
                    || unwrap(state.content)
                    || state;

                const noteList = unwrap(noteState.noteList)
                    || unwrap(noteState.notes)
                    || unwrap(noteState.list)
                    || [];

                if (!Array.isArray(noteList) || noteList.length === 0) return null;

                return JSON.stringify(noteList.map(n => {
                    const note = unwrap(n);
                    return {
                        id: note.noteId || note.id || note.note_id || '',
                        title: note.title || note.name || '',
                        status: note.status || note.auditStatus || '',
                        publish_time: note.publishTime || note.createTime || note.time || '',
                        views: note.readCount || note.views || note.impressions || 0,
                        likes: note.likedCount || note.likes || 0,
                        collects: note.collectedCount || note.collects || 0,
                    };
                }));
            }
        """)
        if raw:
            return json.loads(raw)
    except Exception as e:
        log.debug(f"State extraction for notes failed: {e}")

    return []


def _extract_notes_from_dom(page: Page) -> list[dict]:
    """Extract notes from DOM elements.

    /new/note-manager page structure (DevUI):
      div.notes-container > div.note (with data-impression JSON containing noteId)
        div.img  — thumbnail
        div.info — title (.title), time (.time), metrics (.icon_list > .icon > span)
        actions  — 权限设置, 置顶, 编辑, 删除 buttons
    Metric icon order: 👁views, 💬comments, ❤likes, ⭐collects, 👤followers
    """
    notes = []

    # Primary selector: actual page uses div.note inside .notes-container
    rows = page.locator('.notes-container .note, div.note[data-impression]').all()

    if not rows:
        # Fallback: broader selectors
        rows = page.locator(
            '[class*="note-item"], [class*="note-card"], [class*="content-item"]'
        ).all()

    metric_keys = ["views", "comments", "likes", "collects", "followers"]

    for row in rows:
        try:
            note: dict = {}

            # Extract title from div.title inside div.info
            title_el = row.locator('.info .title, [class*="title"]')
            if title_el.count() > 0:
                note["title"] = (title_el.first.text_content() or "").strip()

            # Extract note ID from data-impression attribute
            impression = row.get_attribute("data-impression") or ""
            if impression:
                id_match = re.search(r'"noteId"\s*:\s*"([a-f0-9]{24})"', impression)
                if id_match:
                    note["id"] = id_match.group(1)

            # Fallback: extract note ID from link href
            if not note.get("id"):
                links = row.locator("a").all()
                for link in links:
                    href = link.get_attribute("href") or ""
                    match = re.search(r'/(?:explore|note|discovery)/([a-f0-9]{24})', href)
                    if match:
                        note["id"] = match.group(1)
                        break

            # Extract publish time from div.time
            time_el = row.locator('.info .time, [class*="time"]')
            if time_el.count() > 0:
                time_text = (time_el.first.text_content() or "").strip()
                time_match = re.search(r'发布于\s*(.+)', time_text)
                note["publish_time"] = time_match.group(1).strip() if time_match else time_text

            # Extract metrics from .icon_list > .icon > span
            icon_spans = row.locator('.icon_list .icon span, .icon_list .icon > span').all()
            for i, span in enumerate(icon_spans):
                if i < len(metric_keys):
                    val = (span.text_content() or "").strip().replace(",", "")
                    try:
                        note[metric_keys[i]] = int(val)
                    except ValueError:
                        note[metric_keys[i]] = val

            if note.get("title"):
                notes.append(note)

        except Exception:
            continue

    return notes
