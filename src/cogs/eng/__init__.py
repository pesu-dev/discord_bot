from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext.commands import Cog

from src.cogs.eng.commands import EngCommands
from src.cogs.eng.groups import EngGroups

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashEng(EngGroups, EngCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashEng(client),
        guild=client.config.guild_object,
    )
