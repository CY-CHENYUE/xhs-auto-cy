"""Data monitoring: snapshots, trends, history, and export."""

import csv
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from core import config_store
from utils.log import get_logger

log = get_logger("monitor")


def _monitor_dir(profile: str) -> Path:
    """Get the monitor data directory for a profile."""
    base = Path.home() / ".xhs-auto-cy" / "monitor" / profile
    base.mkdir(parents=True, exist_ok=True)
    return base


def take_snapshot(page: Page, profile: str) -> dict:
    """Take a data snapshot and save to disk.

    Args:
        page: Browser page (must be logged in as creator).
        profile: Profile name for storage isolation.

    Returns dict with snapshot summary.
    """
    from actions import dashboard

    log.info("Taking data snapshot")

    result = dashboard.get_metrics(page=page, period="7d")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot = {
        "timestamp": timestamp,
        "datetime": datetime.now().isoformat(),
        "overview": result.get("overview", {}),
        "notes": result.get("notes", []),
    }

    # Save snapshot file
    monitor_path = _monitor_dir(profile)
    filepath = monitor_path / f"{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    log.info(f"Snapshot saved to {filepath}")

    return {
        "success": True,
        "snapshot_file": str(filepath),
        "timestamp": timestamp,
        "note_count": len(snapshot["notes"]),
        "overview": snapshot["overview"],
    }


def show_trend(profile: str) -> dict:
    """Compare the two most recent snapshots and show trends.

    Args:
        profile: Profile name.

    Returns dict with trend data.
    """
    log.info("Calculating trends")

    monitor_path = _monitor_dir(profile)
    snapshots = sorted(monitor_path.glob("*.json"))

    if len(snapshots) < 2:
        return {
            "success": False,
            "error": f"Need at least 2 snapshots, found {len(snapshots)}. "
                     "Run 'monitor snapshot' first.",
        }

    # Load the two most recent
    with open(snapshots[-1], encoding="utf-8") as f:
        current = json.load(f)
    with open(snapshots[-2], encoding="utf-8") as f:
        previous = json.load(f)

    period = f"{previous.get('datetime', '?')[:10]} → {current.get('datetime', '?')[:10]}"

    # Build per-note comparison
    prev_notes = {n.get("title", ""): n for n in previous.get("notes", [])}
    curr_notes = current.get("notes", [])

    notes_trend = []
    total_views_delta = 0
    total_likes_delta = 0

    for note in curr_notes:
        title = note.get("title", "")
        prev = prev_notes.get(title)
        if not prev:
            continue

        trend_entry = {"title": title}
        for metric in ("views", "likes", "collects", "comments", "shares"):
            curr_val = _parse_int(note.get(metric, 0))
            prev_val = _parse_int(prev.get(metric, 0))
            delta = curr_val - prev_val
            rate = f"{(delta / prev_val * 100):+.1f}%" if prev_val > 0 else "N/A"

            trend_entry[metric] = {
                "current": curr_val,
                "previous": prev_val,
                "delta": f"{delta:+d}",
                "rate": rate,
            }

            if metric == "views":
                total_views_delta += delta
            elif metric == "likes":
                total_likes_delta += delta

        notes_trend.append(trend_entry)

    return {
        "success": True,
        "period": period,
        "summary": {
            "total_views_delta": f"{total_views_delta:+d}",
            "total_likes_delta": f"{total_likes_delta:+d}",
        },
        "notes": notes_trend,
    }


def show_history(profile: str, note_id: str) -> dict:
    """Show historical data for a specific note across all snapshots.

    Args:
        profile: Profile name.
        note_id: Note ID or title to search for.

    Returns dict with history data.
    """
    log.info(f"Fetching history for note: {note_id}")

    monitor_path = _monitor_dir(profile)
    snapshots = sorted(monitor_path.glob("*.json"))

    if not snapshots:
        return {"success": False, "error": "No snapshots found. Run 'monitor snapshot' first."}

    history = []
    for snap_path in snapshots:
        with open(snap_path, encoding="utf-8") as f:
            data = json.load(f)

        for note in data.get("notes", []):
            # Match by ID or title
            if note_id in (note.get("id", ""), note.get("title", "")):
                history.append({
                    "timestamp": data.get("datetime", data.get("timestamp", "")),
                    "views": _parse_int(note.get("views", 0)),
                    "likes": _parse_int(note.get("likes", 0)),
                    "collects": _parse_int(note.get("collects", 0)),
                    "comments": _parse_int(note.get("comments", 0)),
                })
                break

    return {
        "success": True,
        "note_id": note_id,
        "data_points": len(history),
        "history": history,
    }


def export_data(profile: str, fmt: str = "csv", output: str = "data.csv") -> dict:
    """Export all snapshot data to a file.

    Args:
        profile: Profile name.
        fmt: Output format ("csv" or "json").
        output: Output file path.

    Returns dict with export result.
    """
    log.info(f"Exporting monitor data (format={fmt}, output={output})")

    monitor_path = _monitor_dir(profile)
    snapshots = sorted(monitor_path.glob("*.json"))

    if not snapshots:
        return {"success": False, "error": "No snapshots found."}

    all_rows = []
    for snap_path in snapshots:
        with open(snap_path, encoding="utf-8") as f:
            data = json.load(f)

        ts = data.get("datetime", data.get("timestamp", ""))
        for note in data.get("notes", []):
            row = {"timestamp": ts}
            row.update(note)
            all_rows.append(row)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, ensure_ascii=False, indent=2)
    else:
        # CSV export
        if not all_rows:
            return {"success": False, "error": "No data to export."}

        fieldnames: list[str] = []
        seen: set[str] = set()
        for row in all_rows:
            for key in row:
                if key not in seen:
                    fieldnames.append(key)
                    seen.add(key)

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

    log.info(f"Exported {len(all_rows)} rows to {output_path}")

    return {
        "success": True,
        "format": fmt,
        "output": str(output_path),
        "total_rows": len(all_rows),
        "snapshots_included": len(snapshots),
    }


def _parse_int(value) -> int:
    """Safely parse a value to int."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        clean = value.replace(",", "").strip()
        try:
            return int(clean)
        except ValueError:
            return 0
    return 0
