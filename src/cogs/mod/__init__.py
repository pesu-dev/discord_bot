from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class ModGroups:
    mod = app_commands.Group(name="mod", description="Moderation commands")
    mod_link = app_commands.Group(
        name="link",
        description="Linking moderation",
        parent=mod,
    )


async def setup(client: DiscordBot) -> None:
    from src.cogs.mod.cog import SlashMod

    await client.add_cog(
        SlashMod(client),
        guild=client.config.guild_object,
    )
