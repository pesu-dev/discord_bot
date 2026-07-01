from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

from src.cogs.eng import EngGroups
from src.cogs.eng.commands import EngCommands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashEng(EngGroups, EngCommands, commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
