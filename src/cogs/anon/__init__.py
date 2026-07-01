from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class AnonGroups:
    anon = app_commands.Group(name="anon", description="Anonymous messaging commands")


async def setup(client: DiscordBot) -> None:
    from src.cogs.anon.cog import SlashAnon

    cog = SlashAnon(client)
    await client.add_cog(cog, guild=client.config.guild_object)
    client.tree.add_command(
        cog.ctx_menu,
        guild=client.config.guild_object,
    )
