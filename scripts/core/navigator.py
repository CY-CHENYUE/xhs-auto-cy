"""Page navigation and human-like interaction utilities.

Wraps Playwright page operations with anti-detection timing and retries.
"""

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.log import get_logger
from utils import timing

log = get_logger("nav")

# XHS URLs
XHS_HOME = "https://www.xiaohongshu.com"
XHS_CREATOR = "https://creator.xiaohongshu.com"
XHS_PUBLISH = "https://creator.xiaohongshu.com/publish/publish"
XHS_LOGIN = "https://creator.xiaohongshu.com/login"
XHS_SEARCH = "https://www.xiaohongshu.com/search_result"
XHS_NOTIFICATION = "https://www.xiaohongshu.com/notification"
XHS_DATA_CENTER = "https://creator.xiaohongshu.com/statistics/data-analysis"
XHS_NOTE_MANAGEMENT = "https://creator.xiaohongshu.com/new/note-manager"
XHS_EXPLORE = "https://www.xiaohongshu.com/explore"


def is_security_blocked(page: Page) -> bool:
    """Check if page was redirected to XHS security/404 page."""
    url = page.url
    return "/404" in url or "error_code" in url or "sec_" in url


def goto(page: Page, url: str, wait_until: str = "domcontentloaded",
         timeout: int = 30000) -> None:
    """Navigate to URL with retry and human-like wait."""
    log.info(f"Navigating to {url}")
    try:
        page.goto(url, wait_until=wait_until, timeout=timeout)
    except PlaywrightTimeout:
        log.warning(f"Navigation timeout, retrying: {url}")
        page.goto(url, wait_until=wait_until, timeout=timeout)
    timing.page_load_wait()


def click(page: Page, selector: str, timeout: int = 10000) -> None:
    """Click an element with human-like timing."""
    timing.human_delay(200, 600)
    page.click(selector, timeout=timeout)
    timing.human_delay(300, 800)


def fill_text(page: Page, selector: str, text: str, clear_first: bool = True) -> None:
    """Type text into an input field character by character.

    Simulates human typing speed with per-character random delays.
    """
    element = page.locator(selector)
    element.wait_for(state="visible", timeout=10000)

    if clear_first:
        element.click()
        page.keyboard.press("Meta+a")
        timing.human_delay(100, 300)
        page.keyboard.press("Backspace")
        timing.human_delay(200, 500)

    element.click()
    for char in text:
        page.keyboard.type(char, delay=0)
        timing.typing_delay()


def paste_text(page: Page, selector: str, text: str) -> None:
    """Paste text into an element using clipboard (faster for long content).

    Falls back to fill_text if paste fails.
    """
    element = page.locator(selector)
    element.wait_for(state="visible", timeout=10000)
    element.click()
    page.keyboard.press("Meta+a")
    timing.human_delay(100, 200)

    # Use evaluate to set clipboard and paste
    page.evaluate(f"""
        (text) => {{
            const dt = new DataTransfer();
            dt.setData('text/plain', text);
            const el = document.activeElement;
            if (el) {{
                el.dispatchEvent(new ClipboardEvent('paste', {{
                    clipboardData: dt, bubbles: true, cancelable: true
                }}));
            }}
        }}
    """, text)
    timing.human_delay(300, 600)


def upload_files(page: Page, selector: str, file_paths: list[str]) -> None:
    """Upload files via a file input element.

    Args:
        page: Playwright page.
        selector: Selector for the file input element.
        file_paths: List of absolute file paths to upload.
    """
    log.info(f"Uploading {len(file_paths)} file(s)")
    input_el = page.locator(selector)
    input_el.set_input_files(file_paths)
    timing.action_pause()


def scroll_down(page: Page, distance: int = 500) -> None:
    """Scroll down the page by a given pixel distance."""
    page.mouse.wheel(0, distance)
    timing.scroll_pause()


def wait_for_element(page: Page, selector: str, timeout: int = 10000,
                     state: str = "visible") -> bool:
    """Wait for an element to appear. Returns True if found, False if timeout."""
    try:
        page.locator(selector).first.wait_for(state=state, timeout=timeout)
        return True
    except PlaywrightTimeout:
        return False


def extract_text(page: Page, selector: str, timeout: int = 5000) -> str | None:
    """Extract text content from an element. Returns None if not found."""
    try:
        el = page.locator(selector)
        el.wait_for(state="visible", timeout=timeout)
        return el.text_content()
    except PlaywrightTimeout:
        return None


def extract_all_text(page: Page, selector: str, timeout: int = 5000) -> list[str]:
    """Extract text from all matching elements."""
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout)
    except PlaywrightTimeout:
        return []

    elements = page.locator(selector).all()
    return [el.text_content() or "" for el in elements]


def take_screenshot(page: Page, path: str) -> str:
    """Take a screenshot and return the file path."""
    page.screenshot(path=path)
    log.info(f"Screenshot saved to {path}")
    return path


def get_page_data(page: Page, js_expression: str):
    """Evaluate JavaScript and return the result."""
    return page.evaluate(js_expression)
