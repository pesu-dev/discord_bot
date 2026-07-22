"""Helpers for invoking cog command callbacks under test."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def get_callback(command: Any) -> Callable[..., Any]:
    """Return the underlying coroutine for an app_commands/hybrid Command or plain function."""
    callback = getattr(command, "callback", command)
    while hasattr(callback, "__wrapped__"):
        callback = callback.__wrapped__
    return callback
