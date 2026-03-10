"""Chrome browser lifecycle management using Playwright persistent contexts.

Each profile gets its own Chrome instance with isolated cookies and state.
"""

import subprocess
import sys
from pathlib import Path

from utils.log import get_logger

log = get_logger("browser")

# Track active browser contexts per profile
_active_contexts: dict[str, object] = {}
_active_browsers: dict[str, object] = {}


def _check_playwright_installed() -> bool:
    """Check if playwright and browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


def ensure_dependencies() -> None:
    """Install playwright and browser if not present."""
    if not _check_playwright_installed():
        log.info("Installing playwright...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "playwright>=1.40", "playwright-stealth>=1.0"],
            stdout=subprocess.DEVNULL,
        )

    # Check if chromium is installed
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try launching to check browser availability
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        log.info("Installing Playwright browser (chromium)...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL,
        )


def launch(
    profile_dir: Path,
    profile_name: str = "default",
    headless: bool = False,
    channel: str = "chrome",
    viewport_width: int = 1440,
    viewport_height: int = 900,
) -> tuple:
    """Launch a persistent browser context for a profile.

    Args:
        profile_dir: Path to Chrome user data directory.
        profile_name: Name of the profile (for tracking).
        headless: Run in headless mode.
        channel: Browser channel ("chrome" for real Chrome, None for bundled Chromium).
        viewport_width: Browser viewport width.
        viewport_height: Browser viewport height.

    Returns:
        Tuple of (playwright_instance, browser_context, page).
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    if profile_name in _active_contexts:
        log.warning(f"Profile '{profile_name}' already has an active context. Closing it first.")
        kill(profile_name)

    log.info(f"Launching browser for profile '{profile_name}' "
             f"(headless={headless}, channel={channel})")

    # Clean up stale singleton lock files from previous crashes
    for lock_file in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = profile_dir / lock_file
        if lock_path.exists():
            log.info(f"Removing stale {lock_file}")
            lock_path.unlink(missing_ok=True)

    pw = sync_playwright().start()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel=channel if channel else None,
        headless=headless,
        viewport={"width": viewport_width, "height": viewport_height},
        args=launch_args,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        ignore_https_errors=True,
    )

    # Apply stealth evasions to the browser context
    Stealth().apply_stealth_sync(context)

    # Use first page if exists, otherwise create one
    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()

    _active_contexts[profile_name] = context
    _active_browsers[profile_name] = pw

    log.info(f"Browser launched for profile '{profile_name}'")
    return pw, context, page


def get_context(profile_name: str = "default"):
    """Get the active browser context for a profile, or None if not running."""
    return _active_contexts.get(profile_name)


def get_page(profile_name: str = "default"):
    """Get the first page of the active context."""
    ctx = _active_contexts.get(profile_name)
    if ctx is None:
        return None
    pages = ctx.pages
    return pages[0] if pages else None


def kill(profile_name: str = "default") -> None:
    """Close browser and clean up for a profile."""
    ctx = _active_contexts.pop(profile_name, None)
    pw = _active_browsers.pop(profile_name, None)

    if ctx:
        try:
            ctx.close()
            log.info(f"Browser context closed for '{profile_name}'")
        except Exception as e:
            log.warning(f"Error closing context for '{profile_name}': {e}")

    if pw:
        try:
            pw.stop()
        except Exception:
            pass


def kill_all() -> None:
    """Close all active browser contexts."""
    for name in list(_active_contexts.keys()):
        kill(name)


def restart(
    profile_dir: Path,
    profile_name: str = "default",
    **kwargs,
) -> tuple:
    """Restart browser for a profile."""
    kill(profile_name)
    return launch(profile_dir, profile_name, **kwargs)


def status() -> dict[str, dict]:
    """Return status of all active browser contexts."""
    result = {}
    for name, ctx in _active_contexts.items():
        try:
            pages = ctx.pages
            result[name] = {
                "running": True,
                "pages": len(pages),
                "urls": [p.url for p in pages],
            }
        except Exception:
            result[name] = {"running": False, "error": "Context may be stale"}
    return result
