"""Media download and validation utilities."""

import mimetypes
import os
import uuid
from pathlib import Path

import httpx

from utils.log import get_logger

log = get_logger("media")

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}

MAX_IMAGE_SIZE_MB = 20
MAX_VIDEO_SIZE_MB = 500


def _guess_extension(url: str, content_type: str | None) -> str:
    """Guess file extension from URL path or Content-Type header."""
    # Try URL path first
    path = url.split("?")[0].split("#")[0]
    _, ext = os.path.splitext(path)
    if ext and ext.lower() in (SUPPORTED_IMAGE_EXTS | SUPPORTED_VIDEO_EXTS):
        return ext.lower()

    # Fall back to Content-Type
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext

    return ".jpg"  # safe default


def download_file(url: str, dest_dir: str | Path, timeout: int = 60) -> Path:
    """Download a file from URL to dest_dir.

    Returns the local file path.
    Raises httpx.HTTPStatusError on download failure.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://www.xiaohongshu.com/",
        })
        resp.raise_for_status()

    ext = _guess_extension(url, resp.headers.get("content-type"))
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = dest_dir / filename

    filepath.write_bytes(resp.content)
    log.info(f"Downloaded {url} -> {filepath} ({len(resp.content)} bytes)")
    return filepath


def download_batch(urls: list[str], dest_dir: str | Path) -> list[Path]:
    """Download multiple files, skipping failures.

    Returns list of successfully downloaded file paths.
    """
    results: list[Path] = []
    for url in urls:
        try:
            path = download_file(url, dest_dir)
            results.append(path)
        except Exception as e:
            log.warning(f"Failed to download {url}: {e}")
    return results


def validate_image(path: str | Path) -> None:
    """Validate an image file exists, has supported format and reasonable size.

    Raises MediaValidationError on any issue.
    """
    path = Path(path)
    if not path.is_file():
        raise MediaValidationError(f"Image not found: {path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_IMAGE_EXTS:
        raise MediaValidationError(
            f"Unsupported image format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_IMAGE_EXTS))}"
        )

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise MediaValidationError(
            f"Image too large: {size_mb:.1f}MB (max {MAX_IMAGE_SIZE_MB}MB)"
        )


def validate_video(path: str | Path) -> None:
    """Validate a video file exists, has supported format and reasonable size."""
    path = Path(path)
    if not path.is_file():
        raise MediaValidationError(f"Video not found: {path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_VIDEO_EXTS:
        raise MediaValidationError(
            f"Unsupported video format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_VIDEO_EXTS))}"
        )

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        raise MediaValidationError(
            f"Video too large: {size_mb:.1f}MB (max {MAX_VIDEO_SIZE_MB}MB)"
        )


class MediaValidationError(Exception):
    """Raised when media file validation fails."""
    pass
