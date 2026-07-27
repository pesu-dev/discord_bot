from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.utils.config import Config

COGS_PACKAGE = "src.cogs"
DM_AUTO_GENERATED_NOTICE = "(Do not reply to this bot. This message was auto-generated, and replies are not monitored.)"


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


def build_embed(
    title: str = "",
    color: discord.Color | None = None,
    *,
    description: str = "",
    fields: Sequence[dict] = (),
    timestamp: datetime | None = None,
    footer: str = "PESU Bot",
    thumbnail: str | None = None,
) -> discord.Embed:
    """Build an embed. The only place in the repo that constructs ``discord.Embed``."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color if color is not None else discord.Color.default(),
        timestamp=timestamp or datetime.now(UTC),
    )
    for field in fields:
        embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
    if thumbnail is not None:
        embed.set_thumbnail(url=thumbnail)
    embed.set_footer(text=footer)
    return embed


async def send_dm_safely(
    user: discord.User | discord.Member,
    embed: discord.Embed | None = None,
    *,
    content: str | None = None,
) -> bool:
    """Send a DM to a user, returning True on success and False if it could not be delivered.

    At least one of ``embed`` or ``content`` must be provided.
    """
    if embed is None and content is None:
        raise ValueError("send_dm_safely requires embed and/or content")

    embeds: list[discord.Embed] = []
    if embed is not None:
        embeds.append(embed)
    embeds.append(build_embed(description=DM_AUTO_GENERATED_NOTICE))

    try:
        await user.send(content=content, embeds=embeds)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def build_unknown_error_embed(error: Exception) -> discord.Embed:
    return build_embed(
        title="❗ Unexpected Error",
        color=discord.Color.red(),
        description="Something went wrong while processing the command.",
        fields=[
            {"name": "Error Type", "value": type(error).__name__, "inline": True},
            {"name": "Details", "value": str(error)[:1000] or "No details available."},
            {
                "name": "Support",
                "value": "Please report this to the developers if it keeps happening.",
            },
        ],
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
