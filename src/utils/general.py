from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from src.utils.config import Config

COGS_PACKAGE = "src.cogs"


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


def build_notification_embed(
    title: str,
    description: str,
    color: discord.Color,
    fields: list[dict] | None = None,
) -> discord.Embed:
    """Build a standardized notification embed with the PESU Bot footer."""
    embed = discord.Embed(title=title, description=description, color=color)
    if fields:
        for field in fields:
            embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
    embed.timestamp = datetime.now(UTC)
    embed.set_footer(text="PESU Bot")
    return embed


async def send_dm_safely(user: discord.User | discord.Member, embed: discord.Embed) -> bool:
    """Send a DM to a user, returning True on success and False if it could not be delivered."""
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


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


def get_cogs_dir() -> Path:
    """Return the path to the cogs package directory."""
    return Path(__file__).resolve().parent.parent / "cogs"


def discover_cog_extensions(cogs_dir: Path | None = None, package: str = COGS_PACKAGE) -> list[str]:
    """Return import paths for each cog package under cogs_dir."""
    root = cogs_dir or get_cogs_dir()
    extensions: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if not (path / "__init__.py").is_file():
            continue
        extensions.append(f"{package}.{path.name}")
    return extensions


def resolve_cog_extension(name: str, *, package: str = COGS_PACKAGE, cogs_dir: Path | None = None) -> str:
    """Resolve a short or full cog name to a loadable extension path."""
    extensions = discover_cog_extensions(cogs_dir, package)
    if name in extensions:
        return name

    short_name = name.removeprefix(f"{package}.").removeprefix("cogs.")
    extension = f"{package}.{short_name}"
    if extension in extensions:
        return extension

    available = ", ".join(ext.removeprefix(f"{package}.") for ext in extensions)
    msg = f"Unknown cog `{name}`. Available: {available}"
    raise ValueError(msg)
