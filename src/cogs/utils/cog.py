from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

from src.cogs.utils.commands import UtilsCommands
from src.cogs.utils.components import RoleSelectView

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashUtils(UtilsCommands, commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.cached_data = None
        self.client.add_view(RoleSelectView(client))
