from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext.commands import Cog

from src.cogs.help.commands import HelpCommands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashHelp(HelpCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashHelp(client),
        guild=client.config.guild_object,
    )
