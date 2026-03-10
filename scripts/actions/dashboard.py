"""Content data dashboard and metrics scraping for Xiaohongshu creator center."""

import csv
import json
from pathlib import Path

from playwright.sync_api import Page

from core import navigator as nav
from utils import timing
from utils.log import get_logger

log = get_logger("dashboard")


def get_metrics(
    page: Page,
    period: str = "7d",
    export_csv: str | None = None,
) -> dict:
    """Fetch content performance metrics from the creator data center.

    Args:
        page: Browser page (must be logged in as creator).
        period: Time period - "7d", "30d".
        export_csv: Optional CSV file path for export.

    Returns dict with metrics data.
    """
    log.info(f"Fetching dashboard metrics (period={period})")

    nav.goto(page, nav.XHS_DATA_CENTER)
    timing.action_pause(2000, 4000)

    # Select time period if available
    period_map = {"7d": "7", "30d": "30"}
    period_val = period_map.get(period, "7")

    period_btn = page.locator(f'text="{period_val}天", text="近{period_val}天", '
                              f'[class*="period"][data-value="{period_val}"]')
    if period_btn.count() > 0:
        period_btn.first.click()
        timing.action_pause(1000, 2000)

    # Extract metrics
    metrics = _extract_metrics(page)

    # Extract per-note table data
    notes_data = _extract_notes_table(page)
    metrics["notes"] = notes_data

    # Export to CSV if requested
    if export_csv and notes_data:
        _export_csv(notes_data, export_csv)
        metrics["csv_exported"] = export_csv
        log.info(f"Metrics exported to {export_csv}")

    return metrics


def _extract_metrics(page: Page) -> dict:
    """Extract overview metrics from the dashboard page."""
    metrics: dict = {}

    # Try __INITIAL_STATE__ first
    try:
        raw = page.evaluate("""
            () => {
                const state = window.__INITIAL_STATE__;
                if (!state) return null;
                const stats = state.statistics || state.dataAnalysis || {};
                return JSON.stringify(stats);
            }
        """)
        if raw:
            data = json.loads(raw)
            overview = data.get("overview") or data.get("summary") or {}
            if overview:
                metrics["overview"] = overview
                return metrics
    except Exception as e:
        log.debug(f"State extraction failed: {e}")

    # Fallback: extract from DOM
    metric_names = [
        ("views", ["浏览", "曝光", "观看"]),
        ("likes", ["点赞"]),
        ("collects", ["收藏"]),
        ("comments", ["评论"]),
        ("shares", ["分享"]),
        ("followers", ["涨粉", "粉丝增长"]),
    ]

    for key, keywords in metric_names:
        for kw in keywords:
            # Find elements containing the keyword and a nearby number
            el = page.locator(f'text=/{kw}/')
            if el.count() > 0:
                parent = el.first.locator("..")
                # Look for a number in the parent element
                parent_text = parent.text_content() or ""
                import re
                numbers = re.findall(r"[\d,]+", parent_text)
                if numbers:
                    metrics[key] = numbers[0].replace(",", "")
                    break

    return metrics


def _extract_notes_table(page: Page) -> list[dict]:
    """Extract per-note data from the DevUI table on the data-analysis page.

    Actual table: .d-new-table with columns:
    笔记基础信息 | 曝光 | 观看 | 封面点击率 | 点赞 | 评论 | 收藏 | 涨粉 | 分享 | 人均观看时长 | 弹幕 | 操作

    First cell (.note-info-content) contains title + publish time.
    Last cell ("操作") is excluded from metrics.
    """
    # Column keys matching header order (skip first "title" cell and last "操作" cell)
    metric_cols = [
        "impressions", "views", "cover_ctr", "likes", "comments",
        "collects", "followers", "shares", "avg_watch_time", "danmaku",
    ]

    try:
        raw = page.evaluate("""
            () => {
                const rows = document.querySelectorAll('.d-new-table tbody tr');
                if (!rows.length) return null;
                return Array.from(rows).map(row => {
                    const tds = row.querySelectorAll('td');
                    // First td: note info (title + publish time)
                    const infoCell = tds[0];
                    const noteContent = infoCell ? infoCell.querySelector('.note-info-content') : null;
                    let title = '', publishTime = '';
                    if (noteContent) {
                        // Title is usually the first child text or a .title element
                        const titleEl = noteContent.children[0];
                        title = titleEl ? titleEl.textContent.trim() : '';
                        // Time is the second child
                        const timeEl = noteContent.children[1];
                        publishTime = timeEl ? timeEl.textContent.trim() : '';
                    } else if (infoCell) {
                        title = infoCell.textContent.trim();
                    }
                    // Metric tds: index 1 to N-1 (last is "操作")
                    const metrics = [];
                    for (let i = 1; i < tds.length - 1; i++) {
                        metrics.push(tds[i].textContent.trim());
                    }
                    return { title, publishTime, metrics };
                });
            }
        """)
    except Exception:
        raw = None

    notes: list[dict] = []

    if raw:
        for item in raw:
            if not item.get("title"):
                continue
            note = {"title": item["title"]}
            if item.get("publishTime"):
                note["publish_time"] = item["publishTime"].replace("发布于", "").strip()
            for i, val in enumerate(item.get("metrics", [])):
                if i < len(metric_cols):
                    note[metric_cols[i]] = val
            notes.append(note)
        return notes

    # Fallback: use Playwright locators
    nav.scroll_down(page, 500)
    timing.human_delay(1000, 2000)

    rows = page.locator('.d-new-table tbody tr, table tbody tr').all()
    for row in rows:
        try:
            tds = row.locator("td").all()
            if len(tds) < 3:
                continue
            note = {}
            # First cell: note info
            info_el = tds[0].locator('.note-info-content')
            if info_el.count() > 0:
                children = info_el.first.locator('> *').all()
                if children:
                    note["title"] = (children[0].text_content() or "").strip()
                if len(children) > 1:
                    time_text = (children[1].text_content() or "").strip()
                    note["publish_time"] = time_text.replace("发布于", "").strip()
            else:
                note["title"] = (tds[0].text_content() or "").strip()
            # Metric cells: skip first and last
            for i, td in enumerate(tds[1:-1]):
                if i < len(metric_cols):
                    note[metric_cols[i]] = (td.text_content() or "").strip()
            if note.get("title"):
                notes.append(note)
        except Exception:
            continue

    return notes


def _export_csv(notes: list[dict], filepath: str) -> None:
    """Export notes data to a CSV file."""
    if not notes:
        return

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Collect all keys across all notes
    fieldnames: list[str] = []
    seen: set[str] = set()
    for note in notes:
        for key in note:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(notes)

    log.info(f"Exported {len(notes)} rows to {filepath}")
