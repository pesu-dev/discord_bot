from __future__ import annotations

import contextvars
import functools
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import discord
from discord.ext import commands

from src.utils.general import handle_command_error

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.utils.config import Config

P = ParamSpec("P")
R = TypeVar("R")

_defer_ephemeral: contextvars.ContextVar[bool] = contextvars.ContextVar("defer_ephemeral", default=True)


class CommandLocation(StrEnum):
    GUILD = "guild"
    DM = "dm"


class FunctionalRole(StrEnum):
    ADMIN = "ADMIN"
    MOD = "MOD"
    BOT_DEV = "BOT_DEV"
    LINKED = "LINKED"
    JUST_JOINED = "JUST_JOINED"
    MUTED = "MUTED"

    @property
    def config_attr(self) -> str:
        return f"{self.name.lower()}_role"


_DEFAULT_LOCATION_MESSAGES: dict[CommandLocation, str] = {
    CommandLocation.GUILD: "This command can only be used in a server.",
    CommandLocation.DM: "This command can only be used in DMs.",
}


def _is_guild_messageable(channel: discord.abc.MessageableChannel | None) -> bool:
    if channel is None or not isinstance(channel, discord.abc.Messageable):
        return False
    if isinstance(channel, (discord.DMChannel, discord.GroupChannel)):
        return False
    return getattr(channel, "guild", None) is not None


def _is_dm_messageable(channel: discord.abc.MessageableChannel | None) -> bool:
    return isinstance(channel, (discord.DMChannel, discord.GroupChannel))


def _resolve_context(args: tuple[Any, ...]) -> discord.Interaction | commands.Context:
    if len(args) < 2:
        msg = "Expected at least self and context/interaction"
        raise ValueError(msg)
    ctx_or_interaction = args[1]
    if isinstance(ctx_or_interaction, discord.Interaction | commands.Context):
        return ctx_or_interaction
    msg = f"Expected Interaction or Context, got {type(ctx_or_interaction)}"
    raise TypeError(msg)


def _get_member(ctx_or_interaction: discord.Interaction | commands.Context) -> discord.Member | None:
    if isinstance(ctx_or_interaction, discord.Interaction):
        user = ctx_or_interaction.user
        return user if isinstance(user, discord.Member) else None
    author = ctx_or_interaction.author
    return author if isinstance(author, discord.Member) else None


def _get_channel(ctx_or_interaction: discord.Interaction | commands.Context) -> discord.abc.MessageableChannel | None:
    channel = ctx_or_interaction.channel
    return channel if isinstance(channel, discord.abc.Messageable) else None


def _get_ephemeral() -> bool:
    return _defer_ephemeral.get()


def _propagate_defer_ephemeral(wrapper: Callable[..., Any], wrapped: Callable[..., Any]) -> None:
    if hasattr(wrapped, "_defer_ephemeral"):
        wrapper._defer_ephemeral = wrapped._defer_ephemeral  # type: ignore[attr-defined]


async def _send_rejection(
    ctx_or_interaction: discord.Interaction | commands.Context,
    message: str,
    *,
    ephemeral: bool = True,
    embed: discord.Embed | None = None,
) -> None:
    if isinstance(ctx_or_interaction, discord.Interaction):
        if embed is not None:
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await ctx_or_interaction.followup.send(content=message, ephemeral=ephemeral)
    elif embed is not None:
        await ctx_or_interaction.send(embed=embed, ephemeral=ephemeral)
    else:
        await ctx_or_interaction.send(content=message, ephemeral=ephemeral)


def _member_has_role(member: discord.Member, role: FunctionalRole, config: Config) -> bool:
    return getattr(config, role.config_attr) in member.roles


def defer(*, ephemeral: bool = True) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            ctx_or_interaction = _resolve_context(args)
            token = _defer_ephemeral.set(ephemeral)
            try:
                if isinstance(ctx_or_interaction, discord.Interaction):
                    await ctx_or_interaction.response.defer(ephemeral=ephemeral)
                else:
                    await ctx_or_interaction.defer(ephemeral=ephemeral)
                return await func(*args, **kwargs)
            finally:
                _defer_ephemeral.reset(token)

        wrapper._defer_ephemeral = ephemeral  # type: ignore[attr-defined]
        return wrapper

    return decorator


def requires_location(
    location: CommandLocation,
    *,
    message: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
    rejection_message = message or _DEFAULT_LOCATION_MESSAGES[location]

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            ctx_or_interaction = _resolve_context(args)
            channel = _get_channel(ctx_or_interaction)
            ephemeral = _get_ephemeral()

            if location == CommandLocation.GUILD:
                if not _is_guild_messageable(channel) or _get_member(ctx_or_interaction) is None:
                    await _send_rejection(ctx_or_interaction, rejection_message, ephemeral=ephemeral)
                    return None
            elif not _is_dm_messageable(channel):
                await _send_rejection(ctx_or_interaction, rejection_message, ephemeral=ephemeral)
                return None

            return await func(*args, **kwargs)

        _propagate_defer_ephemeral(wrapper, func)
        return wrapper

    return decorator


def requires_roles(
    *roles: FunctionalRole,
    message: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
    rejection_message = message or "You are not authorised to run this command."

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            ctx_or_interaction = _resolve_context(args)
            member = _get_member(ctx_or_interaction)
            ephemeral = _get_ephemeral()

            if member is None:
                await _send_rejection(ctx_or_interaction, rejection_message, ephemeral=ephemeral)
                return None

            config: Config = args[0].client.config  # type: ignore[attr-defined, union-attr]
            if not any(_member_has_role(member, role, config) for role in roles):
                await _send_rejection(ctx_or_interaction, rejection_message, ephemeral=ephemeral)
                return None

            return await func(*args, **kwargs)

        _propagate_defer_ephemeral(wrapper, func)
        return wrapper

    return decorator


def handle_command_errors(
    *,
    not_found: str | None = None,
    forbidden: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            ctx_or_interaction = _resolve_context(args)
            ephemeral = _get_ephemeral()
            try:
                return await func(*args, **kwargs)
            except Exception as error:
                await handle_command_error(
                    ctx_or_interaction,
                    error,
                    not_found=not_found,
                    forbidden=forbidden,
                    ephemeral=ephemeral,
                )
                return None

        _propagate_defer_ephemeral(wrapper, func)
        return wrapper

    return decorator
