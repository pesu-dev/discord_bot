from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext.commands import Cog

from src.cogs.general.commands import GeneralCommands
from src.cogs.general.components import RoleSelectView
from src.cogs.general.helpers import GeneralHelpers

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashGeneral(GeneralHelpers, GeneralCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.cached_data = None
        self.client.add_view(RoleSelectView(client))


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashGeneral(client),
        guild=client.config.guild_object,
    )
