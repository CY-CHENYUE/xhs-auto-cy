"""Human-like timing utilities to avoid bot detection."""

import random
import time


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def human_delay(min_ms: int = 800, max_ms: int = 2500) -> None:
    """Sleep for a random duration using normal distribution.

    The distribution is centered between min and max, with most values
    falling naturally in the middle range — more human-like than uniform.
    """
    center = (min_ms + max_ms) / 2
    sigma = (max_ms - min_ms) / 4
    delay = _clamp(random.gauss(center, sigma), min_ms, max_ms)
    time.sleep(delay / 1000)


def typing_delay(base_ms: int = 120) -> None:
    """Per-character delay for simulated typing.

    Varies between 60% and 160% of base to mimic natural typing rhythm.
    """
    jitter = random.uniform(0.6, 1.6)
    time.sleep(base_ms * jitter / 1000)


def action_pause(min_ms: int = 1500, max_ms: int = 4000) -> None:
    """Pause between major actions (e.g., after upload, before publish)."""
    human_delay(min_ms, max_ms)


def scroll_pause() -> None:
    """Short pause between scroll actions."""
    human_delay(300, 800)


def page_load_wait() -> None:
    """Wait for page to settle after navigation."""
    human_delay(2000, 4000)
