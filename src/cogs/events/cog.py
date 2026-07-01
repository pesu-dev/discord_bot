from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

from src.cogs.events.listeners import EventListeners

if TYPE_CHECKING:
    from src.bot import DiscordBot


class Events(EventListeners, commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
