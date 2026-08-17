"""Docker HEALTHCHECK heartbeat: the bot refreshes a file; the probe only stats it.

This module is stdlib-only so ``python src/utils/health.py`` can run as the image
HEALTHCHECK without importing the ``src`` package (which would truncate logs).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_DEFAULT_PATH = "/tmp/discord_bot.healthy"
_DEFAULT_MAX_AGE_SECONDS = 60.0


def heartbeat_path() -> Path:
    """Resolve the heartbeat file path (``HEALTHCHECK_PATH`` or the default)."""
    return Path(os.environ.get("HEALTHCHECK_PATH", _DEFAULT_PATH))


def max_age_seconds() -> float:
    """Resolve how recently the heartbeat must have been touched."""
    raw = os.environ.get("HEALTHCHECK_MAX_AGE", str(_DEFAULT_MAX_AGE_SECONDS))
    return float(raw)


def touch_health() -> None:
    """Create or refresh the heartbeat file (call from the bot event loop)."""
    path = heartbeat_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def clear_health() -> None:
    """Remove the heartbeat so a shutting-down container is not healthy."""
    heartbeat_path().unlink(missing_ok=True)


def is_heartbeat_fresh() -> bool:
    """True when the heartbeat file exists and is newer than ``max_age_seconds``."""
    try:
        age = time.time() - heartbeat_path().stat().st_mtime
    except FileNotFoundError:
        return False
    return age <= max_age_seconds()


if __name__ == "__main__":
    sys.exit(0 if is_heartbeat_fresh() else 1)
