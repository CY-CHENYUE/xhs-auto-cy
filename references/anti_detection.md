# Anti-Detection Strategy

## Overview

XHS uses various techniques to detect automated browser activity. This document outlines our countermeasures.

## Browser Fingerprint

### Real Chrome via `channel="chrome"`
- Playwright launches the system-installed Chrome instead of bundled Chromium
- Avoids Chromium-specific detection signals (e.g., missing Chrome plugins, different `navigator.plugins`)
- Fallback: if Chrome is not installed, use bundled Chromium with extra stealth patches

### playwright-stealth
Applied automatically to every page via `stealth_sync(page)`. Patches include:
- `navigator.webdriver` → `false`
- `window.chrome` runtime object injection
- Consistent `navigator.plugins` and `navigator.mimeTypes`
- WebGL vendor/renderer masking
- `chrome.csi` and `chrome.loadTimes` stubs
- Permissions API behavior normalization
- iframe contentWindow access fix

### Launch Arguments
```
--disable-blink-features=AutomationControlled
--no-first-run
--no-default-browser-check
```

## Behavioral Mimicry

### Timing
- **Action delays**: Gaussian distribution (not uniform) with configurable min/max
- **Typing**: Per-character input at 80-200ms intervals with jitter
- **Scrolling**: Random-distance scrolls with short pauses
- **Page load**: Extra wait after navigation for dynamic content

### Input Methods
- Text typed character-by-character (not pasted in bulk)
- Mouse movements before clicks (Playwright default behavior)
- Random small delays between sequential operations

### Viewport & Display
- Default viewport: 1440×900 (common MacBook resolution)
- Locale: `zh-CN`, Timezone: `Asia/Shanghai`
- No User-Agent override (use Chrome's native UA)

## Session Persistence

### Persistent Context
- `launch_persistent_context()` preserves cookies, localStorage, IndexedDB across sessions
- Each profile has its own Chrome user-data directory (`~/.xhs-auto-cy/profiles/<name>/`)
- Login state persists until cookies expire

### Login Cache
- JSON cache records login status with 12-hour TTL
- Avoids unnecessary login checks that could trigger rate limits

## Rate Limiting Awareness

- Minimum 1-3 seconds between major actions
- No rapid-fire requests to search/publish endpoints
- Headless mode disabled by default (headed is less suspicious)

## Known Detection Vectors (XHS-specific)

1. **Rapid navigation**: Don't jump between pages faster than a human would
2. **Repetitive patterns**: Vary timing between operations
3. **Missing interactions**: Scroll the page, hover elements — don't just fill forms
4. **Device consistency**: Keep the same viewport/UA across sessions for one profile
5. **API-level checks**: XHS may check `window.performance`, canvas fingerprint, WebRTC

## Maintenance Notes

- XHS updates their detection roughly monthly
- If operations start failing with CAPTCHA or login redirects, check:
  1. Is `playwright-stealth` up to date?
  2. Has XHS changed their login flow?
  3. Are the selectors in `selectors.toml` still valid?
- Run headed mode to visually debug detection issues
