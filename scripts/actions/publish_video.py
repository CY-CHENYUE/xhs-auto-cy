"""Video post publishing workflow for Xiaohongshu."""

import tempfile
from pathlib import Path

from playwright.sync_api import Page

from core import navigator as nav
from utils import timing, media
from utils.log import get_logger

log = get_logger("publish_video")


def publish(
    page: Page,
    title: str,
    content: str,
    video: str | None = None,
    video_url: str | None = None,
    cover: str | None = None,
    topics: list[str] | None = None,
    preview_only: bool = False,
    private: bool = False,
) -> dict:
    """Publish a video post to Xiaohongshu.

    Args:
        page: Browser page (must be logged in).
        title: Post title.
        content: Post body text.
        video: Local video file path.
        video_url: Video URL to download first.
        cover: Optional cover image path.
        topics: Topic tags.
        preview_only: Fill form but don't publish.

    Returns dict with status and details.
    """
    from actions.publish_image import _calc_title_weight, _extract_topics, _input_topics, _set_private, MAX_TITLE_WEIGHT

    # Validate title
    title_weight = _calc_title_weight(title)
    if title_weight > MAX_TITLE_WEIGHT:
        raise ValueError(f"Title too long: weight {title_weight} > {MAX_TITLE_WEIGHT}")

    # Prepare video
    local_video: str | None = None
    tmp_dir = None

    if video_url:
        tmp_dir = tempfile.mkdtemp(prefix="xhs_vid_")
        downloaded = media.download_file(video_url, tmp_dir)
        local_video = str(downloaded)
    elif video:
        media.validate_video(video)
        local_video = str(Path(video).resolve())

    if not local_video:
        raise ValueError("A video file or URL is required")

    # Extract topics from content if not explicitly provided
    if topics is None:
        content, topics = _extract_topics(content)

    log.info(f"Publishing video post: title='{title}'")

    # Navigate to publish page
    nav.goto(page, nav.XHS_PUBLISH)
    timing.action_pause()

    # Switch to video tab if needed
    video_tab = page.locator('text=上传视频, text=视频, [class*="video-tab"], [data-type="video"]')
    if video_tab.count() > 0:
        video_tab.first.click()
        timing.action_pause()

    # Upload video
    file_input = page.locator('input[type="file"][accept*="video"], input[type="file"]')
    if file_input.count() == 0:
        raise RuntimeError("Video upload input not found")

    file_input.first.set_input_files(local_video)
    log.info("Video file uploaded, waiting for processing...")

    # Wait for video processing (can take a while)
    timing.human_delay(5000, 8000)

    # Wait for processing indicator to disappear or progress to complete
    for _ in range(60):  # max 5 minutes
        processing = page.locator('[class*="progress"], [class*="upload"], text=上传中, text=处理中')
        if processing.count() == 0:
            break
        timing.human_delay(4000, 6000)
    else:
        log.warning("Video processing timeout")

    # Upload cover image if provided
    if cover:
        media.validate_image(cover)
        cover_input = page.locator('[class*="cover"] input[type="file"], '
                                   'text=上传封面, text=选择封面')
        if cover_input.count() > 0:
            if cover_input.first.get_attribute("type") == "file":
                cover_input.first.set_input_files(str(Path(cover).resolve()))
            else:
                cover_input.first.click()
                timing.action_pause()
            log.info("Cover image uploaded")

    # Fill title
    title_input = page.locator('[placeholder*="标题"]')
    if title_input.count() > 0:
        title_input.first.click()
        timing.human_delay(200, 400)
        for ch in title:
            page.keyboard.type(ch, delay=0)
            timing.typing_delay()

    timing.action_pause(500, 1000)

    # Fill content
    content_editor = page.locator('[class*="ql-editor"], [contenteditable="true"], '
                                  '[placeholder*="正文"]')
    if content_editor.count() > 0:
        content_editor.first.click()
        timing.human_delay(300, 600)
        if len(content) > 100:
            page.keyboard.type(content, delay=5)
        else:
            for ch in content:
                page.keyboard.type(ch, delay=0)
                timing.typing_delay(base_ms=60)

    timing.action_pause()

    # Add topics
    _input_topics(page, topics)

    # Set visibility to private if requested
    if private:
        _set_private(page)

    if preview_only:
        log.info("Preview mode: form filled, publish skipped")
        return {"status": "preview", "title": title, "type": "video", "private": private}

    # Click publish
    publish_btn = page.locator('button:has-text("发布"), button:has-text("Publish")')
    if publish_btn.count() == 0:
        raise RuntimeError("Publish button not found")

    timing.action_pause(1000, 2000)
    publish_btn.first.click()
    log.info("Publish button clicked")

    timing.human_delay(3000, 5000)

    current_url = page.url
    if "publish" not in current_url.lower():
        log.info("Video published successfully!")
        return {"status": "success", "title": title, "type": "video", "url": current_url,
                "private": private}
    else:
        error_el = page.locator('[class*="error"], [class*="toast"]')
        error_msg = error_el.first.text_content() if error_el.count() > 0 else "Unknown error"
        return {"status": "error", "message": error_msg}
