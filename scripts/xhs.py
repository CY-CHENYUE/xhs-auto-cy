#!/usr/bin/env python3
"""xhs-auto-cy: Xiaohongshu automation CLI.

Usage:
    python3 xhs.py <command> [options]

Commands:
    browser     Browser lifecycle management
    login       Login via QR code
    publish-image   Publish an image post
    publish-video   Publish a video post
    search      Search notes
    detail      Fetch note details
    comment     Post a comment
    notifications   Scrape notifications
    dashboard   View creator metrics
    profile     Manage account profiles
    notes       Manage published notes (list/edit/delete)
    monitor     Data monitoring (snapshot/trend/history/export)
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path so local imports work
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from utils.log import setup_logging, get_logger
from core import config_store, browser_pool

log = get_logger("cli")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_profile(args) -> str:
    """Get profile name from args, env, or config default."""
    if hasattr(args, "profile") and args.profile:
        return args.profile
    env = config_store.get_env_override("profile")
    if env:
        return env
    cfg = config_store.load_config()
    return config_store.get_default_profile(cfg)


def _get_page(profile_name: str, headless: bool = False):
    """Launch browser if needed and return the active page."""
    page = browser_pool.get_page(profile_name)
    if page is not None:
        return page

    cfg = config_store.load_config()
    profile_dir = config_store.get_profile_dir(profile_name)
    channel = cfg.get("default", {}).get("chrome_channel", "chrome")
    _, _, page = browser_pool.launch(
        profile_dir=profile_dir,
        profile_name=profile_name,
        headless=headless,
        channel=channel,
    )
    return page


def _print_json(data: dict) -> None:
    """Pretty-print a result dict as JSON."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: browser
# ---------------------------------------------------------------------------

def cmd_browser(args):
    cfg = config_store.load_config()
    profile = _resolve_profile(args)

    if args.action == "launch":
        browser_pool.ensure_dependencies()
        profile_dir = config_store.get_profile_dir(profile)
        channel = cfg.get("default", {}).get("chrome_channel", "chrome")
        headless = args.headless or cfg.get("default", {}).get("headless", False)
        browser_pool.launch(
            profile_dir=profile_dir,
            profile_name=profile,
            headless=headless,
            channel=channel,
        )
        print(f"Browser launched for profile '{profile}'")
        # Keep process alive so the browser stays open
        try:
            input("Press Enter to close the browser...\n")
        except (KeyboardInterrupt, EOFError):
            pass
        browser_pool.kill(profile)

    elif args.action == "restart":
        profile_dir = config_store.get_profile_dir(profile)
        channel = cfg.get("default", {}).get("chrome_channel", "chrome")
        browser_pool.restart(profile_dir, profile, channel=channel)
        print(f"Browser restarted for profile '{profile}'")

    elif args.action == "kill":
        browser_pool.kill(profile)
        print(f"Browser killed for profile '{profile}'")

    elif args.action == "status":
        st = browser_pool.status()
        if not st:
            print("No active browser sessions.")
        else:
            _print_json(st)


# ---------------------------------------------------------------------------
# Subcommand: login
# ---------------------------------------------------------------------------

def cmd_login(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth

    if args.check:
        logged_in = auth.check_login(page, profile, use_cache=False)
        _print_json({"profile": profile, "logged_in": logged_in})
    else:
        ok = auth.login_qr(page, profile)
        _print_json({"profile": profile, "login_success": ok})


# ---------------------------------------------------------------------------
# Subcommand: publish-image
# ---------------------------------------------------------------------------

def cmd_publish_image(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, publish_image

    auth.ensure_logged_in(page, profile)

    content = args.content.replace("\\n", "\n") if args.content else ""
    images = args.images or []
    image_urls = args.image_urls or []
    topics = args.topics or []

    result = publish_image.publish(
        page=page,
        title=args.title,
        content=content,
        images=images,
        image_urls=image_urls,
        topics=topics,
        preview_only=args.preview,
        private=args.private,
    )
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: publish-video
# ---------------------------------------------------------------------------

def cmd_publish_video(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, publish_video

    auth.ensure_logged_in(page, profile)

    content = args.content.replace("\\n", "\n") if args.content else ""

    result = publish_video.publish(
        page=page,
        title=args.title,
        content=content,
        video=args.video,
        video_url=args.video_url,
        cover=args.cover,
        topics=args.topics or [],
        preview_only=args.preview,
        private=args.private,
    )
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: search
# ---------------------------------------------------------------------------

def cmd_search(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, search

    auth.ensure_logged_in(page, profile)

    result = search.search(
        page=page,
        keyword=args.keyword,
        sort_by=args.sort,
        note_type=args.type,
        limit=args.limit,
    )
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: detail
# ---------------------------------------------------------------------------

def cmd_detail(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, note_detail

    auth.ensure_logged_in(page, profile)

    result = note_detail.get_detail(page, args.url, xsec_token=args.xsec_token)
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: comment
# ---------------------------------------------------------------------------

def cmd_comment(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, comment

    auth.ensure_logged_in(page, profile)

    result = comment.post_comment(page, args.url, args.text)
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: notifications
# ---------------------------------------------------------------------------

def cmd_notifications(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, notifications

    auth.ensure_logged_in(page, profile)

    result = notifications.scrape(
        page=page,
        notification_type=args.type,
        limit=args.limit,
    )
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: dashboard
# ---------------------------------------------------------------------------

def cmd_dashboard(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, dashboard

    auth.ensure_logged_in(page, profile)

    result = dashboard.get_metrics(
        page=page,
        period=args.period,
        export_csv=args.export_csv,
    )
    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: profile
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Subcommand: notes
# ---------------------------------------------------------------------------

def cmd_notes(args):
    profile = _resolve_profile(args)
    page = _get_page(profile)

    from actions import auth, note_management

    auth.ensure_logged_in(page, profile)

    if args.action == "list":
        result = note_management.list_notes(page, limit=args.limit)
    elif args.action == "delete":
        if not args.note_id:
            print("ERROR: --note-id is required for delete", file=sys.stderr)
            sys.exit(1)
        result = note_management.delete_note(page, args.note_id)
    elif args.action == "edit":
        if not args.note_id:
            print("ERROR: --note-id is required for edit", file=sys.stderr)
            sys.exit(1)
        content = args.content.replace("\\n", "\n") if args.content else args.content
        result = note_management.edit_note(
            page, args.note_id, title=args.title, content=content,
        )
    else:
        print(f"Unknown notes action: {args.action}", file=sys.stderr)
        sys.exit(1)

    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: monitor
# ---------------------------------------------------------------------------

def cmd_monitor(args):
    profile = _resolve_profile(args)

    from actions import monitor

    if args.action == "snapshot":
        page = _get_page(profile)
        from actions import auth
        auth.ensure_logged_in(page, profile)
        result = monitor.take_snapshot(page, profile)
    elif args.action == "trend":
        result = monitor.show_trend(profile)
    elif args.action == "history":
        if not args.note_id:
            print("ERROR: --note-id is required for history", file=sys.stderr)
            sys.exit(1)
        result = monitor.show_history(profile, args.note_id)
    elif args.action == "export":
        result = monitor.export_data(profile, fmt=args.format, output=args.output)
    else:
        print(f"Unknown monitor action: {args.action}", file=sys.stderr)
        sys.exit(1)

    _print_json(result)


# ---------------------------------------------------------------------------
# Subcommand: profile
# ---------------------------------------------------------------------------

def cmd_profile(args):
    cfg = config_store.load_config()

    if args.action == "list":
        profiles = config_store.list_profiles(cfg)
        _print_json({"profiles": profiles})

    elif args.action == "add":
        display = args.display_name or args.name
        config_store.add_profile(cfg, args.name, display)
        print(f"Profile '{args.name}' added.")

    elif args.action == "remove":
        config_store.remove_profile(cfg, args.name)
        print(f"Profile '{args.name}' removed.")

    elif args.action == "set-default":
        config_store.set_default_profile(cfg, args.name)
        print(f"Default profile set to '{args.name}'.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xhs",
        description="Xiaohongshu automation CLI (xhs-auto-cy)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    subs = parser.add_subparsers(dest="command", required=True)

    # -- browser --
    p_browser = subs.add_parser("browser", help="Browser lifecycle management")
    p_browser.add_argument("action", choices=["launch", "restart", "kill", "status"])
    p_browser.add_argument("--profile", default=None, help="Profile name")
    p_browser.add_argument("--headless", action="store_true", help="Run headless")
    p_browser.set_defaults(func=cmd_browser)

    # -- login --
    p_login = subs.add_parser("login", help="Login via QR code scanning")
    p_login.add_argument("--check", action="store_true", help="Only check login status")
    p_login.add_argument("--profile", default=None)
    p_login.set_defaults(func=cmd_login)

    # -- publish-image --
    p_pi = subs.add_parser("publish-image", help="Publish an image post")
    p_pi.add_argument("--title", required=True, help="Post title")
    p_pi.add_argument("--content", required=True, help="Post body text")
    p_pi.add_argument("--images", nargs="+", help="Local image file paths")
    p_pi.add_argument("--image-urls", nargs="+", help="Image URLs to download")
    p_pi.add_argument("--topics", nargs="+", help="Topic hashtags")
    p_pi.add_argument("--preview", action="store_true", help="Fill form but do not submit")
    p_pi.add_argument("--private", action="store_true", help="Publish as private (仅自己可见)")
    p_pi.add_argument("--profile", default=None)
    p_pi.set_defaults(func=cmd_publish_image)

    # -- publish-video --
    p_pv = subs.add_parser("publish-video", help="Publish a video post")
    p_pv.add_argument("--title", required=True, help="Post title")
    p_pv.add_argument("--content", required=True, help="Post body text")
    p_pv.add_argument("--video", default=None, help="Local video file path")
    p_pv.add_argument("--video-url", default=None, help="Video URL to download")
    p_pv.add_argument("--cover", default=None, help="Cover image path")
    p_pv.add_argument("--topics", nargs="+", help="Topic hashtags")
    p_pv.add_argument("--preview", action="store_true", help="Fill form but do not submit")
    p_pv.add_argument("--private", action="store_true", help="Publish as private (仅自己可见)")
    p_pv.add_argument("--profile", default=None)
    p_pv.set_defaults(func=cmd_publish_video)

    # -- search --
    p_search = subs.add_parser("search", help="Search notes")
    p_search.add_argument("--keyword", required=True, help="Search keyword")
    p_search.add_argument("--sort", choices=["latest", "popular", "relevant"], default="relevant")
    p_search.add_argument("--type", choices=["all", "image", "video"], default="all")
    p_search.add_argument("--limit", type=int, default=20, help="Max results")
    p_search.add_argument("--profile", default=None)
    p_search.set_defaults(func=cmd_search)

    # -- detail --
    p_detail = subs.add_parser("detail", help="Fetch note details")
    p_detail.add_argument("--url", required=True, help="Note URL")
    p_detail.add_argument("--xsec-token", default="", help="xsec_token for note access")
    p_detail.add_argument("--profile", default=None)
    p_detail.set_defaults(func=cmd_detail)

    # -- comment --
    p_comment = subs.add_parser("comment", help="Post a comment on a note")
    p_comment.add_argument("--url", required=True, help="Note URL")
    p_comment.add_argument("--text", required=True, help="Comment text")
    p_comment.add_argument("--profile", default=None)
    p_comment.set_defaults(func=cmd_comment)

    # -- notifications --
    p_notif = subs.add_parser("notifications", help="Scrape notifications")
    p_notif.add_argument("--type", choices=["mentions", "likes", "comments", "follows"],
                         default="mentions")
    p_notif.add_argument("--limit", type=int, default=50, help="Max items")
    p_notif.add_argument("--profile", default=None)
    p_notif.set_defaults(func=cmd_notifications)

    # -- dashboard --
    p_dash = subs.add_parser("dashboard", help="Creator data dashboard")
    p_dash.add_argument("--period", choices=["7d", "30d"], default="7d")
    p_dash.add_argument("--export-csv", default=None, help="Export to CSV file path")
    p_dash.add_argument("--profile", default=None)
    p_dash.set_defaults(func=cmd_dashboard)

    # -- notes --
    p_notes = subs.add_parser("notes", help="Manage published notes")
    p_notes_sub = p_notes.add_subparsers(dest="action", required=True)

    p_notes_list = p_notes_sub.add_parser("list", help="List published notes")
    p_notes_list.add_argument("--limit", type=int, default=20, help="Max notes to return")

    p_notes_del = p_notes_sub.add_parser("delete", help="Delete a note")
    p_notes_del.add_argument("--note-id", required=True, help="Note ID to delete")

    p_notes_edit = p_notes_sub.add_parser("edit", help="Edit a note")
    p_notes_edit.add_argument("--note-id", required=True, help="Note ID to edit")
    p_notes_edit.add_argument("--title", default=None, help="New title")
    p_notes_edit.add_argument("--content", default=None, help="New content")

    p_notes.add_argument("--profile", default=None)
    p_notes.set_defaults(func=cmd_notes)

    # -- monitor --
    p_mon = subs.add_parser("monitor", help="Data monitoring and trend analysis")
    p_mon_sub = p_mon.add_subparsers(dest="action", required=True)

    p_mon_sub.add_parser("snapshot", help="Take a data snapshot")

    p_mon_sub.add_parser("trend", help="Compare recent snapshots")

    p_mon_hist = p_mon_sub.add_parser("history", help="View note history")
    p_mon_hist.add_argument("--note-id", required=True, help="Note ID or title")

    p_mon_exp = p_mon_sub.add_parser("export", help="Export all data")
    p_mon_exp.add_argument("--format", choices=["csv", "json"], default="csv")
    p_mon_exp.add_argument("--output", default="data.csv", help="Output file path")

    p_mon.add_argument("--profile", default=None)
    p_mon.set_defaults(func=cmd_monitor)

    # -- profile --
    p_prof = subs.add_parser("profile", help="Manage account profiles")
    p_prof_sub = p_prof.add_subparsers(dest="action", required=True)

    p_prof_sub.add_parser("list", help="List all profiles")

    p_add = p_prof_sub.add_parser("add", help="Add a profile")
    p_add.add_argument("name", help="Profile name")
    p_add.add_argument("--display-name", default=None, help="Display name")

    p_rm = p_prof_sub.add_parser("remove", help="Remove a profile")
    p_rm.add_argument("name", help="Profile name")

    p_sd = p_prof_sub.add_parser("set-default", help="Set default profile")
    p_sd.add_argument("name", help="Profile name")

    p_prof.set_defaults(func=cmd_profile)

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=level)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as exc:
        log.error(f"Command failed: {exc}", exc_info=args.debug)
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        browser_pool.kill_all()


if __name__ == "__main__":
    main()
