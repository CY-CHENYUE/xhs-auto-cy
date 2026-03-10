"""Image post publishing workflow for Xiaohongshu."""

import tempfile
from pathlib import Path

from playwright.sync_api import Page

from core import navigator as nav
from utils import timing, media
from utils.log import get_logger

log = get_logger("publish_image")

# Title length rules: Chinese char/punct = 2, ASCII = 1
MAX_TITLE_WEIGHT = 38


def _calc_title_weight(title: str) -> int:
    """Calculate title weight using XHS rules."""
    weight = 0
    for ch in title:
        if ord(ch) > 127:
            weight += 2
        else:
            weight += 1
    return weight


def _extract_topics(content: str) -> tuple[str, list[str]]:
    """Extract topic tags from the last line of content.

    If the last non-empty line consists entirely of #tag patterns,
    extract them as topics and remove that line from content.

    Returns (cleaned_content, topics_list).
    """
    lines = content.rstrip().split("\n")
    if not lines:
        return content, []

    last_line = lines[-1].strip()

    # Check if last line is all #tags
    import re
    tags = re.findall(r"#(\S+)", last_line)
    remaining = re.sub(r"#\S+", "", last_line).strip()

    if tags and not remaining:
        cleaned = "\n".join(lines[:-1]).rstrip()
        return cleaned, tags

    return content, []


def _input_topics(page: Page, topics: list[str]) -> None:
    """Add topic tags by typing # in the content editor to trigger XHS topic popup.

    Typing # in the XHS editor triggers the built-in topic search popup.
    We then type the tag name, wait for suggestions, and press Enter to
    select the first one — this creates a blue clickable topic tag.
    """
    if not topics:
        return

    log.info(f"Adding {len(topics)} topic tags by typing # in editor")

    for idx, tag in enumerate(topics[:10]):  # XHS limit
        # Re-click editor and move cursor to end before each tag
        content_editor = page.locator('[contenteditable="true"]')
        if content_editor.count() > 0:
            content_editor.first.click()
            timing.human_delay(300, 500)
            # Move cursor to the very end of content
            page.keyboard.press("Meta+ArrowDown")
            timing.human_delay(200, 400)
            page.keyboard.press("End")
            timing.human_delay(200, 300)

        # Type # to trigger the topic search popup
        page.keyboard.type("#", delay=100)
        timing.human_delay(1000, 1500)

        # Verify popup appeared (topic search input or suggestion list)
        popup_selectors = '[class*="topic"], [class*="hashtag"], [class*="suggest"], [class*="search-input"]'
        popup = page.locator(popup_selectors).first
        popup_visible = popup.count() > 0 and popup.is_visible()

        if not popup_visible:
            log.warning(f"Topic popup not visible for '{tag}', pressing Backspace and retrying")
            page.keyboard.press("Backspace")
            timing.human_delay(500, 800)
            page.keyboard.type("#", delay=100)
            timing.human_delay(1000, 1500)

        # Type the tag name to search
        page.keyboard.type(tag, delay=50)
        timing.human_delay(2000, 3000)  # Wait for search results to load

        # Press Enter to select the first suggestion (creates blue tag)
        page.keyboard.press("Enter")
        timing.human_delay(1200, 1800)

        log.info(f"Topic {idx + 1}/{len(topics)} added: '{tag}'")

    log.info("All topics added")


def _set_private(page: Page) -> None:
    """Set post visibility to 'only me' (仅自己可见)."""
    log.info("Setting visibility to private (仅自己可见)")

    # Scroll down to find the visibility setting
    page.mouse.wheel(0, 1000)
    timing.human_delay(500, 1000)

    # Find and click "公开可见" to open visibility dropdown
    public_btn = page.locator('text=公开可见')
    if public_btn.count() > 0:
        # Use Playwright's native click to properly trigger Vue event handlers
        public_btn.first.scroll_into_view_if_needed()
        timing.human_delay(300, 500)
        public_btn.first.click(force=True)
        timing.human_delay(1500, 2000)

        # Wait for dropdown to appear, then select "仅自己可见"
        private_opt = page.locator('text=仅自己可见')
        try:
            private_opt.first.wait_for(state="visible", timeout=5000)
            private_opt.first.click(force=True)
            timing.human_delay(500, 1000)
            log.info("Private visibility set")
            return
        except Exception:
            # Fallback: try clicking the parent container of the visibility setting
            log.warning("Dropdown didn't open with first click, retrying with parent element")
            # Try clicking the container that holds "公开可见"
            public_btn.first.evaluate("""el => {
                // Try clicking the closest interactive parent
                let target = el.closest('[class*=select], [class*=dropdown], [class*=trigger]') || el.parentElement;
                target.click();
            }""")
            timing.human_delay(1500, 2000)
            private_opt = page.locator('text=仅自己可见')
            if private_opt.count() > 0:
                try:
                    private_opt.first.wait_for(state="visible", timeout=5000)
                    private_opt.first.click(force=True)
                    timing.human_delay(500, 1000)
                    log.info("Private visibility set (fallback)")
                    return
                except Exception:
                    pass

    log.warning("Private option not found on page — post will be public")


def publish(
    page: Page,
    title: str,
    content: str,
    images: list[str] | None = None,
    image_urls: list[str] | None = None,
    topics: list[str] | None = None,
    preview_only: bool = False,
    private: bool = False,
) -> dict:
    """Publish an image post to Xiaohongshu.

    Args:
        page: Browser page (must be logged in).
        title: Post title (max weight 38).
        content: Post body text. Topics in last line will be auto-extracted.
        images: Local image file paths.
        image_urls: Image URLs to download first.
        topics: Explicit topic tags (overrides auto-extraction from content).
        preview_only: If True, fill form but don't click publish.

    Returns dict with status and details.
    """
    # Validate title
    title_weight = _calc_title_weight(title)
    if title_weight > MAX_TITLE_WEIGHT:
        raise ValueError(
            f"Title too long: weight {title_weight} > {MAX_TITLE_WEIGHT}. "
            f"Chinese chars count as 2, ASCII as 1."
        )

    # Prepare images
    local_images: list[str] = []
    tmp_dir = None

    if image_urls:
        tmp_dir = tempfile.mkdtemp(prefix="xhs_img_")
        downloaded = media.download_batch(image_urls, tmp_dir)
        local_images.extend(str(p) for p in downloaded)

    if images:
        for img_path in images:
            media.validate_image(img_path)
            local_images.append(str(Path(img_path).resolve()))

    if not local_images:
        raise ValueError("At least one image is required for image posts")

    # Extract topics from content if not explicitly provided
    if topics is None:
        content, topics = _extract_topics(content)

    log.info(f"Publishing image post: title='{title}', "
             f"images={len(local_images)}, topics={len(topics)}")

    # Navigate to publish page
    nav.goto(page, nav.XHS_PUBLISH)
    timing.action_pause()

    # Check if redirected to login page
    current_url = page.url
    if "login" in current_url.lower():
        raise RuntimeError(
            "未登录创作者中心！请先运行登录命令：\n"
            "  python3 scripts/xhs.py login --profile default\n"
            "在弹出的浏览器中完成手机号/扫码登录后重试。"
        )

    # Switch to "上传图文" tab (page defaults to video upload)
    img_tab = page.locator('.creator-tab:has-text("上传图文")')
    if img_tab.count() > 0:
        img_tab.first.evaluate("el => el.click()")
        log.info("Switched to image upload tab")
        timing.action_pause()

    # Upload images - find the image file input
    file_input = page.locator('input[type="file"]')
    try:
        file_input.first.wait_for(state="attached", timeout=15000)
    except Exception:
        raise RuntimeError("Image upload input not found on publish page")

    # Upload images one by one (XHS file input doesn't support multiple)
    for idx, img_path in enumerate(local_images):
        file_input = page.locator('input[type="file"]')
        file_input.first.set_input_files(img_path)
        log.info(f"Uploaded image {idx + 1}/{len(local_images)}: {Path(img_path).name}")
        timing.human_delay(2000, 3000)

    log.info(f"All {len(local_images)} image(s) uploaded")
    timing.action_pause(3000, 5000)

    # Fill title
    title_input = page.locator('[placeholder*="标题"]')
    if title_input.count() > 0:
        title_input.first.click()
        timing.human_delay(300, 500)
        page.keyboard.type(title, delay=30)
        log.info("Title filled")
    else:
        log.warning("Title input not found")

    timing.human_delay(500, 1000)

    # Fill content
    content_editor = page.locator('[contenteditable="true"]')
    if content_editor.count() > 0:
        content_editor.first.click()
        timing.human_delay(300, 600)
        page.keyboard.type(content, delay=5)
        log.info("Content filled")
    else:
        log.warning("Content editor not found")

    timing.action_pause()

    # Add topics
    _input_topics(page, topics)

    # Set visibility to private if requested
    if private:
        _set_private(page)

    if preview_only:
        log.info("Preview mode: form filled, publish button not clicked")
        nav.take_screenshot(page, "/tmp/xhs_preview.png")
        return {"status": "preview", "title": title, "images": len(local_images),
                "private": private}

    # Click publish button
    publish_btn = page.locator('button:has-text("发布")')
    if publish_btn.count() == 0:
        raise RuntimeError("Publish button not found")

    # Scroll publish button into view
    publish_btn.first.evaluate("el => el.scrollIntoView()")
    timing.human_delay(500, 1000)
    publish_btn.first.click()
    log.info("Publish button clicked")

    # Wait for success indication — try to detect "发布成功" text first
    success_text = page.locator('text=发布成功')
    try:
        success_text.first.wait_for(state="visible", timeout=15000)
    except Exception:
        pass  # Timeout is OK, we'll check other signals below

    nav.take_screenshot(page, "/tmp/xhs_publish_result.png")
    current_url = page.url

    # Check for "发布成功" text on page (most reliable signal)
    if success_text.count() > 0 and success_text.first.is_visible():
        log.info("Post published successfully (发布成功 detected)")
        return {"status": "success", "title": title, "images": len(local_images),
                "private": private}

    # Check if URL changed away from publish page
    if "publish" not in current_url.lower():
        log.info("Post published successfully (redirected)")
        return {"status": "success", "title": title, "images": len(local_images),
                "url": current_url, "private": private}

    # XHS often stays on /publish/publish after success but resets the form.
    # Detect this by checking if the title input is empty (form was reset).
    title_input = page.locator('[placeholder*="标题"]')
    if title_input.count() > 0:
        try:
            title_val = title_input.first.input_value(timeout=2000)
            if not title_val:
                log.info("Post published successfully (form reset detected)")
                return {"status": "success", "title": title,
                        "images": len(local_images), "private": private}
        except Exception:
            # contenteditable — check inner text
            try:
                title_text = title_input.first.text_content(timeout=2000) or ""
                if not title_text.strip():
                    log.info("Post published successfully (form reset detected)")
                    return {"status": "success", "title": title,
                            "images": len(local_images), "private": private}
            except Exception:
                pass

    # Check for error messages
    error_el = page.locator('[class*="error"], [class*="toast"][class*="error"], [class*="alert"]')
    error_msg = ""
    if error_el.count() > 0:
        try:
            error_msg = error_el.first.text_content(timeout=2000) or ""
        except Exception:
            pass

    if error_msg and ("失败" in error_msg or "error" in error_msg.lower()):
        log.error(f"Publish failed: {error_msg}")
        return {"status": "error", "message": error_msg}

    log.info("Publish button clicked, check screenshot at /tmp/xhs_publish_result.png")
    return {"status": "unknown", "title": title, "images": len(local_images),
            "message": "Publish clicked but success not confirmed. Check screenshot.",
            "screenshot": "/tmp/xhs_publish_result.png"}
