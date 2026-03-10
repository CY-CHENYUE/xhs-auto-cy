"""Chrome browser lifecycle management using Playwright persistent contexts.

Each profile gets its own Chrome instance with isolated cookies and state.
Supports standalone mode: Chrome runs as an independent process (detached from Python)
and is reused across multiple CLI invocations via CDP (Chrome DevTools Protocol).
"""

import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

from utils.log import get_logger

log = get_logger("browser")

# Track active browser contexts per profile
_active_contexts: dict[str, object] = {}
_active_browsers: dict[str, object] = {}

# Endpoint file name stored inside the profile directory
_CDP_ENDPOINT_FILE = ".cdp_endpoint.json"


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
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        log.info("Installing Playwright browser (chromium)...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL,
        )


# ---------------------------------------------------------------------------
# Standalone Chrome helpers
# ---------------------------------------------------------------------------

def find_chrome_path() -> str:
    """Locate the Chrome executable on the system."""
    if sys.platform == "darwin":
        path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(path):
            return path
    elif sys.platform == "linux":
        for candidate in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            import shutil
            found = shutil.which(candidate)
            if found:
                return found
    elif sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")):
            path = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.exists(path):
                return path
    raise FileNotFoundError("Could not find Chrome executable. Please install Google Chrome.")


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _endpoint_path(profile_dir: Path) -> Path:
    return profile_dir / _CDP_ENDPOINT_FILE


def _read_endpoint(profile_dir: Path) -> dict | None:
    """Read the CDP endpoint file. Returns dict with 'port' and 'pid', or None."""
    ep = _endpoint_path(profile_dir)
    if not ep.exists():
        return None
    try:
        data = json.loads(ep.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_endpoint(profile_dir: Path, port: int, pid: int) -> None:
    ep = _endpoint_path(profile_dir)
    ep.write_text(json.dumps({"port": port, "pid": pid}))


def _remove_endpoint(profile_dir: Path) -> None:
    ep = _endpoint_path(profile_dir)
    ep.unlink(missing_ok=True)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _is_port_listening(port: int) -> bool:
    """Check if something is listening on the given port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            return True
    except (ConnectionRefusedError, OSError):
        return False


def launch_standalone(
    profile_dir: Path,
    profile_name: str = "default",
    headless: bool = False,
) -> dict:
    """Launch Chrome as a detached standalone process with remote debugging.

    Args:
        profile_dir: Path to Chrome user data directory.
        profile_name: Name of the profile (for logging).
        headless: Run in headless mode.

    Returns:
        dict with 'port' and 'pid'.
    """
    chrome_path = find_chrome_path()

    # Clean up stale singleton lock files from previous crashes
    for lock_file in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = profile_dir / lock_file
        if lock_path.exists():
            log.info(f"Removing stale {lock_file}")
            lock_path.unlink(missing_ok=True)

    port = _find_free_port()

    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        chrome_args.append("--headless=new")

    log.info(f"Launching standalone Chrome for '{profile_name}' on port {port}")

    # Launch Chrome detached from this Python process
    proc = subprocess.Popen(
        chrome_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait briefly for Chrome to start listening
    import time
    for _ in range(30):  # up to 3 seconds
        if _is_port_listening(port):
            break
        time.sleep(0.1)
    else:
        log.warning(f"Chrome may not have started on port {port} in time")

    _write_endpoint(profile_dir, port, proc.pid)
    log.info(f"Standalone Chrome launched: PID={proc.pid}, port={port}")
    return {"port": port, "pid": proc.pid}


def connect_existing(
    profile_name: str = "default",
    profile_dir: Path | None = None,
) -> tuple | None:
    """Connect to an already-running standalone Chrome via CDP.

    Args:
        profile_name: Profile name for tracking.
        profile_dir: Path to profile directory (to find endpoint file).

    Returns:
        Tuple of (playwright_instance, browser_context, page) or None if no Chrome running.
    """
    if profile_dir is None:
        from core import config_store
        profile_dir = config_store.get_profile_dir(profile_name)

    endpoint = _read_endpoint(profile_dir)
    if not endpoint:
        return None

    port = endpoint["port"]
    pid = endpoint["pid"]

    if not _is_pid_alive(pid):
        log.info(f"Standalone Chrome PID {pid} is no longer alive, cleaning up")
        _remove_endpoint(profile_dir)
        return None

    if not _is_port_listening(port):
        log.info(f"Port {port} not listening, cleaning up")
        _remove_endpoint(profile_dir)
        return None

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    log.info(f"Connecting to existing Chrome on port {port} for '{profile_name}'")

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

        # Get the default context (the one with the user profile data)
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                ignore_https_errors=True,
            )

        # Apply stealth evasions
        Stealth().apply_stealth_sync(context)

        # Get or create a page
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        _active_contexts[profile_name] = context
        _active_browsers[profile_name] = pw

        log.info(f"Connected to existing Chrome for '{profile_name}'")
        return pw, context, page

    except Exception as e:
        log.warning(f"Failed to connect to Chrome on port {port}: {e}")
        _remove_endpoint(profile_dir)
        try:
            pw.stop()
        except Exception:
            pass
        return None


def disconnect(profile_name: str = "default") -> None:
    """Disconnect Playwright from Chrome without killing the Chrome process."""
    _active_contexts.pop(profile_name, None)
    pw = _active_browsers.pop(profile_name, None)

    if pw:
        try:
            pw.stop()
            log.info(f"Disconnected Playwright for '{profile_name}' (Chrome still running)")
        except Exception:
            pass


def disconnect_all() -> None:
    """Disconnect all Playwright connections without killing Chrome processes."""
    for name in list(_active_contexts.keys()):
        disconnect(name)


# ---------------------------------------------------------------------------
# Original API (preserved for compatibility)
# ---------------------------------------------------------------------------

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
    try:
        pages = ctx.pages
        return pages[0] if pages else None
    except Exception:
        # Context may be stale (e.g. Chrome was killed externally)
        _active_contexts.pop(profile_name, None)
        _active_browsers.pop(profile_name, None)
        return None


def kill(profile_name: str = "default") -> None:
    """Close browser and clean up for a profile.

    Also kills any standalone Chrome process tracked by the endpoint file.
    """
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

    # Also kill standalone Chrome process if endpoint file exists
    from core import config_store
    try:
        profile_dir = config_store.get_profile_dir(profile_name)
        endpoint = _read_endpoint(profile_dir)
        if endpoint:
            pid = endpoint["pid"]
            if _is_pid_alive(pid):
                log.info(f"Killing standalone Chrome PID {pid} for '{profile_name}'")
                os.kill(pid, signal.SIGTERM)
            _remove_endpoint(profile_dir)
    except Exception as e:
        log.warning(f"Error cleaning up standalone Chrome for '{profile_name}': {e}")


def kill_all() -> None:
    """Close all active browser contexts and kill standalone Chrome processes."""
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
    """Return status of all browser sessions (in-memory and standalone)."""
    result = {}

    # Check in-memory contexts
    for name, ctx in _active_contexts.items():
        try:
            pages = ctx.pages
            result[name] = {
                "running": True,
                "mode": "connected",
                "pages": len(pages),
                "urls": [p.url for p in pages],
            }
        except Exception:
            result[name] = {"running": False, "error": "Context may be stale"}

    # Check standalone Chrome processes from endpoint files
    from core import config_store
    try:
        cfg = config_store.load_config()
        profiles = config_store.list_profiles(cfg)
        for prof in profiles:
            pname = prof if isinstance(prof, str) else prof.get("name", "default")
            if pname in result:
                continue
            profile_dir = config_store.get_profile_dir(pname)
            endpoint = _read_endpoint(profile_dir)
            if endpoint and _is_pid_alive(endpoint["pid"]):
                result[pname] = {
                    "running": True,
                    "mode": "standalone",
                    "pid": endpoint["pid"],
                    "port": endpoint["port"],
                }
    except Exception:
        pass

    return result
