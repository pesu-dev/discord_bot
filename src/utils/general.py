from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from src.utils.config import Config


def parse_time(time_str: str) -> int:
    """Parse a duration string ending in y/d/h/m/s into seconds."""
    time_str = time_str.lower().strip()
    try:
        if time_str.endswith("y"):
            return int(time_str[:-1]) * 24 * 60 * 60 * 365
        if time_str.endswith("d"):
            return int(time_str[:-1]) * 24 * 60 * 60
        if time_str.endswith("h"):
            return int(time_str[:-1]) * 60 * 60
        if time_str.endswith("m"):
            return int(time_str[:-1]) * 60
        if time_str.endswith("s"):
            return int(time_str[:-1])
        return int(time_str)
    except ValueError:
        raise ValueError("Invalid time format") from None


def build_unknown_error_embed(error: Exception) -> discord.Embed:
    return (
        discord.Embed(
            title="❗ Unexpected Error",
            description="Something went wrong while processing the command.",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        .add_field(name="Error Type", value=type(error).__name__, inline=True)
        .add_field(
            name="Details",
            value=str(error)[:1000] or "No details available.",
            inline=False,
        )
        .add_field(
            name="Support",
            value="Please report this to the developers if it keeps happening.",
            inline=False,
        )
        .set_footer(
            text="PESU Bot",
        )
    )


async def handle_command_error(
    ctx_or_interaction: discord.Interaction | commands.Context,
    error: Exception,
    *,
    not_found: str | None = None,
    forbidden: str | None = None,
    ephemeral: bool = True,
) -> None:
    original: BaseException = error
    if isinstance(error, app_commands.CommandInvokeError | commands.CommandInvokeError):
        original = error.original

    if isinstance(original, discord.NotFound):
        message = not_found or "The requested resource was not found."
        await _send_command_error(ctx_or_interaction, message, ephemeral=ephemeral)
    elif isinstance(original, discord.Forbidden):
        message = forbidden or "I do not have permission to do that."
        await _send_command_error(ctx_or_interaction, message, ephemeral=ephemeral)
    else:
        embed = build_unknown_error_embed(original if isinstance(original, Exception) else error)
        await _send_command_error(ctx_or_interaction, embed=embed, ephemeral=ephemeral)


async def _send_command_error(
    ctx_or_interaction: discord.Interaction | commands.Context,
    message: str = "",
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
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


def mod_target_error(
    member: discord.Member,
    config: Config,
    *,
    allow_mod_target: bool = False,
) -> str | None:
    """Return user-facing error string, or None if target is valid."""
    if member.bot:
        return "You dare target one of my kind nin amn"
    if not allow_mod_target and any(role in member.roles for role in (config.admin_role, config.mod_role)):
        return "Leyy, he's admin/mod. Can't target them"
    return None
