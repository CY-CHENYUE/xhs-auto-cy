"""TOML-based configuration management for xhs-auto-cy.

Config file location: ~/.xhs-auto-cy/config.toml
Profile data: ~/.xhs-auto-cy/profiles/<name>/
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Python 3.11+ has tomllib built-in
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

from utils.log import get_logger

log = get_logger("config")

BASE_DIR = Path.home() / ".xhs-auto-cy"
CONFIG_PATH = BASE_DIR / "config.toml"
PROFILES_DIR = BASE_DIR / "profiles"

DEFAULT_CONFIG = {
    "default": {
        "profile": "default",
        "headless": False,
        "chrome_channel": "chrome",
    },
    "timing": {
        "min_action_delay_ms": 1000,
        "max_action_delay_ms": 3000,
        "typing_delay_ms": 120,
    },
    "logging": {
        "level": "INFO",
        "format": "pretty",
    },
    "profiles": {
        "default": {
            "display_name": "主账号",
            "created_at": "",
        },
    },
}


def _ensure_dirs() -> None:
    """Create base directories if they don't exist."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load config from TOML file. Creates default if missing."""
    _ensure_dirs()

    if not CONFIG_PATH.exists():
        log.info(f"Creating default config at {CONFIG_PATH}")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    return config


def save_config(config: dict) -> None:
    """Write config dict to TOML file."""
    _ensure_dirs()

    if tomli_w is None:
        log.error("tomli_w not installed. Run: pip install tomli_w")
        raise RuntimeError("tomli_w required for writing config")

    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(config, f)

    log.info(f"Config saved to {CONFIG_PATH}")


def get_profile_dir(profile_name: str) -> Path:
    """Get the Chrome user-data directory for a profile."""
    profile_dir = PROFILES_DIR / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_default_profile(config: dict) -> str:
    """Get the default profile name from config."""
    return config.get("default", {}).get("profile", "default")


def add_profile(config: dict, name: str, display_name: str = "") -> dict:
    """Add a new profile to config."""
    if "profiles" not in config:
        config["profiles"] = {}

    if name in config["profiles"]:
        log.warning(f"Profile '{name}' already exists")
        return config

    config["profiles"][name] = {
        "display_name": display_name or name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    get_profile_dir(name)
    save_config(config)
    log.info(f"Profile '{name}' created")
    return config


def remove_profile(config: dict, name: str, delete_data: bool = False) -> dict:
    """Remove a profile from config."""
    if name not in config.get("profiles", {}):
        log.warning(f"Profile '{name}' not found")
        return config

    del config["profiles"][name]
    save_config(config)

    if delete_data:
        import shutil
        profile_dir = PROFILES_DIR / name
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
            log.info(f"Deleted profile data at {profile_dir}")

    log.info(f"Profile '{name}' removed")
    return config


def list_profiles(config: dict) -> list[dict]:
    """List all profiles with their info."""
    profiles = []
    default_name = get_default_profile(config)

    for name, info in config.get("profiles", {}).items():
        profile_dir = PROFILES_DIR / name
        profiles.append({
            "name": name,
            "display_name": info.get("display_name", name),
            "is_default": name == default_name,
            "data_exists": profile_dir.exists(),
            "created_at": info.get("created_at", ""),
        })

    return profiles


def set_default_profile(config: dict, name: str) -> dict:
    """Set the default profile."""
    if name not in config.get("profiles", {}):
        raise ValueError(f"Profile '{name}' not found")

    config.setdefault("default", {})["profile"] = name
    save_config(config)
    log.info(f"Default profile set to '{name}'")
    return config


def get_env_override(key: str) -> str | None:
    """Check for environment variable override.

    Mapping: XHS_PROFILE -> profile, XHS_DEBUG -> debug mode.
    """
    env_map = {
        "profile": "XHS_PROFILE",
        "headless": "XHS_HEADLESS",
        "debug": "XHS_DEBUG",
    }
    env_key = env_map.get(key)
    if env_key:
        return os.environ.get(env_key)
    return None
