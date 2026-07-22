"""Helpers for invoking cog command callbacks under test."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable


@runtime_checkable
class SupportsCallback(Protocol):
    """Minimal surface of discord.app_commands / ext.commands Command objects."""

    callback: Callable[..., object]


def get_callback(command: SupportsCallback | Callable[..., object]) -> Callable[..., object]:
    """Return the underlying coroutine for an app_commands/hybrid Command or plain function."""
    callback: Callable[..., object] = command.callback if isinstance(command, SupportsCallback) else command
    while hasattr(callback, "__wrapped__"):
        callback = callback.__wrapped__
    return callback
