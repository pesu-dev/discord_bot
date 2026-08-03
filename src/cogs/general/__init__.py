from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext.commands import Cog

from src.cogs.general.commands import GeneralCommands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashGeneral(GeneralCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.cached_data = None


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashGeneral(client),
        guild=client.config.guild_object,
    )
