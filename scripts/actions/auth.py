"""Login and authentication management for Xiaohongshu."""

import json
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from core import browser_pool, config_store, navigator as nav
from utils.log import get_logger
from utils import timing

log = get_logger("auth")

# Login status cache file per profile
_CACHE_EXPIRY_HOURS = 12


def _cache_path(profile_name: str) -> Path:
    return config_store.get_profile_dir(profile_name) / ".login_cache.json"


def _read_cache(profile_name: str) -> bool | None:
    """Read cached login status. Returns None if expired or missing."""
    cache_file = _cache_path(profile_name)
    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text())
        from datetime import datetime, timezone
        cached_at = datetime.fromisoformat(data["checked_at"])
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        if age_hours > _CACHE_EXPIRY_HOURS:
            return None
        return data.get("logged_in", None)
    except Exception:
        return None


def _write_cache(profile_name: str, logged_in: bool) -> None:
    """Cache login status (only caches positive results)."""
    if not logged_in:
        return
    from datetime import datetime, timezone
    cache_file = _cache_path(profile_name)
    cache_file.write_text(json.dumps({
        "logged_in": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }))


def check_login(page: Page, profile_name: str = "default",
                use_cache: bool = True) -> bool:
    """Check if the user is logged in on Xiaohongshu.

    First checks creator center login state, then falls back to homepage.

    Returns True if logged in, False otherwise.
    """
    if use_cache:
        cached = _read_cache(profile_name)
        if cached is not None:
            log.info(f"Login status (cached): logged_in={cached}")
            return cached

    log.info("Checking login status...")

    # Check creator center
    nav.goto(page, nav.XHS_CREATOR, timeout=15000)
    timing.human_delay(1000, 2000)

    current_url = page.url
    if "login" in current_url.lower():
        log.info("Not logged in (redirected to login page)")
        return False

    # Check for user avatar or profile element as login indicator
    logged_in = nav.wait_for_element(
        page, '[class*="user"], [class*="avatar"], [class*="creator"]',
        timeout=5000,
    )

    if not logged_in:
        # Try homepage check
        nav.goto(page, nav.XHS_HOME, timeout=15000)
        timing.human_delay(1000, 2000)
        logged_in = nav.wait_for_element(
            page, '[class*="user"], [class*="avatar"]',
            timeout=5000,
        )

    log.info(f"Login check result: logged_in={logged_in}")
    _write_cache(profile_name, logged_in)
    return logged_in


def login_qr(page: Page, profile_name: str = "default",
             screenshot_dir: str | None = None) -> bool:
    """Navigate to login page for QR code scanning.

    In headed mode: user scans QR code directly in browser.
    Takes a screenshot of the QR code for reference.

    Returns True if login succeeded.
    """
    log.info("Starting QR code login flow...")

    nav.goto(page, nav.XHS_LOGIN, timeout=20000)
    timing.human_delay(2000, 3000)

    # Try to find QR code element
    qr_found = nav.wait_for_element(
        page, '[class*="qrcode"], [class*="QR"], canvas, [class*="login-qr"]',
        timeout=10000,
    )

    if not qr_found:
        log.warning("QR code element not found. Login page may have changed.")

    # Take screenshot for reference
    if screenshot_dir:
        ss_path = str(Path(screenshot_dir) / "login_qr.png")
    else:
        ss_path = str(config_store.get_profile_dir(profile_name) / "login_qr.png")
    nav.take_screenshot(page, ss_path)
    log.info(f"QR code screenshot saved to {ss_path}")
    print(f"[LOGIN] Please scan the QR code. Screenshot: {ss_path}")

    # Wait for login to complete (user scans QR code)
    # Poll for redirect away from login page
    max_wait_seconds = 120
    poll_interval = 3
    waited = 0

    while waited < max_wait_seconds:
        timing.human_delay(poll_interval * 1000, poll_interval * 1000 + 500)
        waited += poll_interval

        current_url = page.url
        if "login" not in current_url.lower():
            log.info("Login successful! Redirected away from login page.")
            _write_cache(profile_name, True)
            print("[LOGIN] Login successful!")
            return True

        if waited % 15 == 0:
            log.info(f"Waiting for QR scan... ({waited}s/{max_wait_seconds}s)")

    log.warning("Login timeout - QR code not scanned within time limit")
    print("[LOGIN] Login timed out. Please try again.")
    return False


def verify_session_live(page: Page, profile_name: str = "default") -> bool:
    """Check if the server-side session is still valid (bypasses local cache).

    Navigates to creator center and checks for login redirect.
    Returns True if session is alive, False if expired.
    """
    log.info("Verifying server-side session...")
    return check_login(page, profile_name, use_cache=False)


def invalidate_cache(profile_name: str = "default") -> None:
    """Remove the local login cache so next check hits the server."""
    cache_file = _cache_path(profile_name)
    if cache_file.exists():
        cache_file.unlink()
        log.info(f"Login cache invalidated for profile '{profile_name}'")


def logout(page: Page, profile_name: str = "default") -> None:
    """Clear login cache. Full logout requires clearing browser cookies."""
    invalidate_cache(profile_name)
    log.info(f"Logged out for profile '{profile_name}'")


def ensure_logged_in(page: Page, profile_name: str = "default",
                     auto_login: bool = True) -> bool:
    """Check login status and attempt login if needed.

    Args:
        page: Browser page.
        profile_name: Profile to check.
        auto_login: If True, start QR login flow when not logged in.

    Returns True if logged in (or login succeeded).
    """
    if check_login(page, profile_name):
        return True

    if not auto_login:
        return False

    log.info("Not logged in. Starting login flow...")
    return login_qr(page, profile_name)
